from __future__ import annotations

import pytest

from AINDY.runtime.nodus_security import NodusSecurityError, validate_nodus_source


def test_valid_nodus_script_passes():
    """Valid Nodus JS-like syntax must not raise."""
    validate_nodus_source(
        """
let r = sys("sys.v1.memory.read", {"query": "test"})
set_state("count", r["data"]["count"])
emit("done", {"ok": true})
"""
    )


def test_empty_script_raises():
    with pytest.raises(NodusSecurityError, match="required"):
        validate_nodus_source("")


def test_python_import_raises():
    with pytest.raises(NodusSecurityError):
        validate_nodus_source('import os\nset_state("x", 1)')


def test_python_from_import_raises():
    with pytest.raises(NodusSecurityError):
        validate_nodus_source("from os import path")


def test_eval_raises():
    with pytest.raises(NodusSecurityError):
        validate_nodus_source('eval("malicious")')


def test_exec_raises():
    with pytest.raises(NodusSecurityError):
        validate_nodus_source('exec("malicious")')


def test_nodus_while_loop_does_not_raise():
    """JS-like while loop must not be rejected - it is valid Nodus syntax."""
    validate_nodus_source(
        """
let i = 0
while i < 10 {
    set_state("i", i)
    i = i + 1
}
"""
    )


def test_nodus_let_syntax_does_not_raise():
    """let declarations are valid Nodus syntax, not Python."""
    validate_nodus_source('let x = 1\nset_state("x", x)')


def test_script_length_limit():
    with pytest.raises(NodusSecurityError, match="length"):
        validate_nodus_source("x" * 12001)
