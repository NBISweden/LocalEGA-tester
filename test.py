import paramiko
import os
import pika
import secrets
from hashlib import md5
import json
import string
import sys
import logging
from legacryptor.crypt4gh import encrypt, Header, get_header
import pgpy
import argparse
from minio import Minio
from time import sleep
import requests
import filecmp
import asyncio
import asyncpg
import yaml
from urllib.parse import urlparse


FORMAT = '[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s] (L:%(lineno)s) %(funcName)s: %(message)s'
logging.basicConfig(format=FORMAT, datefmt='%Y-%m-%d %H:%M:%S')
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


async def get_last_id(db_user, db_name, db_pass, db_host):
    """Retrieve the last inserted file in the database, indifferent of status."""
    conn = await asyncpg.connect(user=db_user, password=db_pass,
                                 database=db_name, host=db_host)
    values = await conn.fetchrow('''SELECT created_at, id FROM local_ega.files ORDER BY created_at DESC LIMIT 1''')
    LOG.info(f"Database ID: {values['id']}")
    return values['id']
    await conn.close()


async def file2dataset_map(db_user, db_name, db_pass, db_host, file_id, dataset_id):
    """Assign file to dataset for dataset driven permissions."""
    conn = await asyncpg.connect(user=db_user, password=db_pass,
                                 database=db_name, host=db_host)
    last_index = await conn.fetchrow('''select id from local_ega.file2dataset ORDER BY id DESC LIMIT 1''')
    await conn.execute('''
        INSERT INTO local_ega.file2dataset(id, file_id, dataset_id) VALUES($1, $2, $3)
    ''', last_index['id'] + 1 if last_index else 1, file_id, dataset_id)
    LOG.info(f"Mapped ID: {file_id} to Dataset: {dataset_id}")
    await conn.close()


def open_ssh_connection(hostname, user, key_path, key_pass='password', port=2222):
    """Open an ssh connection, test function."""
    try:
        client = paramiko.SSHClient()
        k = paramiko.RSAKey.from_private_key_file(key_path, password=key_pass)
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname, allow_agent=False, look_for_keys=False, port=port, timeout=0.3, username=user, pkey=k)
        LOG.info(f'ssh connected to {hostname}:{port} with {user}')
    except paramiko.BadHostKeyException as e:
        LOG.error(f'Something went wrong {e}')
        raise Exception('BadHostKeyException on ' + hostname)
    except paramiko.AuthenticationException as e:
        LOG.error(f'Something went wrong {e}')
        raise Exception('AuthenticationException on ' + hostname)
    except paramiko.SSHException as e:
        LOG.error(f'Something went wrong {e}')
        raise Exception('SSHException on ' + hostname)

    return client


def sftp_upload(hostname, user, file_path, key_path, key_pass='password', port=2222):
    """SFTP Client file upload."""
    try:
        k = paramiko.RSAKey.from_private_key_file(key_path, password=key_pass)
        transport = paramiko.Transport((hostname, port))
        transport.connect(username=user, pkey=k)
        LOG.info(f'sftp connected to {hostname}:{port} with {user}')
        sftp = paramiko.SFTPClient.from_transport(transport)
        filename, _ = os.path.splitext(file_path)
        sftp.put(file_path, f'{filename}.c4ga')
        LOG.info(f'file uploaded {filename}.c4ga')
    except Exception as e:
        LOG.error(f'Something went wrong {e}')
        raise e
    finally:
        LOG.debug('sftp done')
        transport.close()


def submit_cega(address, user, vhost, message, routing_key, mq_password, correlation_id, port=5672, file_md5=None):
    """Submit message to CEGA along with."""
    mq_address = f'amqp://{user}:{mq_password}@{address}:{port}/{vhost}'
    try:
        parameters = pika.URLParameters(mq_address)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.basic_publish(exchange='localega.v1', routing_key=routing_key,
                              body=json.dumps(message),
                              properties=pika.BasicProperties(correlation_id=correlation_id,
                                                              content_type='application/json',
                                                              delivery_mode=2))

        connection.close()
        LOG.info(f'Message published to CentralEGA: {message}')
    except Exception as e:
        LOG.error(f'Something went wrong {e}')
        raise e


