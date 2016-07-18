'''
Created on 1 Jul 2016

@author: James Bailey
'''

import os
import logging

from boto.s3.connection import S3Connection
from pipeline.storage import PipelineMixin
from pipeline.packager import Packager
from storages.backends.s3boto import S3BotoStorage

from collections import OrderedDict

from django.core.files.storage import FileSystemStorage, get_storage_class
from django.conf import settings
from django.contrib.staticfiles.storage import CachedFilesMixin, \
    CachedStaticFilesStorage, StaticFilesStorage
from django.contrib.staticfiles.finders import AppDirectoriesFinder, \
    FileSystemFinder
from django.contrib.staticfiles.utils import matches_patterns
from django.utils import six
from django.utils.text import slugify
from django.utils.functional import LazyObject


def cleanfilename(filename):
    """
    Make sure filenames only contain a-z characters.
    The easiest way to do this is to slugify the filenames.
    """
    stripped_filename, file_extension = os.path.splitext(filename)
    # slugify() expects a unicode object.
    stripped_filename = slugify(unicode(stripped_filename))
    return '%s%s' % (stripped_filename, file_extension)


class OverwriteFilesystemStorage(FileSystemStorage):
    """
    Storage class that overwrites the target file if it exists.

    Default django behaviour is to append an underscore to the uploaded
    filename if it exists. We want to be able to force a filename on upload.

    Note that this implementation is both stupid and naive in that it doesn't
    log any messages to let you know it's overwritten an existing file. It also
    ignores any potential race conditions that arise when more than 1 user
    tries to access the same file.
    """
    def _save(self, name, content):
        full_path = self.path(name)
        logging.debug(full_path)

        directory = os.path.dirname(full_path)
        if not os.path.exists(directory):
            os.makedirs(directory)
        elif not os.path.isdir(directory):
            raise IOError("%s exists and is not a directory." % directory)

        fp = open(full_path, 'wb')
        for chunk in content.chunks():
            fp.write(chunk)
        fp.close()

        if settings.FILE_UPLOAD_PERMISSIONS is not None:
            os.chmod(full_path, settings.FILE_UPLOAD_PERMISSIONS)

        return name

    def get_available_name(self, name):
        return name


# This Proxy class is to allow the use of a Fake S3:
# https://github.com/philroche/fake-s3
class S3ProxyConnection(S3Connection):

    def __init__(self, *args, **kwargs):
        if getattr(settings, 'PROXY_S3', False):
            kwargs['host'] = 'localhost'
            kwargs['port'] = 4567
            kwargs['is_secure'] = False
            kwargs['calling_format'] = \
                'boto.s3.connection.OrdinaryCallingFormat'
        super(S3ProxyConnection, self).__init__(*args, **kwargs)


class S3PipelineCachedStorage(PipelineMixin, CachedFilesMixin, S3BotoStorage):
    pass


class S3PipelineStorage(PipelineMixin, S3BotoStorage):
    pass


# Django-storages can only use one S3 bucket, and has been resistant to using
# more than one bucket (cf.
# https://bitbucket.org/david/django-storages/issue/93/s3boto-seperate-buckets-for-static-and
# )
# So instead 'subclass' the S3BotoStorage to pass in the configured settings.
# The developer of django storages recommends this sort of approach.
#
# Copied from this https://gist.github.com/antonagestam/6075199
class S3StaticStorage(S3PipelineCachedStorage):
    def __init__(self, *args, **kwargs):
        kwargs['bucket'] = settings.AWS_STATIC_BUCKET_NAME
        kwargs['connection_class'] = S3ProxyConnection
        if (getattr(settings, 'CLOUDFRONT_ENABLED', False) and
            getattr(settings, 'CLOUDFRONT_CUSTOM_STATIC_DOMAIN', None)):
            kwargs['custom_domain'] = settings.CLOUDFRONT_CUSTOM_STATIC_DOMAIN
        super(S3StaticStorage, self).__init__(*args, **kwargs)


# Django-storages S3BotoStorage will overwrite the filename (cf.
# settings.AWS_S3_FILE_OVERWRITE)
class S3MediaStorage(S3PipelineStorage):
    def __init__(self, *args, **kwargs):
        kwargs['bucket'] = settings.AWS_MEDIA_BUCKET_NAME
        kwargs['connection_class'] = S3ProxyConnection
        if (getattr(settings, 'CLOUDFRONT_ENABLED', False) and
            getattr(settings, 'CLOUDFRONT_CUSTOM_MEDIA_DOMAIN', None)):
            kwargs['custom_domain'] = settings.CLOUDFRONT_CUSTOM_MEDIA_DOMAIN
        super(S3MediaStorage, self).__init__(*args, **kwargs)


