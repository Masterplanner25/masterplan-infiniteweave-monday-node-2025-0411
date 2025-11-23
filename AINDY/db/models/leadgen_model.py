"""
LEAD GENERATION RESULT MODEL
------------------------------------
Part of: A.I.N.D.Y. – Infinity Algorithm Layer
Purpose: Store results from the B2B Lead Generation via AI Search Optimization module.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, func
from db.database import Base


class LeadGenResult(Base):
    """
    Stores structured data for each discovered lead
    produced by the AI Search Optimization module.
    """

    __tablename__ = "leadgen_results"

    # --- Core Identification ---
    id = Column(Integer, primary_key=True, index=True)
    query = Column(String, index=True)

    # --- Lead Information ---
    company = Column(String, index=True)
    url = Column(String)
    context = Column(String)  # Optional: description, snippet, or hiring note

    # --- Infinity Algorithm Scoring ---
    fit_score = Column(Float)           # Solution / Market Fit
    intent_score = Column(Float)        # Buying intent and urgency
    data_quality_score = Column(Float)  # Information completeness
    overall_score = Column(Float)       # Weighted total score

    # --- Reasoning and Traceability ---
    reasoning = Column(String)          # One-line justification
    created_at = Column(DateTime, default=func.now())

    def __repr__(self):
        return f"<LeadGenResult(company='{self.company}', overall_score={self.overall_score})>"
