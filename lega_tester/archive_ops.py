import os
import logging
from tenacity import retry, stop_after_delay, wait_fixed
import boto3
import botocore

FORMAT = '[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s] (L:%(lineno)s) %(funcName)s: %(message)s'
logging.basicConfig(format=FORMAT, datefmt='%Y-%m-%d %H:%M:%S')
LOG = logging.getLogger(__name__)
# By default the logging level would be INFO
log_level = os.environ.get('DEFAULT_LOG', 'INFO').upper()
LOG.setLevel(log_level)


@retry(wait=wait_fixed(2), stop=(stop_after_delay(300)))
def check_file_exists(address, bucket_name, region_name, file_id, access, secret, ssl_enable, root_ca):
    """Check if there is a file inside s3."""
    s3 = boto3.resource('s3', endpoint_url=address,
                        use_ssl=ssl_enable, aws_access_key_id=access,
                        aws_secret_access_key=secret,
                        config=boto3.session.Config(signature_version='s3v4'),
                        region_name=region_name,
                        verify=root_ca)
    LOG.debug(f'Connected to S3: {address}.')
    try:
        s3.Object(bucket_name, str(file_id)).load()
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "404":
            raise Exception("Could not find the file just uploaded! | FAIL | ")
        else:
            # Something else has gone wrong.
            raise Exception("Oh No, something failed! | FAIL | ")
    else:
        LOG.info(f"Found the file uploaded to inbox as {file_id} in S3Storage. | PASS |")


def list_s3_objects(address, bucket_name, region_name, file_id, access, secret, ssl_enable, root_ca):
    """List all the objects in a bucket."""
    s3 = boto3.resource('s3', endpoint_url=address,
                        use_ssl=ssl_enable, aws_access_key_id=access,
                        aws_secret_access_key=secret,
                        config=boto3.session.Config(signature_version='s3v4'),
                        region_name=region_name,
                        verify=root_ca)
    LOG.debug(f'Connected to S3: {address}.')
    my_bucket = s3.Bucket(bucket_name)
    for obj in my_bucket.objects.all():
        LOG.debug(f'Found ingested file: {obj.key} of size: {obj.size}.')
