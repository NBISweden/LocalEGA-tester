from setuptools import setup, find_packages

setup(
    name='lega_tester',
    version='0.4.2',
    packages=find_packages(),
    py_modules=['lega_tester'],
    include_package_data=True,
    project_urls={
        'Source': 'https://github.com/neicnordic/LocalEGA-tester',
    },
    description='LocalEGA end to end tester script.',
    author='LocalEGA Developers',
    install_requires=[
        'cryptography',
        'PGPy',
        'pika',
        'paramiko',
        'boto3',
        'PyYAML',
        'requests',
        'psycopg2-binary',
        'tenacity',
        'crypt4gh @ git+https://github.com/EGA-archive/crypt4gh.git@v1.1',
    ],
    entry_points={
        'console_scripts': [
            'legatest=lega_tester.test:main',
            'legaenc=lega_tester.test:enc_file'
        ]
    },
    package_data={'': ['config.yaml']},
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
