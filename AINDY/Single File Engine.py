```python
"""
A.I.N.D.Y. Core Loop v1 — Single File Engine
------------------------------------------

This file implements:

1. Flow Runner (stateful execution engine)
2. Node Execution Contract
3. Persistence (PostgreSQL via SQLAlchemy)
4. WAIT / RESUME system
5. Event Router + Subscriptions
6. Memory (event outcomes)
7. Strategy Layer (basic learning)
8. Governance (policy enforcement)
9. Intent → Plan → Flow pipeline

This is a minimal but complete "Temporal-class" system.

NOTE: Simplified for clarity (no async workers, no queues yet).
"""

# =========================
# IMPORTS
# =========================

import uuid, time, datetime
from typing import Dict, Any
from sqlalchemy import create_engine, Column, String, JSON, DateTime, Boolean, Float
from sqlalchemy.orm import declarative_base, sessionmaker

# =========================
# DATABASE SETUP
# =========================

DATABASE_URL = "postgresql://user:pass@localhost/db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# =========================
# DATABASE MODELS
# =========================

class FlowRun(Base):
    __tablename__ = "flow_runs"
    id = Column(String, primary_key=True)
    flow_name = Column(String)
    state = Column(JSON)
    current_node = Column(String)
    status = Column(String)
    waiting_for = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

class FlowHistory(Base):
    __tablename__ = "flow_history"
    id = Column(String, primary_key=True)
    flow_run_id = Column(String)
    node_name = Column(String)
    status = Column(String)
    input_state = Column(JSON)
    output_patch = Column(JSON)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class EventOutcome(Base):
    __tablename__ = "event_outcomes"
    id = Column(String, primary_key=True)
    event_type = Column(String)
    flow_name = Column(String)
    success = Column(Boolean)
    execution_time = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Strategy(Base):
    __tablename__ = "strategies"
    id = Column(String, primary_key=True)
    intent_type = Column(String)
    flow = Column(JSON)
    score = Column(Float)
    usage_count = Column(String)

# =========================
# NODE REGISTRY
# =========================

NODE_REGISTRY = {}

def register_node(name):
    def wrapper(fn):
        NODE_REGISTRY[name] = fn
        return fn
    return wrapper

# =========================
# POLICY (GOVERNANCE)
# =========================

POLICY = {
    "max_retries": 3,
    "blocked_nodes": []
}

def enforce_policy(node_name):
    if node_name in POLICY["blocked_nodes"]:
        raise Exception("Blocked by policy")

# =========================
# NODE EXECUTION CONTRACT
# =========================

def execute_node(node_name, state, context):
    enforce_policy(node_name)

    node_fn = NODE_REGISTRY[node_name]
    attempt = context["attempts"].get(node_name, 0) + 1
    context["attempts"][node_name] = attempt

    return node_fn(state, context)

# =========================
# FLOW RUNNER
# =========================

class PersistentFlowRunner:

    def __init__(self, flow):
        self.flow = flow

    def start(self, initial_state, flow_name="default"):
        db = SessionLocal()

        run = FlowRun(
            id=str(uuid.uuid4()),
            flow_name=flow_name,
            state=initial_state,
            current_node=self.flow["start"],
            status="RUNNING"
        )

        db.add(run)
        db.commit()
        db.close()

        return self.resume(run.id)

    def resume(self, run_id):
        db = SessionLocal()
        run = db.query(FlowRun).get(run_id)

        state = run.state
        current_node = run.current_node

        context = {"run_id": run.id, "attempts": {}}

        while True:

            input_snapshot = state.copy()
            result = execute_node(current_node, state, context)

            status = result["status"]
            patch = result.get("output_patch", {})

            # LOG HISTORY
            db.add(FlowHistory(
                id=str(uuid.uuid4()),
                flow_run_id=run.id,
                node_name=current_node,
                status=status,
                input_state=input_snapshot,
                output_patch=patch
            ))
            db.commit()

            # HANDLE STATUS
            if status == "SUCCESS":
                state.update(patch)

            elif status == "RETRY":
                if context["attempts"][current_node] < POLICY["max_retries"]:
                    continue
                else:
                    run.status = "FAILED"
                    db.commit()
                    return {"status": "FAILED"}

            elif status == "FAILURE":
                run.status = "FAILED"
                db.commit()
                return {"status": "FAILED"}

            elif status == "WAIT":
                run.status = "WAITING"
                run.waiting_for = result.get("wait_for")
                db.commit()
                return {"status": "WAITING", "run_id": run.id}

            # END CHECK
            if current_node in self.flow.get("end", []):
                run.status = "SUCCESS"
                run.state = state
                db.commit()
                return {"status": "SUCCESS", "state": state}

            # NEXT NODE
            next_node = resolve_next_node(current_node, state, self.flow)

            run.current_node = next_node
            run.state = state
            db.commit()

            current_node = next_node

# =========================
# EDGE RESOLUTION
# =========================

def resolve_next_node(current_node, state, flow):
    edges = flow["edges"].get(current_node, [])

    if isinstance(edges, list) and edges and isinstance(edges[0], dict):
        for e in edges:
            if e["condition"](state):
                return e["target"]
        return None

    return edges[0] if edges else None

# =========================
# EVENT ROUTER
# =========================

flow_registry = {}

def route_event(event_type, payload):
    db = SessionLocal()

    # Resume waiting flows
    runs = db.query(FlowRun).filter(
        FlowRun.waiting_for == event_type,
        FlowRun.status == "WAITING"
    ).all()

    for run in runs:
        run.state["event"] = payload
        run.status = "RUNNING"
        run.waiting_for = None
        db.commit()

        runner = PersistentFlowRunner(flow_registry[run.flow_name])
        runner.resume(run.id)

    db.close()

# =========================
# MEMORY (OUTCOME TRACKING)
# =========================

def record_outcome(event_type, flow_name, success, execution_time):
    db = SessionLocal()
    db.add(EventOutcome(
        id=str(uuid.uuid4()),
        event_type=event_type,
        flow_name=flow_name,
        success=success,
        execution_time=execution_time
    ))
    db.commit()
    db.close()

# =========================
# STRATEGY SELECTION
# =========================

def select_strategy(intent_type):
    db = SessionLocal()
    strategies = db.query(Strategy).filter(
        Strategy.intent_type == intent_type
    ).all()

    if not strategies:
        return None

    best = max(strategies, key=lambda s: s.score)
    return best.flow

# =========================
# INTENT PIPELINE
# =========================

def generate_plan_from_intent(intent):
    return {
        "steps": ["analyze", "execute", "evaluate"]
    }

def compile_plan_to_flow(plan):
    flow = {"start": plan["steps"][0], "edges": {}, "end": [plan["steps"][-1]]}
    for i in range(len(plan["steps"]) - 1):
        flow["edges"][plan["steps"][i]] = [plan["steps"][i+1]]
    return flow

def execute_intent(intent_data):

    # Try strategy first
    flow = select_strategy(intent_data["intent"])

    if not flow:
        plan = generate_plan_from_intent(intent_data)
        flow = compile_plan_to_flow(plan)

    flow_registry["dynamic"] = flow

    runner = PersistentFlowRunner(flow)
    return runner.start({"intent": intent_data})

# =========================
# EXAMPLE NODES
# =========================

@register_node("analyze")
def analyze(state, context):
    return {"output_patch": {"analysis": "done"}, "status": "SUCCESS"}

@register_node("execute")
def execute(state, context):
    return {"output_patch": {"result": "done"}, "status": "SUCCESS"}

@register_node("evaluate")
def evaluate(state, context):
    return {"output_patch": {"confidence": 0.9}, "status": "SUCCESS"}

# =========================
# EXAMPLE RUN
# =========================

if __name__ == "__main__":

    flow = {
        "start": "analyze",
        "edges": {
            "analyze": ["execute"],
            "execute": ["evaluate"]
        },
        "end": ["evaluate"]
    }

    flow_registry["test"] = flow

    runner = PersistentFlowRunner(flow)

    result = runner.start({"goal": "Build A.I.N.D.Y."})

    print("\nFINAL RESULT:", result)
```
