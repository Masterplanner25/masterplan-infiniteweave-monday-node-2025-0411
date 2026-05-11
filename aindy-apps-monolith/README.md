# aindy-apps-monolith

`aindy-apps-monolith` is the app/plugin-pack repository that depends on the
installed `aindy-runtime` package.

It owns:

- `apps/`
- `client/`
- `aindy_plugins.json`
- `alembic/`
- app-profile tests and helpers
- app-owned and shared app-facing docs

It does not vendor `AINDY/`. Runtime code, runtime-only entrypoints, and
runtime-only docs live in the separate `aindy-runtime` repo.

## Install

Install runtime first, then install the apps repo:

```bash
python -m pip install "aindy-runtime>=1.0,<2.0"
python -m pip install -e . --no-build-isolation
```

For local split validation with sibling repos:

```bash
python -m pip install -e ../aindy-runtime --no-deps --no-build-isolation
python -m pip install -e . --no-build-isolation
```

## Boot The App Profile

From the apps repo root:

```bash
aindy-runtime-api
```

Equivalent forms:

```bash
uvicorn AINDY.main:app
AINDY_APP_PLUGIN_MANIFEST=./aindy_plugins.json aindy-runtime-api
```

The app repo owns `aindy_plugins.json` and `apps.bootstrap`. The runtime owns
manifest parsing, plugin loading, and process entrypoints.

## Verify

Representative app-profile subset:

```bash
python -m pytest \
  tests/unit/test_app_manifest_bootstrap_contract.py \
  tests/unit/test_import_boundaries.py \
  tests/unit/test_runtime_agent_api_ownership.py \
  tests/unit/test_tasks_public_contract.py \
  tests/unit/test_analytics_public_contract.py \
  tests/unit/test_app_model_registration.py \
  tests/test_bootstrap_completeness.py \
  -m app_profile -q
```

## Validated Split Check

Validated on `2026-05-11` in the extracted repo with installed `aindy-runtime`:

```bash
python -m pip install -e ../aindy-runtime --no-deps --no-build-isolation
python -m pip install -e . --no-build-isolation
python -m pytest \
  tests/unit/test_app_manifest_bootstrap_contract.py \
  tests/unit/test_import_boundaries.py \
  tests/unit/test_runtime_agent_api_ownership.py \
  tests/unit/test_tasks_public_contract.py \
  tests/unit/test_analytics_public_contract.py \
  tests/unit/test_app_model_registration.py \
  tests/test_bootstrap_completeness.py \
  -m app_profile -q
python -c "import os; os.environ.update({'DATABASE_URL':'sqlite://','MONGO_URL':'','AINDY_ALLOW_SQLITE':'1','OPENAI_API_KEY':'sk-test-placeholder','DEEPSEEK_API_KEY':'ds-test-placeholder','SECRET_KEY':'apps-integration-secret','AINDY_API_KEY':'apps-integration-api-key','PERMISSION_SECRET':'apps-integration-permission-secret','AINDY_SKIP_MONGO_PING':'1','SKIP_MONGO_PING':'1'}); from fastapi.testclient import TestClient; import AINDY.main as main; from AINDY.platform_layer import registry; payload=TestClient(main.app, raise_server_exceptions=False).get('/api/version').json(); print(payload['runtime']['boot_profile'], payload['runtime']['app_plugins_loaded'], payload['runtime']['app_plugin_count'], len(registry.get_registered_apps()))"
python scripts/check_app_imports.py
```

Observed result:

- app-profile `/api/version` reported `boot_profile=default-apps`
- `app_plugins_loaded` was `True`
- `app_plugin_count` and `len(registry.get_registered_apps())` were both `16`
- cross-app import boundary scan reported `33 declared, 0 undeclared`

Non-blocking bootstrap warnings seen during smoke validation:

- accepted `APP_DEPENDS_ON` ordering-gap warnings for deferred identity calls
- `apps.freelance.bootstrap` warns when `STRIPE_WEBHOOK_SECRET` is unset
