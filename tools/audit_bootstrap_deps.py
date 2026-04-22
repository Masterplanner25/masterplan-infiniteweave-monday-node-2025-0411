import ast
import pathlib

root = pathlib.Path("apps")
apps = sorted(
    d.name for d in root.iterdir()
    if d.is_dir() and not d.name.startswith("_") and d.name != "__pycache__"
)

print("=== Module-level cross-domain import audit ===\n")
for app in apps:
    app_dir = root / app
    ml_imports = {}
    for pyf in sorted(app_dir.rglob("*.py")):
        if "__pycache__" in str(pyf) or "test_" in pyf.name:
            continue
        try:
            tree = ast.parse(pyf.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = node.module.split(".")
                if (
                    parts[0] == "apps"
                    and len(parts) >= 2
                    and parts[1] != app
                    and parts[1] != "_adapters"
                ):
                    key = str(pyf.relative_to(root))
                    ml_imports.setdefault(key, set()).add(parts[1])

    if ml_imports:
        print(f"  {app}:")
        for f, deps in sorted(ml_imports.items()):
            print(f"    {f}: {sorted(deps)}")
    else:
        print(f"  {app}: (no module-level cross-domain imports)")