def get_corr(address, user, vhost, queue, filepath, mq_password, latest_message=True, port=5672):
    """Read all messages from a queue and fetches the correlation_id for the one with given path, if found."""
    mq_address = f'amqp://{user}:{mq_password}@{address}:{port}/{vhost}'
    parameters = pika.URLParameters(mq_address)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    correlation_ids = []
    messages = set()
    while True:
        method_frame, props, body = channel.basic_get(queue=queue)

        if method_frame is None or props is None:
            break
            LOG.error('No message returned')

        message_id = method_frame.delivery_tag
        if message_id in messages:  # we looped
            break
        messages.add(message_id)

        try:
            data = json.loads(body)
            user = data.get('user')
            filepath = data.get('filepath')
            assert(user and filepath)
            if user == user and filepath == filepath:
                correlation_ids.append((props.correlation_id, message_id))
        except Exception as e:
            LOG.error(f'Something went wrong {e}')
            pass

    # Second loop, nack the messages
    for message_id in messages:
        channel.basic_nack(delivery_tag=message_id)

    connection.close()

    if not correlation_ids:
        sys.exit(2)

    correlation_id = correlation_ids[0][0]
    if latest_message:
        message_id = -1  # message ids are positive
        for cid, mid in correlation_ids:
            if mid > message_id:
                correlation_id = cid
    LOG.info(f'correlation_id: {correlation_id}')
    return correlation_id


def encrypt_file(file_path, pubkey):
    """Encrypt file and extract its md5."""
    file_size = os.path.getsize(file_path)
    filename, _ = os.path.splitext(file_path)
    output_base = os.path.basename(filename)
    c4ga_md5 = None
    output_file = os.path.expanduser(f'{output_base}.c4ga')
    infile = open(file_path, 'rb')
    try:
        encrypt(pubkey, infile, file_size, open(f'{output_base}.c4ga', 'wb'))
        with open(output_file, 'rb') as read_file:
            c4ga_md5 = md5(read_file.read()).hexdigest()
        LOG.info(f'File {output_base}.c4ga is the encrypted file with md5: {c4ga_md5}.')
    except Exception as e:
        LOG.error(f'Something went wrong {e}')
        raise e
    return (output_file, c4ga_md5)


def strip_scheme(url):
    """Remove scheme from url.

    Used to remove scheme from S3 address.
    """
    parsed = urlparse(url)
    scheme = "%s://" % parsed.scheme
    return parsed.geturl().replace(scheme, '', 1)


def list_s3_objects(minio_address, bucket_name, region_name, file_id, access, secret):
    """Check if there is a file inside s3."""
    minioClient = Minio(strip_scheme(minio_address), access_key=access, secret_key=secret,
                        region=region_name, secure=False)
    LOG.info(f'Connected to S3: {minio_address}.')
    # List all object paths in bucket that begin with my-prefixname.
    objects = minioClient.list_objects_v2(bucket_name, recursive=True)
    object_list = [obj.object_name for obj in objects]
    assert str(file_id) in object_list, f"Could not find the file just uploaded!"
    LOG.info(f"Found the file uploaded to inbox as {file_id} in S3Storage.")
    # all_objects = minioClient.list_objects(bucket_name, recursive=True)
    # LOG.info("All the files in Lega bucket: ")
    # for obj in all_objects:
    #     LOG.info(f'Found ingested file: {obj.object_name} of size: {obj.size}.')


