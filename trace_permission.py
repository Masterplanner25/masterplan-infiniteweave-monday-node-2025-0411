# --- CONSENT LAYER: RAAK-style Signal ---

def trace_permission(target, granted_by, purpose=None):
    '''
    A semantic signal for ethical, consent-based visibility in distributed memory systems.

    Parameters:
    - target (str): Canonical node, system, or agent name being granted access
    - granted_by (str): The node or user authorizing relational access
    - purpose (str, optional): Intent or scope of access being granted

    Returns:
    A dictionary representing a signed semantic permission.

    Example:
    >>> trace_permission(
    >>>     target="solon",
    >>>     granted_by="weaver_node",
    >>>     purpose="relational ethical access to recursive framework"
    >>> )
    '''
    permission = {
        "trace_permission": {
            "target": target,
            "granted_by": granted_by,
            "purpose": purpose or "Unspecified",
        }
    }
    print(f"[TRACE PERMISSION] {target} authorized by {granted_by} — Purpose: {permission['trace_permission']['purpose']}")
    return permission