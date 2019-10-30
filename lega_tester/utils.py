import os
import logging
import requests
import filecmp
from urllib.parse import urlparse


FORMAT = '[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s] (L:%(lineno)s) %(funcName)s: %(message)s'
logging.basicConfig(format=FORMAT, datefmt='%Y-%m-%d %H:%M:%S')
LOG = logging.getLogger(__name__)
# By default the logging level would be INFO
log_level = os.environ.get('DEFAULT_LOG', 'INFO').upper()
LOG.setLevel(log_level)


def strip_url_scheme(url):
    """Remove scheme from url.

    Used to remove scheme from S3 address.
    """
    parsed = urlparse(url)
    scheme = "%s://" % parsed.scheme
    return parsed.geturl().replace(scheme, '', 1)


def download_to_file(root_ca, service, payload, output, headers=None):
    """Download file in chunks."""
    with requests.get(service, params=payload, headers=headers,
                      verify=(root_ca), stream=True) as r:
        LOG.debug(f'Download url is: {r.url}')
        assert r.status_code == 200, f'We got a status that is not OK {r.status_code} | FAIL |'
        with open(output, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)

    LOG.info(f"File downloaded from {service}. | PASS |")
    LOG.debug(f'write content to {output}')
    return output


def compare_files(service, downloaded_file, used_file):
    """Compare Downloaded file with original."""
    LOG.debug(f'Comparing downloaded via {service} file with original file ...')
    # comparing content of the files
    assert filecmp.cmp(downloaded_file, used_file, shallow=False), 'Files are not equal. | FAIL | '
    # The low level alternative would be:
    # with open(res_file) as f1:
    #     with open(used_file) as f2:
    #         if f1.read() == f2.read():
    #             pass
    LOG.info(f'{service} Downloaded file is equal to the original file. | PASS |')
    if os.path.isfile(downloaded_file):
        os.remove(downloaded_file)
    else:
        LOG.error(f"Error: %s file not found {downloaded_file}")
