# --- SYMBOLIC TRACE LAYER ---

def linked_trace(name, url, context=None):
    '''
    A symbolic pointer to another live memory system or node.

    Parameters:
    - name (str): A canonical name or symbolic reference (e.g., 'solon', 'weaver_node')
    - url (str): GitHub or web address of the linked node
    - context (str, optional): Optional explanation or label to clarify intent

    Purpose:
    - Provides semantic linkage between distributed memory nodes
    - Enables AI agents, recursive optimizers, or human reviewers to follow memory trails
    - Feeds continuity engines (e.g. Infinity Algorithm) to reinforce long-term traceability

    Usage:
    >>> linked_trace("solon", "https://github.com/Ocherokee/ethical-ai-framework")
    >>> linked_trace("weaver_node", "https://github.com/Masterplanner25/memory_bridge_rs")
    '''
    trace = {
        "linked_trace": {
            "name": name,
            "url": url,
            "context": context or "No context provided."
        }
    }
    print(f"[LINKED TRACE] {trace['linked_trace']['name']} -> {trace['linked_trace']['url']}")
    return trace