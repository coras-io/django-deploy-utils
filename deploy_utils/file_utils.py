from __future__ import unicode_literals
__author__ = 'Philip Roche'

from django.core.files.base import ContentFile

from .storage import  DummyStorage


def copy_static_file(path, dest_path):
    """
    Attempt to copy ``path`` with storage
    """
    static_storage = DummyStorage()
    with open(path, "rb") as source_file:
        static_storage.save(dest_path, ContentFile(source_file.read()))


def post_process_static_file(path, rel_path, dry_run=False):
    static_storage = DummyStorage()
    if hasattr(static_storage, 'post_process'):
        processor = static_storage.post_process([(path, rel_path)], dry_run=dry_run)
        post_processed_files = []
        for original_path, processed_path, processed in processor:
            if processed:
                post_processed_files.append(original_path)


def get_changed_files_local(filelist):
    message = ''
    files_changed = []
    for file in filelist:
        files_changed.append(file)
    return message, files_changed
