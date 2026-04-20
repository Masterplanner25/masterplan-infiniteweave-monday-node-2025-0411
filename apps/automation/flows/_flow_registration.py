import logging

from AINDY.runtime.flow_engine import FLOW_REGISTRY, register_flow, register_node

logger = logging.getLogger(__name__)


def single_node_flow(start: str) -> dict:
    return {"start": start, "edges": {}, "end": [start]}


def register_nodes(nodes: dict[str, callable]) -> None:
    for node_name, node_fn in nodes.items():
        register_node(node_name)(node_fn)


def register_single_node_flows(flows: dict[str, str]) -> None:
    for flow_name, node_name in flows.items():
        if flow_name not in FLOW_REGISTRY:
            register_flow(flow_name, single_node_flow(node_name))
