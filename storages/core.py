from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals


import datetime
import errno
import itertools
import os
import urlparse

from . import locks
from .exceptions import SuspiciousOperation
from .utils import abspath, filepath_to_uri, get_valid_filename, safe_join


__all__ = ("Storage", "FileSystemStorage")


def chunks(f, chunk_size=None):
    """
    Read the file and yield chucks of ``chunk_size`` bytes.
    """
    if not chunk_size:
        chunk_size = 64 * 2 ** 10

    if hasattr(f, "seek"):
        f.seek(0)

    while True:
        data = f.read(chunk_size)
        if not data:
            break
        yield data


class Storage(object):
    """
    A base storage class, providing some default behaviors that all other
    storage systems can inherit or override, as necessary.
    """

    # The following methods represent a public interface to private methods.
    # These shouldn't be overridden by subclasses unless absolutely necessary.

    def open(self, name, mode=None):
        """
        Retrieves the specified file from storage.
        """
        if mode is None:
            mode = "rb"

        return self._open(name, mode)

    def save(self, name, content):
        """
        Saves new content to the file specified by name. The content should be a
        proper File object, ready to be read from the beginning.
        """
        # Get the proper name for the file, as it will actually be saved.
        if name is None:
            name = content.name

        name = self.get_available_name(name)
        name = self._save(name, content)

        # Store filenames with forward slashes, even on Windows
        return name.replace("\\", "/")

    # These methods are part of the public API, with default implementations.

    def get_valid_name(self, name):
        """
        Returns a filename, based on the provided filename, that's suitable for
        use in the target storage system.
        """
        return get_valid_filename(name)

    def get_available_name(self, name):
        """
        Returns a filename that's free on the target storage system, and
        available for new content to be written to.
        """
        dir_name, file_name = os.path.split(name)
        file_root, file_ext = os.path.splitext(file_name)
        # If the filename already exists, add an underscore and a number (before
        # the file extension, if one exists) to the filename until the generated
        # filename doesn't exist.
        count = itertools.count(1)
        while self.exists(name):
            # file_ext includes the dot.
            name = os.path.join(dir_name, "%s_%s%s" % (file_root, next(count), file_ext))

        return name

    def path(self, name):
        """
        Returns a local filesystem path where the file can be retrieved using
        Python's built-in open() function. Storage systems that can't be
        accessed using open() should *not* implement this method.
        """
        raise NotImplementedError("This backend doesn't support absolute paths.")

    # The following methods form the public API for storage systems, but with
    # no default implementations. Subclasses must implement *all* of these.

    def delete(self, name):
        """
        Deletes the specified file from the storage system.
        """
        raise NotImplementedError()

    def exists(self, name):
        """
        Returns True if a file referenced by the given name already exists in the
        storage system, or False if the name is available for a new file.
        """
        raise NotImplementedError()

    def listdir(self, path):
        """
        Lists the contents of the specified path, returning a 2-tuple of lists;
        the first item being directories, the second item being files.
        """
        raise NotImplementedError()

    def size(self, name):
        """
        Returns the total size, in bytes, of the file specified by name.
        """
        raise NotImplementedError()

    def url(self, name):
        """
        Returns an absolute URL where the file's contents can be accessed
        directly by a Web browser.
        """
        raise NotImplementedError()

    def accessed_time(self, name):
        """
        Returns the last accessed time (as datetime object) of the file
        specified by name.
        """
        raise NotImplementedError()

    def created_time(self, name):
        """
        Returns the creation time (as datetime object) of the file
        specified by name.
        """
        raise NotImplementedError()

    def modified_time(self, name):
        """
        Returns the last modified time (as datetime object) of the file
        specified by name.
        """
        raise NotImplementedError()


class FileSystemStorage(Storage):
    """
    Standard filesystem storage
    """

    def __init__(self, location=None, base_uri=None, default_permissions=None, chunk_size=None):
        self.base_location = location
        self.location = abspath(self.base_location)
        self.base_uri = base_uri
        self.default_permissions = default_permissions
        self.chunk_size = chunk_size

    def _open(self, name, mode=None):
        if mode is None:
            mode = "rb"

        return open(self.path(name), mode)

    def _save(self, name, content):
        full_path = self.path(name)

        # Create any intermediate directories that do not exist.
        # Note that there is a race between os.path.exists and os.makedirs:
        # if os.makedirs fails with EEXIST, the directory was created
        # concurrently, and we can continue normally. Refs #16082.
        directory = os.path.dirname(full_path)
        if not os.path.exists(directory):
            try:
                os.makedirs(directory)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise
        if not os.path.isdir(directory):
            raise IOError("%s exists and is not a directory." % directory)

        # There's a potential race condition between get_available_name and
        # saving the file; it's possible that two threads might return the
        # same name, at which point all sorts of fun happens. So we need to
        # try to create the file, but if it already exists we have to go back
        # to get_available_name() and try again.

        while True:
            try:
                # This fun binary flag incantation makes os.open throw an
                # OSError if the file already exists before we open it.
                fd = os.open(full_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0))
                try:
                    locks.lock(fd, locks.LOCK_EX)
                    for chunk in chunks(content, chunk_size=self.chunk_size):
                        os.write(fd, chunk)
                finally:
                    locks.unlock(fd)
                    os.close(fd)
            except OSError as e:
                if e.errno == errno.EEXIST:
                    # Ooops, the file exists. We need a new file name.
                    name = self.get_available_name(name)
                    full_path = self.path(name)
                else:
                    raise
            else:
                # OK, the file save worked. Break out of the loop.
                break

        if self.default_permissions is not None:
            os.chmod(full_path, self.default_permissions)

        return name

    def delete(self, name):
        name = self.path(name)
        # If the file exists, delete it from the filesystem.
        # Note that there is a race between os.path.exists and os.remove:
        # if os.remove fails with ENOENT, the file was removed
        # concurrently, and we can continue normally.
        if os.path.exists(name):
            try:
                os.remove(name)
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise

    def exists(self, name):
        return os.path.exists(self.path(name))

    def listdir(self, path):
        path = self.path(path)
        directories, files = [], []
        for entry in os.listdir(path):
            if os.path.isdir(os.path.join(path, entry)):
                directories.append(entry)
            else:
                files.append(entry)
        return directories, files

    def path(self, name):
        try:
            path = safe_join(self.location, name)
        except ValueError:
            raise SuspiciousOperation("Attempted access to '%s' denied." % name)
        return os.path.normpath(path)

    def size(self, name):
        return os.path.getsize(self.path(name))

    def url(self, name):
        if self.base_uri is None:
            raise ValueError("This file is not accessible via a URL.")
        return urlparse.urljoin(self.base_uri, filepath_to_uri(name))

    def accessed_time(self, name):
        return datetime.fromtimestamp(os.path.getatime(self.path(name)))

    def created_time(self, name):
        return datetime.fromtimestamp(os.path.getctime(self.path(name)))

    def modified_time(self, name):
        return datetime.fromtimestamp(os.path.getmtime(self.path(name)))
