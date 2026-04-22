from AINDY.runtime.flow_engine.shared import Callable, Optional, Session, logger

NODE_REGISTRY: dict[str, Callable] = {}
FLOW_REGISTRY: dict[str, dict] = {}


def _registry_flow_plan(
    intent_type: str,
    db: Session,
    user_id: str = None,
) -> Optional[dict]:
    from AINDY.platform_layer import registry

    context = {
        "flow_type": intent_type,
        "intent_type": intent_type,
        "db": db,
        "user_id": user_id,
    }
    handler = registry.get_flow_strategy(intent_type)
    value = handler(context) if handler else None
    return value if isinstance(value, dict) else None


select_strategy = _registry_flow_plan


def register_node(name: str):
    def wrapper(fn: Callable):
        NODE_REGISTRY[name] = fn
        return fn

    return wrapper


def register_flow(name: str, flow: dict) -> None:
    FLOW_REGISTRY[name] = flow
    logger.debug("Flow registered: %s", name)
