# Documentation Frontmatter Standard

Architecture and reference docs under the governed `docs/` sections must start with YAML frontmatter as the first block in the file.

Required format:

```yaml
---
title: "Human-readable title"
last_verified: "YYYY-MM-DD"
api_version: "X.Y"
status: current
owner: "platform-team"
---
```

Required fields:

- `title`: Human-readable document title.
- `last_verified`: ISO date when the doc was last checked against the current system.
- `api_version`: The `AINDY/config.py` `API_VERSION` major and minor version, in `X.Y` format.
- `status`: One of `current`, `outdated`, or `draft`.
- `owner`: Team or individual responsible for maintaining the doc.

Status rules:

- `current`: verified within the last 90 days and believed accurate.
- `outdated`: known to be behind the current implementation, or older than the freshness window.
- `draft`: in progress and not yet verified.

The linter is `python scripts/lint_docs.py`. Missing or invalid frontmatter is a build failure. Stale docs are warnings unless strict mode is enabled.

## Contributing Documentation

### When adding a new architecture doc

1. Place it in the appropriate `docs/` subdirectory.
2. Add the required frontmatter as the first block in the file.
3. Set `last_verified` to today's date.
4. Set `api_version` to the current `API_VERSION` major and minor from `AINDY/config.py`.
5. Set `status` to `draft` until you verify the content against the current system, then change it to `current`.
6. Run `python scripts/lint_docs.py` before committing.

### When updating an existing doc

1. Update `last_verified` to today's date.
2. Update `api_version` if the API version has changed.
3. If the doc is now accurate, set `status` to `current`.

### When you know a doc is wrong but don't have time to fix it

1. Change `status` to `outdated`.
2. Optionally add this comment at the top of the doc body after the frontmatter:

```html
<!-- STATUS: This doc describes the system as of api_version X.Y.
     Section "Foo" is known to be outdated as of YYYY-MM-DD. -->
```
