
import os
import logging
import psycopg2
from .utils import is_none_p
from tenacity import retry, stop_after_delay, wait_exponential, retry_if_result


FORMAT = '[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s] (L:%(lineno)s) %(funcName)s: %(message)s'
logging.basicConfig(format=FORMAT, datefmt='%Y-%m-%d %H:%M:%S')
LOG = logging.getLogger(__name__)
# By default the logging level would be INFO
log_level = os.environ.get('DEFAULT_LOG', 'INFO').upper()
LOG.setLevel(log_level)


def get_last_id(db_user, db_name, db_pass, db_host, ssl_enable):
    """Retrieve the last inserted file in the database, indifferent of status."""
    conn = psycopg2.connect(user=db_user, password=db_pass,
                            database=db_name, host=db_host,
                            # We might need to use `verify-ca`
                            # but for standard ssl connection `require` is eneough
                            sslmode='require' if ssl_enable else 'disable')
    cursor = conn.cursor()
    cursor.execute('''SELECT created_at, id FROM local_ega.files ORDER BY created_at DESC LIMIT 1''')
    values = cursor.fetchone()
    if (values is None):
        LOG.debug(f'Database is empty')
        cursor.close()
        conn.close()
        return 0
    else:
        LOG.debug(f"Database ID: {values}")
        cursor.close()
        conn.close()
        return values[1]


def get_file_status(db_user, db_name, db_pass, db_host, file_id, ssl_enable):
    """Retrieve the last inserted file in the database, indifferent of status."""
    conn = psycopg2.connect(user=db_user, password=db_pass,
                            database=db_name, host=db_host,
                            # We might need to use `verify-ca`
                            # but for standard ssl connection `require` is eneough
                            sslmode='require' if ssl_enable else 'disable')
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM local_ega.files where id = %(file_id)s', {"file_id": file_id})
    status = cursor.fetchone()[0]
    LOG.debug(f"File status: {status}")
    cursor.close()
    conn.close()
    return status

@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=(stop_after_delay(14400)),
       retry=(retry_if_result(is_none_p)))  #noqa: C901
def ensure_db_status(config, fileID, expected_status):
    """Verify DB status is correct before continuing."""
    status = get_file_status(config['db_in_user'], config['db_name'],
                             config['db_in_pass'], config['db_address'],
                             fileID,
                             config['db_ssl'])
    while (status != expected_status):
        return None

    return status


def file2dataset_map(db_user, db_name, db_pass, db_host, file_id, dataset_id, ssl_enable):
    """Assign file to dataset for dataset driven permissions."""
    conn = psycopg2.connect(user=db_user, password=db_pass,
                            database=db_name, host=db_host,
                            # We might need to use `verify-ca`
                            # but for standard ssl connection `require` is eneough
                            sslmode='require' if ssl_enable else 'disable')
    last_index = None
    with conn.cursor() as cursor:
        cursor.execute('''SELECT id FROM local_ega_ebi.filedataset ORDER BY id DESC LIMIT 1''')
        value = cursor.fetchone()
        last_index = value[0] if value is not None else 0
    with conn.cursor() as cursor:
        cursor.execute('INSERT INTO local_ega_ebi.filedataset(id, file_id, dataset_stable_id) VALUES(%(last_index)s, %(file_id)s, %(dataset_id)s)',
                       {"last_index": last_index + 1 if last_index is not None else 1, "file_id": file_id, "dataset_id": dataset_id})
        LOG.debug(f"Mapped ID: {file_id} to Dataset: {dataset_id}")
        conn.commit()
    conn.close()
