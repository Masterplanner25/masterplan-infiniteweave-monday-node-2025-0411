from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _imports_apps_bootstrap(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "apps.bootstrap":
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "apps.bootstrap":
                    return True
    return False


def test_runtime_health_and_startup_code_do_not_import_apps_bootstrap():
    runtime_files = (
        ROOT / "AINDY" / "main.py",
        ROOT / "AINDY" / "routes" / "health_router.py",
        ROOT / "AINDY" / "platform_layer" / "health_service.py",
    )

    leaking = [str(path.relative_to(ROOT)) for path in runtime_files if _imports_apps_bootstrap(path)]
    assert leaking == []
