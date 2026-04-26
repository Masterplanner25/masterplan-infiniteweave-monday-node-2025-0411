# API Breaking Change Policy

## What constitutes a MAJOR (breaking) change:
- Removing an endpoint
- Removing a field from a response body
- Changing a field's type (string -> integer, etc.)
- Changing a field's name
- Changing authentication mechanism
- Changing pagination structure
- Changing error response shape

## What constitutes a MINOR (additive) change:
- Adding a new endpoint
- Adding a new optional field to a response body
- Adding a new query parameter (optional, with default)
- Adding a new error code

## What constitutes a PATCH change:
- Fixing an incorrect status code
- Fixing a typo in a field name that was documented incorrectly
- Fixing a bug that caused wrong values to be returned

## Versioning procedure:
1. Update `API_VERSION` in `AINDY/config.py`
2. Update `"version"` in `client/package.json` to match MAJOR.MINOR
   Client patch version tracks frontend-only changes.
3. If MAJOR was bumped: update `API_MIN_CLIENT_VERSION` to the new version
4. Deploy backend first, then frontend
5. After deploy: verify `GET /api/version` returns the new version

## Deployment order for breaking changes:
Always deploy backend BEFORE frontend for MAJOR version bumps.
The `VersionMismatchBanner` gives users a reload prompt during the window
between backend and frontend deploy.