# May be necessary to put this arg in as well (&static aswell):
# see gist above
# custom_domain=settings.AWS_MEDIA_CUSTOM_DOMAIN)


"""
AppDirectoriesFinder and FileSystemFinder below were subclassed so that
they would call get_files below and be able to ignore sub directories like
'img/venues/seatmaps'. This was not possible before
"""


def get_files(storage, ignore_patterns=None, location=''):
    """
    Recursively walk the storage directories yielding the paths
    of all files that should be copied.
    """
    if ignore_patterns is None:
        ignore_patterns = []
    directories, files = storage.listdir(location)
    for fn in files:
        if matches_patterns(fn, ignore_patterns) or (
                location and matches_patterns(os.path.join(location, fn),
                                              ignore_patterns)):
            continue
        if location:
            fn = os.path.join(location, fn)
        yield fn
    for dir in directories:
        if matches_patterns(dir, ignore_patterns) or (
                location and matches_patterns(os.path.join(location, dir),
                                              ignore_patterns)):
            continue
        if location:
            dir = os.path.join(location, dir)
        for fn in get_files(storage, ignore_patterns, dir):
            yield fn


class AppDirectoriesFinder(AppDirectoriesFinder):
    """
    Like AppDirectoriesFinder, but doesn't return any additional ignored
    patterns.
    """
    def list(self, ignore_patterns):
        """
        List all files in all app storages.
        """
        for storage in six.itervalues(self.storages):
            if storage.exists(''):  # check if storage location exists
                for path in get_files(storage, ignore_patterns):
                    yield path, storage


class FileSystemFinder(FileSystemFinder):
    """
    Like FileSystemFinder, but doesn't return any additional ignored patterns
    """
    def list(self, ignore_patterns):
        """
        List all files in all locations.
        """
        for _prefix, root in self.locations:
            storage = self.storages[root]
            for path in get_files(storage, ignore_patterns):
                yield path, storage


class DummyPipelineMixin(PipelineMixin):

    def post_process(self, paths, dry_run=False, **options):
        if dry_run:
            return

        packager = Packager(storage=self)
        for _abs_path, rel_path in paths:
            files_to_process = OrderedDict()
            files_to_process[rel_path] = (self, rel_path)
            for package_name in packager.packages['css']:
                package = packager.package_for('css', package_name)
                output_file = package.output_filename

                if rel_path in package.paths:
                    if self.packing:
                        packager.pack_stylesheets(package)
                    files_to_process[output_file] = (self, output_file)
                    yield output_file, output_file, True
            for package_name in packager.packages['js']:
                package = packager.package_for('js', package_name)
                output_file = package.output_filename
                if rel_path in package.paths:
                    if self.packing:
                        packager.pack_javascripts(package)
                    files_to_process[output_file] = (self, output_file)
                    yield output_file, output_file, True

            super_class = super(PipelineMixin, self)

            if hasattr(super_class, 'post_process'):
                for name, hashed_name, processed in super_class.post_process(
                        files_to_process.copy(), dry_run, **options):
                    yield name, hashed_name, processed


class DummyS3PipelineCachedStorage(DummyPipelineMixin,
                                   CachedFilesMixin,
                                   S3BotoStorage):
    pass


class DummyPipelineStorage(DummyPipelineMixin, StaticFilesStorage):
    pass


class DummyPipelineCachedStorage(DummyPipelineMixin, CachedStaticFilesStorage):
    pass


DummyS3StaticStorage = lambda: DummyS3PipelineCachedStorage(
    bucket=settings.AWS_STATIC_BUCKET_NAME,
    connection_class=S3ProxyConnection,
)


class DummyStorage(LazyObject):
    def _setup(self):
        dummyStorage = ''
        if settings.STATICFILES_STORAGE == 'pipeline.storage.PipelineCachedStorage':
            dummyStorage = 'deploy_utils.storage.DummyPipelineCachedStorage'
        elif settings.STATICFILES_STORAGE == 'pipeline.storage.PipelineStorage':
            dummyStorage = 'deploy_utils.storage.DummyPipelineStorage'
        elif settings.STATICFILES_STORAGE == 'deploy_utils.storage.S3StaticStorage':
            dummyStorage = 'deploy_utils.storage.DummyS3StaticStorage'

        self._wrapped = get_storage_class(dummyStorage)()



