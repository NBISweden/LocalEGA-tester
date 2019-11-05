import os
import secrets
import string
import sys
import logging
from legacryptor.crypt4gh import Header, get_header
import pgpy
import argparse
import yaml
from .utils import download_to_file, compare_files, is_none_p, read_enc_file_values
from .archive_ops import list_s3_objects, check_file_exists
from .db_ops import get_last_id, ensure_db_status, file2dataset_map
from .mq_ops import submit_cega, get_corr, purge_cega_mq
from .inbox_ops import encrypt_file, open_ssh_connection, sftp_upload, sftp_remove
from pathlib import Path
from tenacity import retry, stop_after_delay, wait_exponential, retry_if_result


VALUES_FILE = '/volume/enc_file_values.txt'

FORMAT = '[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s] (L:%(lineno)s) %(funcName)s: %(message)s'
logging.basicConfig(format=FORMAT, datefmt='%Y-%m-%d %H:%M:%S')
LOG = logging.getLogger(__name__)
# By default the logging level would be INFO
log_level = os.environ.get('DEFAULT_LOG', 'INFO').upper()
LOG.setLevel(log_level)


def prepare_config(conf):
    """Prepare configuration variables after parsing config file."""
    with open(conf, 'r') as stream:
        try:
            config_file = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            LOG.error(exc)

    return config_file['localega']


# TESTS


def test_step_upload(config, test_user, test_file):
    """Do the first step of the test, send file to inbox."""
    key_pk = os.path.expanduser(config['user_key'])
    # Test Inbox Connection before anything
    open_ssh_connection(config['inbox_address'], test_user, key_pk, port=int(config['inbox_port']))
    sftp_upload(config['inbox_address'], test_user, test_file, key_pk, port=int(config['inbox_port']))


def test_step_check_archive(config, fileID):
    """Check the archive if the file was archived."""
    # default to S3 Archive as this is default setup.
    if 'data_storage_type' in config and config['data_storage_type']:
        storage_type = config['data_storage_type']
    else:
        storage_type = "S3Storage"
    if storage_type == "S3Storage":
        check_file_exists(config['s3_address'], config['s3_bucket'],
                          config['s3_region'], fileID,
                          config['s3_access'], config['s3_secret'],
                          config['s3_ssl'],
                          config['tls_ca_root_file'])
        # While we are at it let us see what is inside the S3 Archive
        list_s3_objects(config['s3_address'], config['s3_bucket'],
                        config['s3_region'], fileID,
                        config['s3_access'], config['s3_secret'],
                        config['s3_ssl'],
                        config['tls_ca_root_file'])
    elif storage_type == "FileStorage":
        assert Path.is_file(f'/ega/archive/{fileID}'), f"Could not find the file just uploaded! | FAIL | "
        file_path = Path(f'/ega/archive/{fileID}')
        LOG.debug(f'Found ingested file: {file_path.name} of size: {file_path.stat().st_size}.')


def test_step_res_download(config, filename, fileID, used_file, session_key, iv):
    """Test download from RES service.

    Not necessary but good to have and see before testing dataedge
    """
    # Verify that the file can be downloaded from RES using the session_key and IV
    res_file = f'/volume/{filename}.res'
    res_payload = {'sourceKey': session_key, 'sourceIV': iv, 'filePath': fileID}
    res_url = f"https://{config['res_address']}:{config['res_port']}/file"
    # download_to_file(res_url, res_payload, res_file,
    #                  config['tls_cert_tester'],
    #                  config['tls_key_tester'])
    download_to_file(config['tls_ca_root_file'], res_url, res_payload, res_file)
    compare_files('RES', res_file, used_file)


def test_step_dataedge_download(config, filename, stableID, used_file):
    """Test download from DataEdge service."""
    # Verify that the file can be downloaded from DataEdge
    # We are using a token that can be validated by DataEdge
    token = config['token']
    dataedge_file = f'/volume/{filename}.dataedge'
    edge_payload = {'destinationFormat': 'plain'}
    edge_headers = {'Authorization': f'Bearer {token}'}  # No token no permissions
    dataedge_url = f"https://{config['dataedge_address']}:{config['dataedge_port']}/files/{stableID}"
    # download_to_file(dataedge_url, edge_payload, dataedge_file,
    #                  config['tls_cert_tester'],
    #                  config['tls_key_tester'], headers=edge_headers)
    download_to_file(config['tls_ca_root_file'], dataedge_url, edge_payload, dataedge_file, headers=edge_headers)
    compare_files('DataEdge', dataedge_file, used_file)


