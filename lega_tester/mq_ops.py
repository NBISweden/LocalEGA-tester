
import os
import pika
import json
import sys
import logging
import ssl
from pathlib import Path
from tenacity import retry, stop_after_delay, wait_fixed


FORMAT = '[%(asctime)s][%(name)s][%(process)d %(processName)s][%(levelname)-8s] (L:%(lineno)s) %(funcName)s: %(message)s'
logging.basicConfig(format=FORMAT, datefmt='%Y-%m-%d %H:%M:%S')
LOG = logging.getLogger(__name__)
# By default the logging level would be INFO
log_level = os.environ.get('DEFAULT_LOG', 'INFO').upper()
LOG.setLevel(log_level)


def submit_cega(protocol, address, user, vhost, message, routing_key, mq_password,
                correlation_id,
                root_ca, test_cert, test_key_file,
                port=5672, file_md5=None):
    """Submit message to CEGA along with."""
    mq_address = f'{protocol}://{user}:{mq_password}@{address}:{port}/{vhost}'

    try:
        LOG.debug(f'Connection address: {mq_address}')
        parameters = pika.URLParameters(mq_address)
        if protocol == 'amqps':
            context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS)  # Enforcing (highest) TLS version (so... 1.2?)

            context.check_hostname = False

            cacertfile = Path(root_ca)
            certfile = Path(test_cert)
            keyfile = Path(test_key_file)

            context.verify_mode = ssl.CERT_NONE
            if cacertfile.exists():
                context.verify_mode = ssl.CERT_REQUIRED
                context.load_verify_locations(cafile=str(cacertfile))

            if certfile.exists():
                assert(keyfile.exists())
                context.load_cert_chain(str(certfile), keyfile=str(keyfile))

            parameters.ssl_options = pika.SSLOptions(context=context, server_hostname=None)
            LOG.debug('Added SSL_OPTIONS for MQ connection.')
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.basic_publish(exchange='localega.v1', routing_key=routing_key,
                              body=json.dumps(message),
                              properties=pika.BasicProperties(correlation_id=correlation_id,
                                                              content_type='application/json',
                                                              delivery_mode=2))

        connection.close()
        LOG.debug(f'Message published to CentralEGA: {message}')
    except Exception as e:
        LOG.error(f'Something went wrong {e}')
        raise e


@retry(wait=wait_fixed(2), stop=(stop_after_delay(300)))  #noqa: C901
def get_corr(protocol, address, user, vhost, queue, filepath, mq_password,
             root_ca, test_cert, test_key_file,
             latest_message=True, port=5672):
    """Read all messages from a queue and fetches the correlation_id for the one with given path, if found."""
    mq_address = f'{protocol}://{user}:{mq_password}@{address}:{port}/{vhost}'
    LOG.debug(f'Connection address: {mq_address}')
    parameters = pika.URLParameters(mq_address)
    if protocol == 'amqps':
        context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS)  # Enforcing (highest) TLS version (so... 1.2?)

        context.check_hostname = False

        cacertfile = Path(root_ca)
        certfile = Path(test_cert)
        keyfile = Path(test_key_file)

        context.verify_mode = ssl.CERT_NONE
        if cacertfile.exists():
            context.verify_mode = ssl.CERT_REQUIRED
            context.load_verify_locations(cafile=str(cacertfile))

        if certfile.exists():
            assert(keyfile.exists())
            context.load_cert_chain(str(certfile), keyfile=str(keyfile))

        parameters.ssl_options = pika.SSLOptions(context=context, server_hostname=None)
        LOG.debug('Added SSL_OPTIONS for MQ connection.')
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    correlation_ids = []
    messages = set()
    while True:
        method_frame, props, body = channel.basic_get(queue=queue)

        if method_frame is None or props is None:
            LOG.debug(f'No message returned in {queue}')
            break

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
        except Exception as error:
            LOG.error(f'Something went wrong {error} in {queue}')
            pass

    # Second loop, nack the messages
    for message_id in messages:
        channel.basic_nack(delivery_tag=message_id)

    connection.close()

    if not correlation_ids:
        LOG.error(f'No correlation ids found for {queue}.')
        sys.exit(102)

    correlation_id = correlation_ids[0][0]
    if latest_message:
        message_id = -1  # message ids are positive
        for cid, mid in correlation_ids:
            if mid > message_id:
                correlation_id = cid
    LOG.debug(f'correlation_id: {correlation_id} in {queue}')
    return correlation_id


def purge_cega_mq(protocol, address, user, vhost, mq_password,
                  root_ca, test_cert, test_key_file,
                  port=5672):
    """."""
    queues = ['v1.files', 'v1.files.completed', 'v1.files.error', 'v1.files.inbox', 'v1.files.processing', 'v1.stableIDs']
    mq_address = f'{protocol}://{user}:{mq_password}@{address}:{port}/{vhost}'
    LOG.debug(f'Connection address: {mq_address}')
    parameters = pika.URLParameters(mq_address)
    if protocol == 'amqps':
        context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS)  # Enforcing (highest) TLS version (so... 1.2?)

        context.check_hostname = False

        cacertfile = Path(root_ca)
        certfile = Path(test_cert)
        keyfile = Path(test_key_file)

        context.verify_mode = ssl.CERT_NONE
        if cacertfile.exists():
            context.verify_mode = ssl.CERT_REQUIRED
            context.load_verify_locations(cafile=str(cacertfile))

        if certfile.exists():
            assert(keyfile.exists())
            context.load_cert_chain(str(certfile), keyfile=str(keyfile))

        parameters.ssl_options = pika.SSLOptions(context=context, server_hostname=None)
        LOG.debug('Added SSL_OPTIONS for MQ connection.')

    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    for queue in queues:
        try:
            channel.queue_purge(queue=queue)
            LOG.debug(f'Purged queue: {queue}')
        except Exception as error:
            LOG.error(f'Something went wrong {error}')
            pass

    connection.close()
