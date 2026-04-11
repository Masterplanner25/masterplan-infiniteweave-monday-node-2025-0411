"""Alias that forwards db.database imports to AINDY.db.database."""

from importlib import import_module
import sys

sys.modules[__name__] = import_module("AINDY.db.database")
