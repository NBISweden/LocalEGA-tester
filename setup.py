from setuptools import setup, find_packages

setup(
    name='lega_test',
    version='0.2.0',
    packages=find_packages(),
    py_modules=['lega_test'],
    include_package_data=True,
    project_urls={
        'Source': 'https://github.com/NBISweden/LocalEGA-tester',
    },
    description='LocalEGA end to end tester script.',
    author='LocalEGA Developers',
    install_requires=[
        'cryptography',
        'PGPy==0.4.3',
        'pika',
        'paramiko',
        'minio',
        'PyYAML',
        'requests',
        'psycopg2-binary',
        'tenacity',
        'legacryptor @ git+https://github.com/neicnordic/LocalEGA-cryptor',
    ],
    entry_points={
        'console_scripts': [
            'legatest=lega_tester.test:main'
        ]
    },
    platforms='any',
    classifiers=[
        'Development Status :: 5 - Production/Stable',

        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Topic :: Software Development :: Testing',

        'License :: OSI Approved :: Apache Software License',

        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
)
