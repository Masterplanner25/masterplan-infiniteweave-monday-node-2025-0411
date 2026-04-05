You are working in the AINDY/ Python/FastAPI codebase.

TASK: V1-CONT-004 — Create `AINDY/tests/integration/test_execution_contract.py`
with integration tests that verify the execution contract is enforced end-to-end
for both the Genesis and Task subsystems.

PREREQUISITE: V1-CONT-003 must be complete (Task operations emit SystemEvents).
Do not start this task until `tests/v1_gates/test_v1_gates.py::test_task_operations_emit_system_event`
is passing.

FILES TO READ FIRST (in order):
1. AINDY/tests/v1_gates/test_v1_gates.py           — gate tests as reference;
                                                      read lines 434-508 for the
                                                      genesis (V1-VAL-011) and
                                                      task (V1-VAL-012) patterns
2. AINDY/tests/v1_gates/conftest.py                 — SQLite ARRAY shim
3. AINDY/tests/unit/conftest.py                     — SQLite type shims
4. AINDY/core/observability_events.py               — the emit helper
5. AINDY/services/system_event_types.py             — TASK_* and GENESIS_* constants
6. AINDY/routes/genesis_router.py lines 50-120      — genesis message endpoint
7. AINDY/services/task_services.py lines 366-531    — task service functions

BACKGROUND:
The gate tests (tests/v1_gates/) verify pass/fail at a single point each.
This integration test file goes deeper: it tests multiple lifecycle events per
operation, verifies event_type values, verifies no crash on failure paths, and
confirms the contract holds across both subsystems. These tests use the same
`client`, `auth_headers`, and `db_session` fixtures from the shared conftest.

FIND THE SHARED FIXTURES:
The gate test conftest (tests/v1_gates/conftest.py) inherits from a parent
conftest. Before writing the new file, run:
  grep -rn "def client\|def auth_headers\|def db_session" AINDY/tests/
to find where `client`, `auth_headers`, and `db_session` are defined.
The new test file must either use those fixtures directly or copy the minimal
conftest pattern needed for it to run standalone.

CREATE: AINDY/tests/integration/test_execution_contract.py

The file must contain the following 6 tests:

─────────────────────────────────────────────────────────────────────────────
TEST 1: test_task_create_emits_task_created_event
─────────────────────────────────────────────────────────────────────────────
POST /apps/tasks/create with a valid payload.
Assert:
  - Response is 2xx (not 5xx).
  - At least one SystemEvent with event_type == "task.created" was written.
  - The event payload contains "task_id" and "name".

─────────────────────────────────────────────────────────────────────────────
TEST 2: test_task_start_emits_task_started_event
─────────────────────────────────────────────────────────────────────────────
Create a task via the service layer directly (not HTTP), then call
`start_task(db, name, user_id)` from `services.task_services`.
Assert:
  - At least one SystemEvent with event_type == "task.started" was written
    after the start call.

─────────────────────────────────────────────────────────────────────────────
TEST 3: test_task_complete_emits_task_completed_event
─────────────────────────────────────────────────────────────────────────────
Create and start a task via service layer, then call `complete_task`.
Assert:
  - At least one SystemEvent with event_type == "task.completed" was written.

─────────────────────────────────────────────────────────────────────────────
TEST 4: test_task_pause_emits_task_paused_event
─────────────────────────────────────────────────────────────────────────────
Create and start a task via service layer, then call `pause_task`.
Assert:
  - At least one SystemEvent with event_type == "task.paused" was written.

─────────────────────────────────────────────────────────────────────────────
TEST 5: test_genesis_message_emits_started_event
─────────────────────────────────────────────────────────────────────────────
POST /apps/genesis/message with a valid session_id and message.
If no session exists (404/422), skip via pytest.skip with message
"no genesis session available in test DB".
Assert:
  - At least one SystemEvent with event_type == "genesis.message.started"
    was written (emitted BEFORE the flow runs, so this holds even if the
    flow itself fails).

─────────────────────────────────────────────────────────────────────────────
TEST 6: test_contract_events_are_never_fatal
─────────────────────────────────────────────────────────────────────────────
Patch `core.observability_events.emit_observability_event` to raise
RuntimeError("simulated emit failure").
POST /apps/tasks/create.
Assert:
  - The endpoint still returns 2xx (the contract emission failure must NOT
    propagate to the caller).

─────────────────────────────────────────────────────────────────────────────

IMPLEMENTATION NOTES:
- Use `from unittest.mock import patch` for test 6.
- Use `from services.system_event_types import SystemEventTypes` for event_type
  constant strings (do not hardcode string literals in asserts).
- Tests 2-4 call service layer functions directly — they need a `db_session`
  fixture and a valid user_id UUID string. Use "00000000-0000-0000-0000-000000000001"
  as the test user_id (consistent with the existing gate tests).
- Wrap the db_session.expire_all() call before querying SystemEvent rows
  (same pattern as the gate tests) to avoid stale-read false negatives.
- If tests/integration/ has no conftest.py, create a minimal one that includes
  the ARRAY→JSON SQLite shim (copy from tests/v1_gates/conftest.py).

ACCEPTANCE CRITERIA:
- `python -m pytest tests/integration/test_execution_contract.py -v` runs
  all 6 tests; none are ERROR; test 5 may be skipped but must not fail.
- `python -m pytest tests/unit/ -q` still passes with 740 passed (no regressions
  from a new conftest accidentally shadowing fixtures).
- No test uses `pytest.skip` as a way to avoid implementing the assertion —
  skip is only allowed in test 5 for the "no session" case.
