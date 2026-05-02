"""Compatibility package exposing the legacy ``nodus`` namespace."""

from __future__ import annotations

import os
import sys
from importlib.machinery import PathFinder


def _installed_nodus_search_path() -> list[str]:
    package_dir = os.path.abspath(os.path.dirname(__file__))
    aindy_dir = os.path.dirname(package_dir)
    root_dir = os.path.dirname(aindy_dir)
    blocked = {package_dir, aindy_dir, root_dir}
    return [
        path
        for path in sys.path
        if os.path.abspath(path or os.getcwd()) not in blocked
    ]


if __name__ == "nodus":
    _spec = PathFinder.find_spec("nodus", _installed_nodus_search_path())
    if _spec and _spec.submodule_search_locations:
        __path__ = list(_spec.submodule_search_locations)
        __file__ = _spec.origin or __file__
        if __spec__ is not None:
            __spec__.submodule_search_locations = _spec.submodule_search_locations
