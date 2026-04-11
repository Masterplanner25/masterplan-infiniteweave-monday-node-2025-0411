"""Legacy `db` package aliasing `AINDY.db`."""

from importlib import import_module
import sys

module = import_module("AINDY.db")
sys.modules[__name__] = module

_aindy_models = sys.modules.get("AINDY.db.models")
if _aindy_models is not None:
    sys.modules.setdefault("db.models", _aindy_models)
    prefix = "AINDY.db.models."
    alias_prefix = "db.models."
    for name, mod in list(sys.modules.items()):
        if name.startswith(prefix):
            alias = f"{alias_prefix}{name[len(prefix):]}"
            sys.modules.setdefault(alias, mod)
