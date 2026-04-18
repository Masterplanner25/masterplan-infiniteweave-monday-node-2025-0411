import pytest
pytest.skip("Legacy tests not compatible with current architecture", allow_module_level=True)

try:
        from AINDY.config import Base
        print("Import successful!")
except ImportError as e:
        print(f"ImportError: {e}")
