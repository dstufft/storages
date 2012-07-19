from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

import datetime
import errno
import io
import os

import pytest

from storages import FileSystemStorage
from storages.exceptions import SuspiciousOperation


def test_emtpy_location():
    """
    Makes sure an exception is raised if the location is empty
    """
    storage = FileSystemStorage(location="")
    assert storage.base_location == ""
    assert storage.location == os.getcwd()


def test_file_access_options(tmpdir):
    """
    Standard file access options are available, and work as expected.
    """
    storage = FileSystemStorage(location=str(tmpdir))

    assert not storage.exists("storage_test")

    f = storage.open("storage_test", "w")
    f.write("storage contents")
    f.close()

    assert storage.exists("storage_test")

    f = storage.open("storage_test", "r")
    assert f.read() == "storage contents"
    f.close()

    storage.delete("storage_test")
    assert not storage.exists("storage_test")


def test_file_accessed_time(tmpdir):
    """
    File storage returns a Datetime object for the last accessed time of
    a file.
    """
    storage = FileSystemStorage(location=str(tmpdir))

    assert not storage.exists("test.file")

    f = io.StringIO("custom contents")
    f_name = storage.save("test.file", f)
    atime = storage.accessed_time(f_name)

    assert atime == datetime.datetime.fromtimestamp(os.path.getatime(storage.path(f_name)))
    assert datetime.datetime.now() - storage.accessed_time(f_name) < datetime.timedelta(seconds=2)


def test_file_created_time(tmpdir):
    """
    File storage returns a Datetime object for the creation time of
    a file.
    """
    storage = FileSystemStorage(location=str(tmpdir))

    assert not storage.exists("test.file")

    f = io.StringIO("custom contents")
    f_name = storage.save("test.file", f)
    ctime = storage.created_time(f_name)

    assert ctime == datetime.datetime.fromtimestamp(os.path.getctime(storage.path(f_name)))
    assert datetime.datetime.now() - storage.created_time(f_name) < datetime.timedelta(seconds=2)


def test_file_modified_time(tmpdir):
    """
    File storage returns a Datetime object for the last modified time of
    a file.
    """
    storage = FileSystemStorage(location=str(tmpdir))

    assert not storage.exists("test.file")

    f = io.StringIO("custom contents")
    f_name = storage.save("test.file", f)
    mtime = storage.modified_time(f_name)

    assert mtime == datetime.datetime.fromtimestamp(os.path.getmtime(storage.path(f_name)))
    assert datetime.datetime.now() - storage.modified_time(f_name) < datetime.timedelta(seconds=2)


def test_file_save_without_name(tmpdir):
    """
    File storage extracts the filename from the content object if no
    name is given explicitly.
    """
    storage = FileSystemStorage(location=str(tmpdir))

    assert not storage.exists("test.file")

    class NamedStringIO(io.StringIO):
        name = "test.file"

    f = NamedStringIO("custom contents")

    storage_f_name = storage.save(None, f)

    assert storage_f_name == f.name
    assert os.path.exists(os.path.join(str(tmpdir), f.name))


def test_file_save_with_path(tmpdir):
    """
    Saving a pathname should create intermediate directories as necessary.
    """
    storage = FileSystemStorage(location=str(tmpdir))

    assert not storage.exists("path/to")

    storage.save("path/to/test.file", io.StringIO("file saved with path"))

    assert storage.exists("path/to")
    assert storage.open("path/to/test.file").read() == "file saved with path"
    assert os.path.exists(os.path.join(str(tmpdir), "path", "to", "test.file"))


def test_file_path(tmpdir):
    """
    File storage returns the full path of a file
    """
    storage = FileSystemStorage(location=str(tmpdir))

    assert not storage.exists("test.file")

    f = io.StringIO("custom contents")
    f_name = storage.save("test.file", f)

    assert storage.path(f_name) == os.path.join(str(tmpdir), f_name)


def test_file_uri(tmpdir):
    """
    File storage returns a url to access a given file from the Web.
    """
    storage = FileSystemStorage(location=str(tmpdir), base_uri="/test_media_url/")

    assert storage.uri("test.file") == "".join([storage.base_uri, "test.file"])

    # should encode special chars except ~!*()'
    # like encodeURIComponent() JavaScript function do
    assert storage.uri(r"""~!*()'@#$%^&*abc`+ =.file""") == """/test_media_url/~!*()'%40%23%24%25%5E%26*abc%60%2B%20%3D.file"""

    # should translate os path separator(s) to the url path separator
    assert storage.uri("""a/b\\c.file""") == """/test_media_url/a/b/c.file"""

    storage.base_uri = None

    with pytest.raises(ValueError):
        storage.uri("test.file")


