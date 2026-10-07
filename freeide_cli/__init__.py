"""Compatibility namespace for pre-rename imports.

Jetts-TUI's implementation lives in :mod:`jettstui`. Older plugins and
launchers may still import ``freeide_cli.*``; keep that import path working
without retaining a second copy of the source tree.
"""

import jettstui as _implementation

__path__ = _implementation.__path__
__version__ = _implementation.__version__
__release_date__ = _implementation.__release_date__


def __getattr__(name: str):
    return getattr(_implementation, name)
