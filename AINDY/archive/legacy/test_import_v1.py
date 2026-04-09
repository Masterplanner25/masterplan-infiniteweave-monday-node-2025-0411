import pytest
pytest.skip("Legacy tests not compatible with current architecture", allow_module_level=True)

try:
        from config import Base
        print("Import successful!")
except ImportError as e:
        print(f"ImportError: {e}")
