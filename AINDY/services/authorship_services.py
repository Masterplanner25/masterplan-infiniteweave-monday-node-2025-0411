"""
Authorship Services
--------------------
This module connects the Epistemic Reclaimer to A.I.N.D.Y.’s backend logic.
It provides API-facing functions to:
    - Run the full authorship reclamation pipeline
    - Detect and log AI fingerprints
    - Generate and return verified, semantically watermarked text

Dependencies:
    from authorship.Authorship import epistemic_reclaim
"""

from Tools.authorship.Authorship import epistemic_reclaim


def reclaim_authorship(
    content: str,
    author: str = "Knight, Shawn",
    motto: str = "Quicker, Better, Smarter, Faster"
) -> dict:
    """
    Executes the Epistemic Reclaimer process and returns metadata.
    Used by the Authorship Router.

    Args:
        content (str): Raw text or content body.
        author (str): Name or alias of the originator.
        motto (str): Custom motto or authorship message.

    Returns:
        dict: {
            "reclaimed_text": str,
            "fingerprints_detected": list,
            "originator": str,
            "motto": str
        }
    """

    reclaimed_text, fingerprints = epistemic_reclaim(
        raw_text=content,
        originator=author,
        motto=motto
    )

    return {
        "reclaimed_text": reclaimed_text,
        "fingerprints_detected": fingerprints,
        "originator": author,
        "motto": motto
    }
