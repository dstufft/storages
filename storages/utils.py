from __future__ import absolute_import
from __future__ import division


import os
import re
import urllib

from . import locks

try:
    from shutil import copystat
except ImportError:
    import stat

    def copystat(src, dst):
        """Copy all stat info (mode bits, atime and mtime) from src to dst"""
        st = os.stat(src)
        mode = stat.S_IMODE(st.st_mode)
        if hasattr(os, 'utime'):
            os.utime(dst, (st.st_atime, st.st_mtime))
        if hasattr(os, 'chmod'):
            os.chmod(dst, mode)


__all__ = ("abspath", "file_move_safe", "filepath_to_uri", "get_valid_filename", "safe_join")


def get_valid_filename(s):
    """
    Returns the given string converted to a string that can be used for a clean
    filename. Specifically, leading and trailing spaces are removed; other
    spaces are converted to underscores; and anything that is not a unicode
    alphanumeric, dash, underscore, or dot, is removed.
    >>> get_valid_filename("john's portrait in 2004.jpg")
    'johns_portrait_in_2004.jpg'
    """
    s = s.strip().replace(" ", "_")
    return re.sub(r"(?u)[^-\w.]", "", s)


# Define our own abspath function that can handle joining
# unicode paths to a current working directory that has non-ASCII
# characters in it.  This isn't necessary on Windows since the
# Windows version of abspath handles this correctly.  The Windows
# abspath also handles drive letters differently than the pure
# Python implementation, so it's best not to replace it.
if os.name == "nt":
    abspath = os.path.abspath
else:
    def abspath(path):
        """
        Version of os.path.abspath that uses the unicode representation
        of the current working directory, thus avoiding a UnicodeDecodeError
        in join when the cwd has non-ASCII characters.
        """
        if not os.path.isabs(path):
            path = os.path.join(os.getcwdu(), path)
        return os.path.normpath(path)


def _samefile(src, dst):
    # Macintosh, Unix.
    if hasattr(os.path, "samefile"):
        try:
            return os.path.samefile(src, dst)
        except OSError:
            return False

    # All other platforms: check for same pathname.
    return (os.path.normcase(os.path.abspath(src)) ==
            os.path.normcase(os.path.abspath(dst)))


def file_move_safe(old_file_name, new_file_name, chunk_size=1024 * 64, allow_overwrite=False):
    """
    Moves a file from one location to another in the safest way possible.

    First, tries ``os.rename``, which is simple but will break across filesystems.
    If that fails, streams manually from one file to another in pure Python.

    If the destination file exists and ``allow_overwrite`` is ``False``, this
    function will throw an ``IOError``.
    """

    # There's no reason to move if we don't have to.
    if _samefile(old_file_name, new_file_name):
        return

    try:
        os.rename(old_file_name, new_file_name)
        return
    except OSError:
        # This will happen with os.rename if moving to another filesystem
        # or when moving opened files on certain operating systems
        pass

    # first open the old file, so that it won't go away
    with open(old_file_name, 'rb') as old_file:
        # now open the new file, not forgetting allow_overwrite
        fd = os.open(new_file_name, os.O_WRONLY | os.O_CREAT | getattr(os, 'O_BINARY', 0) |
                                    (not allow_overwrite and os.O_EXCL or 0))
        try:
            locks.lock(fd, locks.LOCK_EX)
            current_chunk = None
            while current_chunk != '':
                current_chunk = old_file.read(chunk_size)
                os.write(fd, current_chunk)
        finally:
            locks.unlock(fd)
            os.close(fd)
    copystat(old_file_name, new_file_name)

    try:
        os.remove(old_file_name)
    except OSError as e:
        # Certain operating systems (Cygwin and Windows)
        # fail when deleting opened files, ignore it.  (For the
        # systems where this happens, temporary files will be auto-deleted
        # on close anyway.)
        if getattr(e, 'winerror', 0) != 32 and getattr(e, 'errno', 0) != 13:
            raise


def safe_join(base, *paths):
    """
    Joins one or more path components to the base path component intelligently.
    Returns a normalized, absolute version of the final path.

    The final path must be located inside of the base path component (otherwise
    a ValueError is raised).
    """
    base = base
    paths = [p for p in paths]
    final_path = abspath(os.path.join(base, *paths))
    base_path = abspath(base)
    base_path_len = len(base_path)

    # Ensure final_path starts with base_path (using normcase to ensure we
    # don't false-negative on case insensitive operating systems like Windows)
    # and that the next character after the final path is os.sep (or nothing,
    # in which case final_path must be equal to base_path).
    if not os.path.normcase(final_path).startswith(os.path.normcase(base_path)) \
       or final_path[base_path_len:base_path_len + 1] not in ("", os.path.sep):
        raise ValueError("The joined path (%s) is located outside of the base "
                         "path component (%s)" % (final_path, base_path))
    return final_path


def filepath_to_uri(path):
    """
    Convert an file system path to a URI portion that is suitable for
    inclusion in a URL.

    We are assuming input is either UTF-8 or unicode already.

    This method will encode certain chars that would normally be recognized as
    special chars for URIs.  Note that this method does not encode the '
    character, as it is a valid character within URIs.  See
    encodeURIComponent() JavaScript function for more details.

    Returns an ASCII string containing the encoded result.
    """
    if path is None:
        return path

    # I know about `os.sep` and `os.altsep` but I want to leave
    # some flexibility for hardcoding separators.
    return urllib.quote(path.replace("\\", "/"), safe=b"/~!*()'")
