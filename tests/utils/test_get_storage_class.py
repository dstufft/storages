import pytest

from storages import FileSystemStorage
from storages.utils import get_storage_class


def test_get_filesystem_storage():
    """
    get_storage_class returns the class for a storage backend name/path.
    """
    assert get_storage_class("storages.FileSystemStorage") is FileSystemStorage


def test_get_invalid_storage_module():
    """
    get_storage_class raises an error if the requested import don't exist.
    """
    with pytest.raises(ValueError):
        get_storage_class("NonExistingStorage")


def test_get_nonexisting_storage_class():
    """
    get_storage_class raises an error if the requested class don't exist.
    """
    with pytest.raises(AttributeError):
        get_storage_class("storages.NonExistingStorage")


def test_get_nonexisting_storage_module():
    """
    get_storage_class raises an error if the requested module don't exist.
    """
    # Error message may or may not be the fully qualified path.
    with pytest.raises(ImportError):
        get_storage_class("storages.non_existing.NonExistingStoage")
