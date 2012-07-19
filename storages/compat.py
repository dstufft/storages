from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

import sys

# -------
# Pythons
# -------

# Syntax sugar.
_ver = sys.version_info

#: Python 2.x?
is_py2 = (_ver[0] == 2)

#: Python 3.x?
is_py3 = (_ver[0] == 3)


if is_py2:
    import urlparse
else:
    import urllib.parse as urlparse
