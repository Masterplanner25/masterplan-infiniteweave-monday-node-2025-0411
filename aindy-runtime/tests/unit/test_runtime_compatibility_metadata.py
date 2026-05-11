from __future__ import annotations

import pytest

from AINDY._version import __version__ as runtime_package_version
from AINDY.config import settings
from AINDY.platform_layer.runtime_compatibility import runtime_repo_compatibility_metadata


pytestmark = pytest.mark.runtime_only


def test_runtime_repo_compatibility_metadata_matches_runtime_versions():
    metadata = runtime_repo_compatibility_metadata()

    assert metadata["runtime_package"] == {
        "name": "aindy-runtime",
        "version": runtime_package_version,
    }
    assert metadata["apps_repo_contract"]["declaration_format"] == "pep440"
    assert metadata["apps_repo_contract"]["recommended_runtime_requirement"] == ">=1.0,<2.0"
    assert metadata["apps_repo_contract"]["compatible_runtime_major"] == runtime_package_version.split(".")[0]
    assert metadata["apps_repo_contract"]["compatible_api_major"] == settings.API_VERSION.split(".")[0]
