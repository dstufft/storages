from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals


import os
import re
import sys
import urllib


__all__ = ("abspath", "filepath_to_uri", "get_valid_filename", "import_module", "safe_join")


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


def _resolve_name(name, package, level):
    """
    Return the absolute name of the module to be imported.
    """
    if not hasattr(package, "rindex"):
        raise ValueError("'package' not set to a string")

    dot = len(package)
    for x in xrange(level, 1, -1):
        try:
            dot = package.rindex('.', 0, dot)
        except ValueError:
            raise ValueError("attempted relative import beyond top-level "
                              "package")
    return "%s.%s" % (package[:dot], name)


def import_module(name, package=None):
    """
    Import a module.

    The 'package' argument is required when performing a relative import. It
    specifies the package to use as the anchor point from which to resolve the
    relative import to an absolute import.

    """
    if name.startswith("."):
        if not package:
            raise TypeError("relative imports require the 'package' argument")
        level = 0
        for character in name:
            if character != ".":
                break
            level += 1
        name = _resolve_name(name[level:], package, level)

    __import__(name)

    return sys.modules[name]