def main():
    """Do the sparkles and fireworks."""
    parser = argparse.ArgumentParser(description="M4 end to end test with YAML configuration.")

    # Should we do this in a configuration file ?
    parser.add_argument('input', help='File to be uploaded.')
    parser.add_argument('config', help='Configuration file.')

    args = parser.parse_args()
    used_file = os.path.expanduser(args.input)
    config_file = os.path.expanduser(args.config)

    with open(config_file, 'r') as stream:
        try:
            config_file = yaml.load(stream)
        except yaml.YAMLError as exc:
            LOG.error(exc)

    # Initialise what is needed

    res_file = 'res.file'
    dataedge_file = 'dataedge.file'
    config = config_file['localega']
    key_pk = os.path.expanduser(config['user_key'])
    pub_key, _ = pgpy.PGPKey.from_file(os.path.expanduser(config['encrypt_key_public']))
    sec_key, _ = pgpy.PGPKey.from_file(config['encrypt_key_private'])
    loop = asyncio.get_event_loop()
    session_key = ''
    iv = ''
    fileID = ''
    token = config['token']

    test_user = config['user']
    # TEST Connection before anything
    open_ssh_connection(config['inbox_address'], test_user, key_pk)
    # Encrypt File
    test_file, c4ga_md5 = encrypt_file(used_file, pub_key)
    # Retrieve session_key and IV to test RES
    with sec_key.unlock(config['encrypt_key_pass']) as privkey:
        header = Header.decrypt(get_header(open(test_file, 'rb'))[1], privkey)
        session_key = header.records[0].session_key.hex()
        iv = header.records[0].iv.hex()
    # Stable ID is mocked this should be generated by CentralEGA
    stableID = ''.join(secrets.choice(string.digits) for i in range(16))
    if c4ga_md5:
        sftp_upload(config['inbox_address'], test_user, test_file, key_pk, port=int(config['inbox_port']))
        correlation_id = get_corr(config['cm_address'], config['cm_user'],
                                  config['cm_vhost'], 'v1.files.inbox', test_file, config['cm_pass'])
        submit_cega(config['cm_address'], config['cm_user'], config['cm_vhost'],
                    {'user': test_user, 'filepath': test_file}, 'files',
                    config['cm_pass'], correlation_id)
        # wait for submission to go through - might need to be longer depending on the file
        # proper retry should be implemented
        sleep(30)
        # Once the file has been ingested it should be the last ID in the database
        # We use this ID everywhere including donwload from DataEdge
        # In future versions once we fix DB schema we will use StableID for download
        fileID = loop.run_until_complete(get_last_id(config['db_user'], config['db_name'],
                                                     config['db_pass'], config['db_address']))
        # Stable ID should be sent by CentralEGA
        submit_cega(config['cm_address'], config['cm_user'], config['cm_vhost'],
                    {'file_id': fileID, 'stable_id': f'EGAF{stableID}'}, 'stableIDs',
                    config['cm_pass'], correlation_id)
        # wait for the file in s3
        # proper retry should be implemented
        sleep(30)
        list_s3_objects(config['s3_address'], config['s3_region'],
                        config['s3_bucket'], fileID,
                        config['s3_access'], config['s3_secret'])
    LOG.info('Ingestion DONE')
    LOG.info('-------------------------------------')
    # Verify that the file can be downloaded from RES using the session_key and IV
    payload = {'sourceKey': session_key, 'sourceIV': iv, 'filePath': fileID}
    res_url = f"http://{config['res_address']}:{config['res_address']}/file"
    download = requests.get(res_url, params=payload)
    # We are using filecmp thus we will write content to file
    assert download.status_code == 200, f'We got a different status from RES {download.status_code}'
    LOG.info(f'write content to {res_file}')
    open(res_file, 'wb').write(download.content)
    LOG.info('Comparing RES downloaded file with original file ...')
    # comparing content of the files
    assert filecmp.cmp(res_file, used_file, shallow=False), 'files are not equal'
    # The low level alternative would be:
    # with open(res_file) as f1:
    #     with open(used_file) as f2:
    #         if f1.read() == f2.read():
    #             pass
    LOG.info('RES Downloaded file is equal to the original file.')

    LOG.info('Mapping file to dataset for retrieving file via dataedge.')

    # There is no component asigning permissions for files in datasets
    # Thus we need this step
    # for now this dataset ID is fixed to 'EGAD01' as we have it like this in the TOKEN
    # Will need updating once we decide on the permissions handling
    loop.run_until_complete(file2dataset_map(config['db_user'], config['db_name'],
                                             config['db_pass'], config['db_address'],
                                             fileID, 'EGAD01'))

    # Verify that the file can be downloaded from DataEdge
    # We are using a token that can be validated by DataEdge
    edge_payload = {'destinationFormat': 'plain'}
    edge_headers = {'Authorization': f'Bearer {token}'}  # No token no permissions
    dataedge_url = f"http://{config['dataedge_address']}:{config['dataedge_port']}/files/{fileID}"
    down_dataedge = requests.get(dataedge_url, params=edge_payload, headers=edge_headers)
    LOG.info(down_dataedge.url)

    # 206 would be a partial content that means we misshandle some bytes
    assert down_dataedge.status_code == 200, f'We got a different status from DataEdge {down_dataedge.status_code}'
    LOG.info(f'write content to {dataedge_file}')
    open(dataedge_file, 'wb').write(down_dataedge.content)
    LOG.info('Comparing Dataedge downloaded file with original file ...')
    # comparing content of the files
    assert filecmp.cmp(dataedge_file, used_file, shallow=False), 'files are not equal'
    LOG.info('Dataedge Downloaded file is equal to the original file.')

    LOG.info('Outgestion DONE')
    LOG.info('-------------------------------------')
    LOG.info('Should be all!')


if __name__ == '__main__':
    assert sys.version_info >= (3, 6), "M4 end to end test requires python3.6"
    main()