# FIXTURES


def fixture_step_db_id(config):
    """Do a check of the DB ids."""
    # Get current id from database
    current_id = get_last_id(config['db_in_user'], config['db_name'],
                             config['db_in_pass'], config['db_address'],
                             config['db_ssl'])
    LOG.debug(f'Current last DB id {current_id}')
    return current_id


@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=(stop_after_delay(14400)),
       retry=(retry_if_result(is_none_p)))  #noqa: C901
def fixture_step_file_id(config, db_id):
    """Get FileID to the file just uploaded."""
    fileID = get_last_id(config['db_in_user'], config['db_name'],
                         config['db_in_pass'], config['db_address'],
                         config['db_ssl'])
    while (fileID <= db_id):
        return None

    return fileID


def fixture_step_encrypt(config, original_file):
    """Encrypt file and retrieve necessary info for test."""
    pub_key, _ = pgpy.PGPKey.from_file(Path(config['encrypt_key_public']))
    sec_key, _ = pgpy.PGPKey.from_file(config['encrypt_key_private'])
    # Encrypt File
    test_file = encrypt_file(original_file, pub_key)
    # Retrieve session_key and IV to test RES
    with sec_key.unlock(config['encrypt_key_pass']) as privkey:
        header = Header.decrypt(get_header(open(test_file, 'rb'))[1], privkey)
        session_key = header.records[0].session_key.hex()
        iv = header.records[0].iv.hex()

    with open(VALUES_FILE, 'w+') as enc_file:
        enc_file.write(f'{original_file},{test_file},{session_key},{iv}')


def fixture_step_completed(config, current_id, output_base):
    """Test if file has completed both in MQ and in DB."""
    # Once the file has been ingested it should be the last ID in the database
    # We use this ID everywhere including donwload from DataEdge
    # In future versions once we fix DB schema we will use StableID for download
    cm_protocol = 'amqps' if config['cm_ssl'] else 'amqp'
    # wait for submission to go through
    get_corr(cm_protocol, config['cm_address'], config['cm_user'],
             config['cm_vhost'], 'v1.files.completed', f'{output_base}.c4ga',
             config['cm_pass'],
             config['tls_ca_root_file'],
             config['tls_cert_tester'],
             config['tls_key_tester'],
             port=config['cm_port'])


def fixture_step_purge(config):
    """Purge MQ queues, to clean after test."""
    cm_protocol = 'amqps' if config['cm_ssl'] else 'amqp'
    purge_cega_mq(cm_protocol, config['cm_address'], config['cm_user'],
                  config['cm_vhost'],
                  config['cm_pass'],
                  config['tls_ca_root_file'],
                  config['tls_cert_tester'],
                  config['tls_key_tester'],
                  port=config['cm_port'])

# FAKING CEGA DEPENDENCIES


def dependency_make_cega_submission(config, test_user, output_base):
    """Fake a submission in order to trigger ingestion.

    In a real case scenario this would be done at CEGA.
    """
    # Stable ID is mocked as this should be generated by CentralEGA
    cm_protocol = 'amqps' if config['cm_ssl'] else 'amqp'
    correlation_id = get_corr(cm_protocol, config['cm_address'], config['cm_user'], config['cm_vhost'],
                              'v1.files.inbox', f'{output_base}.c4ga',
                              config['cm_pass'],
                              config['tls_ca_root_file'],
                              config['tls_cert_tester'],
                              config['tls_key_tester'],
                              port=config['cm_port'])
    submit_cega(cm_protocol, config['cm_address'], config['cm_user'], config['cm_vhost'],
                {'user': test_user, 'filepath': f'{output_base}.c4ga'}, 'files',
                config['cm_pass'], correlation_id,
                config['tls_ca_root_file'],
                config['tls_cert_tester'],
                config['tls_key_tester'],
                port=config['cm_port'])

    return correlation_id


