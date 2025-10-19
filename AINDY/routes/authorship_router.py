# /routers/authorship_router.py
"""
A.I.N.D.Y. Authorship Router
----------------------------
API interface for the Epistemic Reclaimer (Authorship Integrity Layer).
Allows users and collaborators to upload text and receive a
reclaimed, watermarked version with a visible + invisible authorship signature.
"""

# /routes/authorship_router.py
from fastapi import APIRouter
from services.authorship_services import reclaim_authorship

router = APIRouter(prefix="/authorship", tags=["Authorship"])

@router.post("/reclaim")
def reclaim_authorship_endpoint(content: str, author: str = "Last name, First name", motto: str = "Yourmottohere"):
    """
    Reclaim authorship for provided text.
    Returns semantically watermarked text and fingerprint metadata.
    """
    return reclaim_authorship(content, author, motto)

