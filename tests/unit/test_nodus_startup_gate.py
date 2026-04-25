from __future__ import annotations

import logging

import pytest


def test_nodus_gate_raises_in_prod_when_nodus_nodes_registered_and_vm_unavailable(monkeypatch):
    from AINDY import main
    import AINDY.runtime.flow_engine as flow_engine

    monkeypatch.setattr(main.settings, "ENV", "production")
    monkeypatch.setattr(
        flow_engine,
        "NODE_REGISTRY",
        {"nodus.execute": object(), "plain.node": object()},
    )
    monkeypatch.setattr(
        main,
        "_check_nodus_importable",
        lambda: (False, "NODUS_SOURCE_PATH is not set"),
    )

    with pytest.raises(RuntimeError, match="Registered nodes: \\['nodus.execute'\\]"):
        main._enforce_nodus_gate()


def test_nodus_gate_warns_in_dev_when_nodus_nodes_registered_and_vm_unavailable(monkeypatch, caplog):
    from AINDY import main
    import AINDY.runtime.flow_engine as flow_engine

    monkeypatch.setattr(main.settings, "ENV", "development")
    monkeypatch.setattr(
        flow_engine,
        "NODE_REGISTRY",
        {"nodus.execute": object(), "nodus.helper": object()},
    )
    monkeypatch.setattr(
        main,
        "_check_nodus_importable",
        lambda: (False, "NODUS_SOURCE_PATH is not set"),
    )

    with caplog.at_level(logging.WARNING):
        main._enforce_nodus_gate()

    assert "Registered nodes: ['nodus.execute', 'nodus.helper']" in caplog.text
    assert "Set NODUS_SOURCE_PATH" in caplog.text


def test_nodus_gate_allows_registered_nodus_nodes_when_vm_available(monkeypatch, caplog):
    from AINDY import main
    import AINDY.runtime.flow_engine as flow_engine

    monkeypatch.setattr(main.settings, "ENV", "production")
    monkeypatch.setattr(
        flow_engine,
        "NODE_REGISTRY",
        {"nodus.execute": object(), "nodus.record": object()},
    )
    monkeypatch.setattr(
        main,
        "_check_nodus_importable",
        lambda: (True, "C:/nodus"),
    )

    with caplog.at_level(logging.INFO):
        main._enforce_nodus_gate()

    assert "Nodus VM verified for 2 registered nodus.* node(s)." in caplog.text


def test_nodus_gate_skips_when_no_nodus_nodes_registered_and_vm_unavailable(monkeypatch, caplog):
    from AINDY import main
    import AINDY.runtime.flow_engine as flow_engine

    monkeypatch.setattr(main.settings, "ENV", "production")
    monkeypatch.setattr(
        flow_engine,
        "NODE_REGISTRY",
        {"plain.node": object(), "other.node": object()},
    )
    monkeypatch.setattr(
        main,
        "_check_nodus_importable",
        lambda: (False, "NODUS_SOURCE_PATH is not set"),
    )

    with caplog.at_level(logging.INFO):
        main._enforce_nodus_gate()

    assert "Nodus VM not available; no Nodus nodes registered, skipping." in caplog.text