def test_listdir(tmpdir):
    """
    File storage returns a tuple containing directories and files.
    """
    storage = FileSystemStorage(location=str(tmpdir))

    assert not storage.exists("storage_test_1")
    assert not storage.exists("storage_test_2")
    assert not storage.exists("storage_dir_1")

    storage.save("storage_test_1", io.StringIO("custom content"))
    storage.save("storage_test_2", io.StringIO("custom content"))

    os.mkdir(os.path.join(str(tmpdir), 'storage_dir_1'))

    dirs, files = storage.listdir("")

    assert set(dirs) == set(["storage_dir_1"])
    assert set(files) == set(["storage_test_1", "storage_test_2"])


def test_file_storage_prevents_directory_traversal(tmpdir):
    """
    File storage prevents directory traversal (files can only be accessed if
    they're below the storage location).
    """
    storage = FileSystemStorage(location=str(tmpdir))

    with pytest.raises(SuspiciousOperation):
        storage.exists("..")

    with pytest.raises(SuspiciousOperation):
        storage.exists("/etc/passwd")


def test_file_storage_preserves_filename_case(tmpdir):
    """
    The storage backend should preserve case of filenames.
    """
    storage = FileSystemStorage(location=str(tmpdir))

    f = storage.open("CaSe_SeNsItIvE", "w")
    f.write("storage contents")
    f.close()

    assert os.path.join(str(tmpdir), "CaSe_SeNsItIvE") == storage.path("CaSe_SeNsItIvE")


def test_makedirs_race_handling(tmpdir, monkeypatch):
    """
    File storage should be robust against directory creation race conditions.
    """
    real_makedirs = os.makedirs

    # Monkey-patch os.makedirs, to simulate a normal call, a raced call,
    # and an error.
    def fake_makedirs(path):
        if path == os.path.join(str(tmpdir), "normal"):
            real_makedirs(path)
        elif path == os.path.join(str(tmpdir), "raced"):
            real_makedirs(path)
            raise OSError(errno.EEXIST, "simulated EEXIST")
        elif path == os.path.join(str(tmpdir), "error"):
            raise OSError(errno.EACCES, "simulated EACCES")
        else:
            pytest.fail("unexpected argument %r" % path)

    monkeypatch.setattr(os, "makedirs", fake_makedirs)

    storage = FileSystemStorage(location=str(tmpdir))

    storage.save("normal/test.file", io.StringIO("saved normally"))
    assert storage.open("normal/test.file").read() == "saved normally"

    storage.save("raced/test.file", io.StringIO("saved with race"))
    assert storage.open("raced/test.file").read() == "saved with race"

    # Check that OSErrors aside from EEXIST are still raised.
    with pytest.raises(OSError):
        storage.save("error/test.file", io.StringIO("not saved"))


def test_remove_race_handling(tmpdir, monkeypatch):
    """
    File storage should be robust against file removal race conditions.
    """
    real_remove = os.remove

    # Monkey-patch os.remove, to simulate a normal call, a raced call,
    # and an error.
    def fake_remove(path):
        if path == os.path.join(str(tmpdir), "normal.file"):
            real_remove(path)
        elif path == os.path.join(str(tmpdir), "raced.file"):
            real_remove(path)
            raise OSError(errno.ENOENT, "simulated ENOENT")
        elif path == os.path.join(str(tmpdir), "error.file"):
            raise OSError(errno.EACCES, "simulated EACCES")
        else:
            pytest.fail("unexpected argument %r" % path)

    monkeypatch.setattr(os, "remove", fake_remove)

    storage = FileSystemStorage(location=str(tmpdir))

    storage.save("normal.file", io.StringIO("delete normally"))
    storage.delete("normal.file")

    assert not storage.exists("normal.file")

    storage.save("raced.file", io.StringIO("delete with race"))
    storage.delete("raced.file")

    assert not storage.exists("normal.file")

    # Check that OSErrors aside from ENOENT are still raised.
    storage.save("error.file", io.StringIO("delete with error"))

    with pytest.raises(OSError):
        storage.delete("error.file")
