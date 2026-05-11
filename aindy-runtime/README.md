# aindy-runtime

`aindy-runtime` is the standalone runtime package extracted from the former monolith.

It contains the runtime code under `AINDY/`, the runtime-only manifests and entrypoints,
runtime-owned documentation, and the runtime contract test suite. It does not include
`apps/`, `apps.bootstrap`, or app-profile-only tests and docs.

## Install

```bash
python -m pip install -e . --no-deps --no-build-isolation
```

## Run

Runtime-only API boot:

```bash
aindy-runtime
```

Minimum runtime environment:

```bash
DATABASE_URL=sqlite://
AINDY_BOOT_MODE=runtime-only
SECRET_KEY=...
AINDY_API_KEY=...
PERMISSION_SECRET=...
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=ds-...
```

Equivalent module and ASGI forms:

```bash
python -m AINDY.runtime_only
uvicorn AINDY.runtime_only:app
```

Generic API entrypoint:

```bash
aindy-runtime-api
```

## Verify

```bash
python -m pytest \
  tests/unit/test_runtime_only_test_fixtures.py \
  tests/unit/test_platform_only_startup.py \
  tests/unit/test_runtime_packaging.py \
  tests/unit/test_runtime_boundary.py \
  tests/unit/test_runtime_compatibility_metadata.py \
  tests/api/test_version_api.py \
  -m runtime_only -q
```

## Docs

Runtime-owned documentation lives under `docs/runtime/`.

## Validated Split Check

Validated on `2026-05-11` in the extracted repo:

```bash
python -m pytest \
  tests/unit/test_runtime_only_test_fixtures.py \
  tests/unit/test_platform_only_startup.py \
  tests/unit/test_runtime_packaging.py \
  tests/unit/test_runtime_boundary.py \
  tests/unit/test_runtime_compatibility_metadata.py \
  tests/api/test_version_api.py \
  -m runtime_only -q
python -c "import os; os.environ.update({'AINDY_BOOT_MODE':'runtime-only','DATABASE_URL':'sqlite://','MONGO_URL':'','AINDY_ALLOW_SQLITE':'1','OPENAI_API_KEY':'sk-test-placeholder','DEEPSEEK_API_KEY':'ds-test-placeholder','SECRET_KEY':'runtime-integration-secret','AINDY_API_KEY':'runtime-integration-api-key','PERMISSION_SECRET':'runtime-integration-permission-secret','AINDY_SKIP_MONGO_PING':'1','SKIP_MONGO_PING':'1'}); from fastapi.testclient import TestClient; import AINDY.main as main; from AINDY.platform_layer import registry; payload=TestClient(main.app, raise_server_exceptions=False).get('/api/version').json(); print(payload['runtime']['boot_profile'], payload['runtime']['app_plugins_loaded'], sorted({tool['name'] for tool in registry.get_tools_for_run('default', {'user_id':'user-1','db':object()})}))"
```

Observed result:

- runtime-only `/api/version` reported `boot_profile=platform-only`
- `app_plugins_loaded` was `False`
- baseline runtime agent tools were `memory.recall` and `memory.write`
