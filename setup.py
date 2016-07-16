# Always prefer setuptools over distutils
from setuptools import setup, find_packages
# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='gluent_eng',

    # Version should comply with PEP440
    version='2016.6.1',

    description='GLUENT_ENG: Collection of linux, hadoop and database tools by Gluent enginers',
    long_description=long_description,

    url='https://github.com/gluent/gluent-eng',

    maintainer='Maxym Kharchenko',
    maintainer_email='maxym@gluent.com',

    license='Apache License, Version 2.0',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 3 - Alpha',

        'Environment :: Console',

        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',

        'Operating System :: POSIX :: Linux',

        'Topic :: System :: Monitoring',
        'Topic :: Utilities',

        'License :: OSI Approved :: Apache Software License',

        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
    ],

    keywords='hadoop database monitor linux process logs autodiscovery monitoring multitail service',

    packages=find_packages(exclude=['contrib', 'docs', 'tests']),

    install_requires=['termcolor', 'pyyaml'],

    entry_points={
        'console_scripts': [
            'ptail=gluent_eng.command_line_ptail:main',
            'linux-service=gluent_eng.command_line_service:main',
        ],
    },
)
