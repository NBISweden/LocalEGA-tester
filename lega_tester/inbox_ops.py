import paramiko
import os
import logging
from tenacity import retry, stop_after_delay, wait_fixed
from legacryptor.crypt4gh import encrypt
from hashlib import md5


FORMAT = '[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s] (L:%(lineno)s) %(funcName)s: %(message)s'
logging.basicConfig(format=FORMAT, datefmt='%Y-%m-%d %H:%M:%S')
LOG = logging.getLogger(__name__)
# By default the logging level would be INFO
log_level = os.environ.get('DEFAULT_LOG', 'INFO').upper()
LOG.setLevel(log_level)


@retry(wait=wait_fixed(20000), stop=(stop_after_delay(360000)))
def open_ssh_connection(hostname, user, key_path, key_pass='password', port=2222):
    """Open an ssh connection, test function."""
    try:
        client = paramiko.SSHClient()
        k = paramiko.RSAKey.from_private_key_file(key_path, password=key_pass)
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname, allow_agent=False, look_for_keys=False,
                       port=port, timeout=0.3, username=user, pkey=k)
        LOG.info(f'ssh connected to {hostname}:{port} with {user} | PASS |')
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
        LOG.debug(f'sftp connected to {hostname}:{port} with {user}')
        sftp = paramiko.SFTPClient.from_transport(transport)
        filename, _ = os.path.splitext(file_path)
        output_base = os.path.basename(filename)
        if os.path.isfile(file_path):
            sftp.put(file_path, f'{output_base}.c4ga')
        else:
            raise IOError('Could not find localFile {file_path} !!')
        LOG.info(f'file uploaded {output_base}.c4ga | PASS |')
    except Exception as e:
        LOG.error(f'Something went wrong {e}')
        raise e
    finally:
        LOG.debug('sftp done')
        transport.close()


def encrypt_file(file_path, pubkey):
    """Encrypt file and extract its md5."""
    file_size = os.path.getsize(file_path)
    filename, _ = os.path.splitext(file_path)
    c4ga_md5 = None
    output_file = os.path.expanduser(f'{filename}.c4ga')
    infile = open(file_path, 'rb')
    try:
        encrypt(pubkey, infile, file_size, open(f'{filename}.c4ga', 'wb'))
        with open(filename, 'rb') as read_file:
            c4ga_md5 = md5(read_file.read()).hexdigest()
        LOG.debug(f'File {filename}.c4ga is the encrypted file with md5: {c4ga_md5}.')
    except Exception as e:
        LOG.error(f'Something went wrong {e}')
        raise e
    return (output_file, c4ga_md5)
