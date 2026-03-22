from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_task_list_scopes_by_user():
    src = _read("routes/task_router.py")
    assert "Task.user_id" in src or "task_services.Task.user_id" in src, (
        "tasks list endpoint must filter by user_id"
    )
    assert "current_user" in src, "tasks list endpoint must reference current_user"


def test_leadgen_list_scopes_by_user():
    src = _read("routes/leadgen_router.py")
    assert "LeadGenResult.user_id" in src, "leadgen list must filter by user_id"
    assert "current_user" in src, "leadgen list must reference current_user"


def test_bridge_nodes_scoped_by_user():
    src = _read("routes/bridge_router.py")
    assert "find_by_tags" in src and "current_user" in src, (
        "bridge /nodes should scope by current_user"
    )
    assert "user_id=str(current_user[\"sub\"])" in src, (
        "bridge /nodes should pass user_id to DAO"
    )


def test_bridge_link_ownership_check():
    src = _read("routes/bridge_router.py")
    assert "Cannot link nodes you do not own" in src, (
        "bridge /link must enforce ownership checks"
    )
