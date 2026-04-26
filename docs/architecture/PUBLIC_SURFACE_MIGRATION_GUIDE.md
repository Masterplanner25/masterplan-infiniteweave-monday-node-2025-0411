---
title: "Public Surface Migration Guide"
last_verified: "2026-04-26"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Public Surface Migration Guide

This document tracks breaking changes and migration steps for all public
surfaces. When a surface is bumped to a new major version, a section is
added here.

## Migration: LoopAdjustment ORM → Service Functions (analytics consumers)

**Affects:** analytics callers of automation.public.LoopAdjustment
**Status:** IN PROGRESS (Apps Prompt 3)
**Target version:** automation.public v2.0

### Before

```python
from apps.automation.public import LoopAdjustment
rows = db.query(LoopAdjustment).filter(...).all()
```

### After

```python
from apps.automation.public import get_loop_adjustments
rows = get_loop_adjustments(user_id, db, limit=10)
```

The returned `rows` are plain dicts, not ORM objects. Access columns as
`row["prediction_accuracy"]` instead of `row.prediction_accuracy`.

---

(Add more migration sections here as surfaces evolve.)
