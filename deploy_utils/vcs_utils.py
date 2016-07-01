from __future__ import unicode_literals

__author__ = 'Philip Roche'

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile


def get_changed_files_git(commit_id, path='../'):
    try:
        import pygit2
        repo = pygit2.Repository(path)
        commit = repo.revparse_single(commit_id)
        message = commit.message

        # Diff between specified parent and its immediate parent on the
        # current branch.
        # (See http://www.paulboxley.com/blog/2011/06/git-caret-and-tilde)
        diff = repo.diff(commit_id, '%s~1' % commit_id)
        files_changed = []
        for p in diff:
            delta = p.delta
            # TODO: Get rid of this tix-specific path
            changed_file_path = delta.new_file.path.replace('tix/', '')
            files_changed.append(changed_file_path)
        return message, files_changed
    except ImportError:
        raise Exception("Unable to proceed as pygit2 is not installed.")


def save_with_default_storage(abs_file_path, relative_file_path):

    with open(abs_file_path) as fp:
        default_storage.save(relative_file_path, ContentFile(fp.read()))
