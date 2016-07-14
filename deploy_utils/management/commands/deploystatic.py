'''
Created on 21 May 2014

@author: philroche

python manage.py deploystatic --commit=3b282d9a07db7ab7e317944208b92cf66e1294c5
python manage.py deploystatic --file=media/css/all.css --file=media/js/feedback.js
'''

from optparse import make_option
import os
import six

from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.staticfiles.finders import get_finders

from deploy_utils.vcs_utils import get_changed_files_git
from deploy_utils.file_utils import get_changed_files_local, \
    post_process_static_file, copy_static_file


try:
    # For Python 2.x compatibility
    input = raw_input
except NameError:
    pass


def prompt(name, default=None):
    """
    Grab user input from command line.

    :param name: prompt text
    :param default: default value if no input provided.
    """

    prompt = name + (' [%s]' % default if default else '')
    prompt += ' ' if name.endswith('?') else ': '
    while True:
        rv = input(prompt)
        if rv:
            return rv
        if default is not None:
            return default


def to_bool(val, default=False, yes_choices=None, no_choices=None):
    if not isinstance(val, six.string_types):
        return bool(val)

    yes_choices = yes_choices or ('y', 'yes', '1', 'on', 'true', 't')
    no_choices = no_choices or ('n', 'no', '0', 'off', 'false', 'f')

    if val.lower() in yes_choices:
        return True
    elif val.lower() in no_choices:
        return False
    return default


def prompt_bool(name, default=False,
                yes_choices=('y', 'yes', '1', 'on', 'true', 't'),
                no_choices=('n', 'no', '0', 'off', 'false', 'f')):
    """
    Grabs user input from command line and converts to boolean
    value.

    :param name: prompt text
    :param default: default value if no input provided.
    :param yes_choices: default 'y', 'yes', '1', 'on', 'true', 't'
    :param no_choices: default 'n', 'no', '0', 'off', 'false', 'f'
    """

    while True:
        rv = prompt(name + '?', yes_choices[0] if default else no_choices[0])
        if not rv:
            return default
        rv = to_bool(rv, default=None, yes_choices=yes_choices,
                     no_choices=no_choices)
        if rv is not None:
            return rv


def get_static_file_path(abs_path):
    """
    Check if the given file path represents a static file, and if so return
    the corresponding relative path (i.e. relative to the static folder it
    belongs to); otherwise return None.
    """
    # First check if the file appears to be in one of the installed apps'
    # 'static' subdirectories
    # TODO: Need to also check if it's in one of STATICFILES_DIRS
    # TODO: Also need to handle npm-installed files; this might help:
    # https://github.com/kevin1024/django-npm

    static_dir = "{}static{}".format(os.path.sep, os.path.sep)
    index = abs_path.rfind(static_dir)
    if index != -1:
        # Path includes '/static/'; now check if it is actually is a static
        # file by seeing if any of our static file finders returns it
        rel_path = abs_path[index + len(static_dir):]
        for finder in get_finders():
            # If the given relative path is a static file, then one of our
            # finders should return the corresponding absolute path
            found_paths = finder.find(rel_path, all=True)
            if abs_path in found_paths:
                return rel_path

    # Return None to indicate that this is not a static file
    return None


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('-d', '--dry-run', action='store_true', dest='dry_run',
                    default=False, help='Do you want to do a dry run to " \
                        "list all the files without actually saving them?'),
        make_option('-c', '--commit', action='store', type="string",
                    dest='commit', default=None,
                    help='What revision/commit do you want to deploy?'),
        make_option('-p', '--path', action='store', type="string", dest='path',
            default=None, help='What is the path to the working copy?'),
        make_option('-f', '--file', action='append', type="string",
                    dest='filelist', default=[],
                    help='What media files do you want to deploy?'),
        make_option('--noinput', action='store_false', dest='interactive',
                    default=True, help='Tells the command to NOT prompt the " \
                            "user to confirm whether or not to proceed.'),
        )

    help = 'Management command to deploy static files to S3 (or similar) " \
        "using STATICFILES_STORAGE. First you must update your VCS then run " \
        "this command to sync your new theme files with S3'

    def handle(self, **options):
        commit = options.get('commit', None)
        filelist = options.get('filelist', [])
        dry_run = options.get('dry_run', False)
        path = options.get('path', None)
        verbosity = int(options.get('verbosity', 1))
        interactive = options.get('interactive', True)

        verbose_output = False
        if verbosity > 1:
            verbose_output = True

        vcs = False
        if len(filelist) == 0:
            vcs = True

        get_changed_files = get_changed_files_git

        if path == None:
            # Look in the parent directory
            path = '..'

        # check staticfiles and pipeline is actually being used
        if settings.STATICFILES_STORAGE not in (
            'deploy_utils.storage.S3StaticStorage',
            'pipeline.storage.PipelineCachedStorage',
            'pipeline.storage.PipelineStorage'):

            self.stdout.write("Looks like you are not using S3 storage or " \
                "pipeline for static files - as such there is no need to " \
                "deploy any static files.")
            return

        if vcs:
            if not commit:
                commit = prompt("What commit do you want to deploy?")
            message, files_changed = get_changed_files(commit, path)
        else:
            message, files_changed = get_changed_files_local(filelist)

        if not files_changed:
            if vcs:
                self.stdout.write("No files were changed in revision %s " \
                    "\n\n COMMIT MESSAGE: '%s'" % (commit, message))
            else:
                self.stdout.write("You must specify files to deploy")
            return

        # show message from revision and prompt to proceed
        if vcs:
            prompt_message = "Are you sure you want to deploy commit" \
                " %s\nCOMMIT MESSAGE: '%s' \nFILES CHANGED:" % (
                commit, message)
        else:
            prompt_message = "Are you sure you want to " \
                "deploy these files:"

        for file_changed in files_changed:
            prompt_message = prompt_message + '\n\t' + file_changed

        if interactive and not prompt_bool(prompt_message + '\n'):
            self.stdout.write('Deployment aborted')
            return

        # loop through all files and save each one using the default storage
        # (s3 is this case) if it is a static file
        for file_changed in files_changed:
            abs_path = os.path.join(os.path.abspath(path),
                                    file_changed)

            relative_path = get_static_file_path(abs_path)

            if verbose_output:
                self.stdout.write('file_changed = %s ' % file_changed)
                self.stdout.write('path = %s ' % path)
                self.stdout.write('abs_path = %s ' % abs_path)
                self.stdout.write('relative_path = %s ' % relative_path)

            if not relative_path:
                self.stdout.write('%s is _NOT_ a media/static file and will ' \
                    'not be deployed' % file_changed)
            elif not os.path.isfile(abs_path):  # check that the file exists
                self.stdout.write("%s doesn't exist locally so can't be " \
                                  "deployed" % abs_path)
            else:
                # this is a valid static file and we'll
                # post-process it now
                if not dry_run:
                    copy_static_file(abs_path, relative_path)
                    self.stdout.write('\tcopied %s ' % relative_path)
                    post_process_static_file(abs_path, relative_path)
                    self.stdout.write('\tprocessed %s ' % relative_path)
