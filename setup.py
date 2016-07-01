'''
Created on 1 Jul 2016

@author: James Bailey
'''

import os
from setuptools import find_packages, setup

with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as readme:
    README = readme.read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='django-deploy-utils',
    version='0.1',
    packages=find_packages(),
    include_package_data=True,
    license='GNU GPL',  # example license
    description='Tools to help with Django deployments.',
    long_description=README,
    url='https://www.example.com/',
    author='James Bailey',
    author_email='james.bailey@coras.io',
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Framework :: Django :: 1.9',  # replace "X.Y" as appropriate
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GPL License',  # example license
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        # Replace these appropriately if you are stuck on Python 2.
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
    install_requires=[
        "Django>=1.8",
        "django-pipeline-1.6.8",
        "pygit2==0.24.1",
        "boto==2.38.0",
        "django-storages-redux==1.3",
    ],
)