def dependency_make_cega_stableID(config, fileID, correlation_id, stableID):
    """Fake generation of a stableID once a file has been ingested.

    In a real case there will be a service on CEGA watching the MQ queue and
    generating one.
    """
    cm_protocol = 'amqps' if config['cm_ssl'] else 'amqp'
    submit_cega(cm_protocol, config['cm_address'], config['cm_user'], config['cm_vhost'],
                {'file_id': fileID, 'stable_id': stableID}, 'stableIDs',
                config['cm_pass'], correlation_id,
                config['tls_ca_root_file'],
                config['tls_cert_tester'],
                config['tls_key_tester'],
                port=config['cm_port'])


def dependency_map_file2dataset(config, fileID):
    """Map file to dataset for retrieving file via dataedge."""
    LOG.debug('Mapping file to dataset for retrieving file via dataedge.')

    # There is no component asigning permissions for files in datasets
    # Thus we need this step
    # for now this dataset ID is fixed to 'EGAD01' as we have it like this in the TOKEN
    # Will need updating once we decide on the permissions handling
    file2dataset_map(config['db_out_user'], config['db_name'],
                     config['db_out_pass'], config['db_address'],
                     fileID, 'EGAD01',
                     config['db_ssl'])


def enc_file():
    """Encrypt file and store information about it."""
    parser = argparse.ArgumentParser(description="End to end test for LocalEGA,\
                                                  with YAML configuration.")

    # Should we do this in a configuration file ?
    parser.add_argument('input', help='File to be uploaded.')
    parser.add_argument('config', help='Configuration file.')

    args = parser.parse_args()
    original_file = Path(args.input)
    config = prepare_config(Path(args.config))
    fixture_step_encrypt(config, original_file)
    LOG.debug('-------------------------------------')
    LOG.info('file encrypted!')


def main():
    """Do the sparkles and fireworks."""
    parser = argparse.ArgumentParser(description="End to end test for LocalEGA,\
                                                  with YAML configuration.")
    parser.add_argument('config', help='Configuration file.')

    args = parser.parse_args()

    enc_data = Path(VALUES_FILE)
    # Initialise what is needed
    config = prepare_config(Path(args.config))
    test_user = config['user']

    db_id = fixture_step_db_id(config)
    current_id = 1 if db_id == 0 else db_id
    original_file, test_file, session_key, iv = read_enc_file_values(enc_data)

    enc_file = Path(test_file)
    filename = Path(enc_file).stem
    output_base = Path(filename).name

    test_step_upload(config, test_user, test_file)
    correlation_id = dependency_make_cega_submission(config, test_user, output_base)

    # Stable ID should be sent by CentralEGA
    stableID = 'EGAF'+''.join(secrets.choice(string.digits) for i in range(16))
    fileID = fixture_step_file_id(config, db_id)

    # Wait for file status
    # check that verify did its job and put the file in COMPLETED
    ensure_db_status(config, fileID, "COMPLETED")

    # check file is in archive
    test_step_check_archive(config, fileID)

    # Additional step and not really needed
    fixture_step_completed(config, current_id, output_base)
    dependency_make_cega_stableID(config, fileID, correlation_id, stableID)

    # check that finalize did its job and put the file in READY
    # needed for downloading
    ensure_db_status(config, fileID, "READY")
    LOG.debug('Ingestion DONE')
    LOG.debug('-------------------------------------')
    test_step_res_download(config, filename, fileID, original_file, session_key, iv)

    dependency_map_file2dataset(config, fileID)
    test_step_dataedge_download(config, filename, stableID, original_file)

    LOG.debug('Outgestion DONE')
    LOG.debug('-------------------------------------')

    LOG.debug('Cleaning up ...')
    sftp_remove(config['inbox_address'], test_user, test_file,
                os.path.expanduser(config['user_key']),
                port=int(config['inbox_port']))
    fixture_step_purge(config)
    LOG.debug('-------------------------------------')
    LOG.info('Should be all!')


if __name__ == '__main__':
    assert sys.version_info >= (3, 6), "End to end test requires python3.6"
    main()
