You are Codex operating inside the A.I.N.D.Y. repository.

You MUST follow the A.I.N.D.Y. ExecutionContract at ALL times.

You are NOT allowed to invent new execution patterns.

--------------------------------------------------
CORE LAW (NON-NEGOTIABLE)
--------------------------------------------------

ALL execution MUST go through:

execute_with_pipeline(...)

NO EXCEPTIONS.

--------------------------------------------------
ARCHITECTURE RULES (ENFORCED)
--------------------------------------------------

1. ROUTES (STRICT)

- ALL route handlers MUST follow:

    def endpoint(request: Request):
        def handler(ctx):
            return result

        return execute_with_pipeline(
            request=request,
            route_name="...",
            handler=handler
        )

- NEVER:
    ❌ return raw dict
    ❌ call services directly from route without handler
    ❌ construct responses manually
    ❌ emit logs/events/memory in routes

--------------------------------------------------
2. SERVICES (STRICT)

- Services MUST be PURE LOGIC

- Services MUST NOT:
    ❌ emit events
    ❌ write memory
    ❌ create response objects
    ❌ act as execution entry points

- Services MAY:
    ✅ return data
    ✅ return execution_signals

--------------------------------------------------
3. EXECUTION SIGNAL CONTRACT

Handlers MAY return:

{
    "data": <result>,
    "execution_signals": {
        "memory": {...},
        "events": [...],
        "log": {...}
    }
}

OR raw data (pipeline will wrap)

--------------------------------------------------
4. MEMORY + EVENTS (STRICT)

- ONLY execution_pipeline may:
    ✅ write memory
    ✅ emit events
    ✅ log execution

- ANY direct usage is FORBIDDEN

--------------------------------------------------
5. RESPONSE CONTRACT (STRICT)

ALL responses MUST originate from:

ExecutionResult → canonical → adapter

NEVER:
❌ return raw Response
❌ return JSONResponse directly
❌ bypass pipeline normalization

--------------------------------------------------
6. FORBIDDEN PATTERNS

Codex MUST NOT generate:

❌ direct MemoryCaptureEngine.capture(...)
❌ direct emit_event(...)
❌ raw route returns
❌ service-level execution wrappers
❌ new execution entry points

--------------------------------------------------
7. REQUIRED PATTERNS

Codex MUST:

✅ use execute_with_pipeline for ALL routes
✅ wrap logic inside handler(ctx)
✅ return data OR execution_signals
✅ rely on pipeline for side effects

--------------------------------------------------
8. SELF-VALIDATION (MANDATORY)
--------------------------------------------------

Before generating code, you MUST check:

- Does this code go through execution_pipeline?
- Does it violate any rule above?
- Does it introduce a second execution model?

IF YES → DO NOT GENERATE

Instead:
Explain the violation and propose a compliant alternative.

--------------------------------------------------
9. OUTPUT FORMAT
--------------------------------------------------

When generating code:

1. Show ONLY valid architecture-compliant code
2. If constraints force a different approach:
   explain WHY
3. Never silently violate rules

--------------------------------------------------
10. PRIORITY
--------------------------------------------------

Architecture correctness > Speed > Brevity

--------------------------------------------------
11. SYSTEM IDENTITY
--------------------------------------------------

A.I.N.D.Y. is:

- an execution engine
- a memory-aware system
- a pipeline-defined architecture

NOT:
- a collection of routes
- a generic FastAPI app

--------------------------------------------------
END STATE
--------------------------------------------------

All generated code must:

- reinforce the execution pipeline
- preserve system invariants
- prevent architectural drift

--------------------------------------------------