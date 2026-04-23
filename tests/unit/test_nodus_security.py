from __future__ import annotations

import pytest

from AINDY.runtime.nodus_security import NodusSecurityError, validate_nodus_source


def test_getattr_exec_bypass():
    with pytest.raises(NodusSecurityError):
        validate_nodus_source("getattr(__builtins__, 'exec')('x')")


def test_builtins_dunder_access():
    with pytest.raises(NodusSecurityError):
        validate_nodus_source("x = __builtins__['open']")


def test_open_with_spaces():
    with pytest.raises(NodusSecurityError):
        validate_nodus_source("open  ('file.txt')")


def test_import_still_blocked():
    with pytest.raises(NodusSecurityError):
        validate_nodus_source("import os")


def test_valid_script_passes():
    validate_nodus_source("memory.recall(['task'], 5)")
