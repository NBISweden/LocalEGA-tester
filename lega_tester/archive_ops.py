import os
import logging
from minio import Minio
from distutils import util
from tenacity import retry, stop_after_delay, wait_fixed
from .utils import strip_url_scheme


FORMAT = '[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s] (L:%(lineno)s) %(funcName)s: %(message)s'
logging.basicConfig(format=FORMAT, datefmt='%Y-%m-%d %H:%M:%S')
LOG = logging.getLogger(__name__)
# By default the logging level would be INFO
log_level = os.environ.get('DEFAULT_LOG', 'INFO').upper()
LOG.setLevel(log_level)

SSL_ENABLE = bool(util.strtobool(os.environ.get('TLS_ENABLE', 'false')))


@retry(wait=wait_fixed(20000), stop=(stop_after_delay(360000)))
def list_s3_objects(minio_address, bucket_name, region_name, file_id, access, secret):
    """Check if there is a file inside s3."""
    minioClient = Minio(strip_url_scheme(minio_address), access_key=access, secret_key=secret,
                        region=region_name, secure=SSL_ENABLE)
    LOG.debug(f'Connected to S3: {minio_address}.')
    # List all object paths in bucket that begin with my-prefixname.
    objects = minioClient.list_objects_v2(bucket_name, recursive=True)
    object_list = [obj.object_name for obj in objects]
    assert str(file_id) in object_list, f"Could not find the file just uploaded! | FAIL | "
    LOG.info(f"Found the file uploaded to inbox as {file_id} in S3Storage. | PASS |")
    all_objects = minioClient.list_objects(bucket_name, recursive=True)
    LOG.debug("All the files in Lega bucket: ")
    for obj in all_objects:
        LOG.debug(f'Found ingested file: {obj.object_name} of size: {obj.size}.')
