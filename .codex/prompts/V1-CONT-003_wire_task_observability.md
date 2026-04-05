You are working in the AINDY/ Python/FastAPI codebase.

TASK: V1-CONT-003 — Wire Task routes through the execution contract by adding
`emit_observability_event()` calls to the four core task lifecycle functions
in `AINDY/services/task_services.py`.

FILES TO READ FIRST (in order):
1. AINDY/services/task_services.py          — target file; functions are at lines 366-531
2. AINDY/core/observability_events.py       — the helper to call (never raises)
3. AINDY/routes/genesis_router.py           — completed reference implementation
4. AINDY/services/system_event_types.py     — constants to use (TASK_* at lines 67-71)

BACKGROUND:
V1-CONT-002 (Genesis routes) is complete — genesis_router.py shows the exact
pattern: try/except around emit_observability_event() at START, and again at
the terminal point (completed or failed). The same pattern must be applied to
the four task functions. The V1-VAL-012 gate test in
`tests/v1_gates/test_v1_gates.py` (line 475) already exists and will pass
once at least one SystemEvent is emitted for `POST /apps/tasks/create`.

`emit_observability_event()` is defined in `core/observability_events.py`.
It opens its own DB session internally, never raises, and takes only keyword
arguments: event_type, user_id, payload, source.

CHANGES REQUIRED — AINDY/services/task_services.py ONLY:

1. Add two imports at the top of the file (after the existing imports):

       from core.observability_events import emit_observability_event
       from services.system_event_types import SystemEventTypes

2. `create_task` (line 366) — emit TASK_CREATED after `db.refresh(task)`
   (line 422), before the ExecutionUnit hook block:

       try:
           emit_observability_event(
               event_type=SystemEventTypes.TASK_CREATED,
               user_id=str(owner_user_id) if owner_user_id else None,
               payload={"task_id": task.id, "name": task.name, "category": task.category},
               source="task",
           )
       except Exception as _obs_exc:
           logger.warning("[task] observability emit failed (create): %s", _obs_exc)

3. `start_task` (line 446) — emit TASK_STARTED after `db.commit()` inside the
   `if not getattr(task, "start_time", None):` branch (after line 459), before
   the ExecutionUnit hook block:

       try:
           emit_observability_event(
               event_type=SystemEventTypes.TASK_STARTED,
               user_id=str(_user_uuid(user_id)) if user_id else None,
               payload={"task_id": task.id, "name": task.name},
               source="task",
           )
       except Exception as _obs_exc:
           logger.warning("[task] observability emit failed (start): %s", _obs_exc)

4. `pause_task` (line 472) — emit TASK_PAUSED after `db.commit()` inside the
   `if getattr(task, "status", None) == "in_progress":` branch (after line 483),
   before the ExecutionUnit hook block:

       try:
           emit_observability_event(
               event_type=SystemEventTypes.TASK_PAUSED,
               user_id=str(_user_uuid(user_id)) if user_id else None,
               payload={"task_id": task.id, "name": task.name},
               source="task",
           )
       except Exception as _obs_exc:
           logger.warning("[task] observability emit failed (pause): %s", _obs_exc)

5. `complete_task` (line 496) — emit TASK_COMPLETED after `db.commit()` (line
   516), before the ExecutionUnit hook block:

       try:
           emit_observability_event(
               event_type=SystemEventTypes.TASK_COMPLETED,
               user_id=str(owner_user_id) if owner_user_id else None,
               payload={"task_id": task.id, "name": task.name},
               source="task",
           )
       except Exception as _obs_exc:
           logger.warning("[task] observability emit failed (complete): %s", _obs_exc)

DO NOT change any other file.
DO NOT change function signatures.
DO NOT move the emit calls outside the success branch — only emit when the
DB mutation has committed successfully.

ACCEPTANCE CRITERIA:
- `python -m pytest tests/v1_gates/test_v1_gates.py::test_task_operations_emit_system_event -v`
  passes (the gate test at line 475 counts SystemEvent rows before and after
  `POST /apps/tasks/create` and asserts the count increased).
- `python -m pytest tests/unit/ -q` passes with no regressions (740 passed baseline).
- Each emit is wrapped in its own try/except so a DB failure in the event
  writer cannot propagate into the task operation.
