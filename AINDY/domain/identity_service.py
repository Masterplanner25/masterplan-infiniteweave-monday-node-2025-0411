"""
Identity Service — v5 Phase 2

Manages user identity profiles. Observes patterns from
workflow behavior and updates identity incrementally.

Key principle: Identity is inferred, not declared.
A.I.N.D.Y. watches what users do and builds a picture
of who they are over time. Users can also explicitly
set preferences.

Evolution tracking: every change is logged with what
changed, why, and when. The identity layer evolves
alongside the user.
"""
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IdentityService:
    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    def get_or_create(self) -> "UserIdentity":
        """
        Get the user's identity profile.
        Creates a blank profile if none exists.
        """
        from db.models.user_identity import UserIdentity

        identity = (
            self.db.query(UserIdentity)
            .filter(UserIdentity.user_id == UUID(str(self.user_id)))
            .first()
        )

        if not identity:
            identity = UserIdentity(
                user_id=UUID(str(self.user_id)),
                preferred_languages=[],
                preferred_tools=[],
                avoided_tools=[],
                evolution_log=[],
            )
            self.db.add(identity)
            self.db.commit()
            self.db.refresh(identity)

        return identity

    def get_profile(self) -> dict:
        """
        Get the user's full identity profile as a dict.
        Returns a clean summary for use in prompts and UI.
        """
        identity = self.get_or_create()

        return {
            "user_id": self.user_id,
            "communication": {
                "tone": identity.tone,
                "notes": identity.communication_notes,
            },
            "tools": {
                "preferred_languages": identity.preferred_languages or [],
                "preferred_tools": identity.preferred_tools or [],
                "avoided_tools": identity.avoided_tools or [],
            },
            "decision_making": {
                "risk_tolerance": identity.risk_tolerance,
                "speed_vs_quality": identity.speed_vs_quality,
                "notes": identity.decision_notes,
            },
            "learning": {
                "style": identity.learning_style,
                "detail_preference": identity.detail_preference,
                "notes": identity.learning_notes,
            },
            "evolution": {
                "observation_count": identity.observation_count or 0,
                "last_updated": (
                    identity.last_updated.isoformat()
                    if identity.last_updated
                    else None
                ),
                "change_count": len(identity.evolution_log or []),
            },
        }

    def update_explicit(
        self,
        tone: str = None,
        preferred_languages: list = None,
        preferred_tools: list = None,
        avoided_tools: list = None,
        risk_tolerance: str = None,
        speed_vs_quality: str = None,
        learning_style: str = None,
        detail_preference: str = None,
        communication_notes: str = None,
        decision_notes: str = None,
        learning_notes: str = None,
    ) -> dict:
        """
        Explicitly set identity preferences.
        Called when user directly states their preferences.
        All changes are logged in evolution_log.
        """
        from db.models.user_identity import (
            VALID_DETAIL_PREFERENCES,
            VALID_LEARNING_STYLES,
            VALID_RISK_TOLERANCE,
            VALID_SPEED_VS_QUALITY,
            VALID_TONES,
        )

        identity = self.get_or_create()
        changes = []
        now = _utcnow()

        def record_change(dimension, old, new, trigger="explicit"):
            if old != new and new is not None:
                changes.append(
                    {
                        "timestamp": now.isoformat(),
                        "dimension": dimension,
                        "old_value": old,
                        "new_value": new,
                        "trigger": trigger,
                    }
                )

        if tone and tone in VALID_TONES:
            record_change("tone", identity.tone, tone)
            identity.tone = tone

        if preferred_languages is not None:
            record_change(
                "preferred_languages",
                identity.preferred_languages,
                preferred_languages,
            )
            identity.preferred_languages = preferred_languages

        if preferred_tools is not None:
            record_change(
                "preferred_tools", identity.preferred_tools, preferred_tools
            )
            identity.preferred_tools = preferred_tools

        if avoided_tools is not None:
            record_change(
                "avoided_tools", identity.avoided_tools, avoided_tools
            )
            identity.avoided_tools = avoided_tools

        if risk_tolerance and risk_tolerance in VALID_RISK_TOLERANCE:
            record_change(
                "risk_tolerance", identity.risk_tolerance, risk_tolerance
            )
            identity.risk_tolerance = risk_tolerance

        if speed_vs_quality and speed_vs_quality in VALID_SPEED_VS_QUALITY:
            record_change(
                "speed_vs_quality",
                identity.speed_vs_quality,
                speed_vs_quality,
            )
            identity.speed_vs_quality = speed_vs_quality

        if learning_style and learning_style in VALID_LEARNING_STYLES:
            record_change(
                "learning_style", identity.learning_style, learning_style
            )
            identity.learning_style = learning_style

        if detail_preference and detail_preference in VALID_DETAIL_PREFERENCES:
            record_change(
                "detail_preference",
                identity.detail_preference,
                detail_preference,
            )
            identity.detail_preference = detail_preference

        if communication_notes:
            identity.communication_notes = communication_notes
        if decision_notes:
            identity.decision_notes = decision_notes
        if learning_notes:
            identity.learning_notes = learning_notes

        if changes:
            log = list(identity.evolution_log or [])
            log.extend(changes)
            identity.evolution_log = log
            identity.last_updated = now
            identity.observation_count = (
                identity.observation_count or 0
            ) + len(changes)

        self.db.add(identity)
        self.db.commit()
        self.db.refresh(identity)

        return {
            "changes_recorded": len(changes),
            "changes": changes,
            "profile": self.get_profile(),
        }

    def observe(self, event_type: str, context: dict) -> None:
        """
        Observe a workflow event and infer identity signals.
        Called automatically by the capture engine.

        This is how identity is built without explicit input —
        A.I.N.D.Y. watches what the user does and infers
        their preferences over time.
        """
        try:
            identity = self.get_or_create()
            changes = []
            now = _utcnow()

            def maybe_add_to_list(
                field_name: str, current_list: list, value: str
            ):
                if value and value not in (current_list or []):
                    new_list = list(current_list or []) + [value]
                    setattr(identity, field_name, new_list)
                    changes.append(
                        {
                            "timestamp": now.isoformat(),
                            "dimension": field_name,
                            "old_value": current_list,
                            "new_value": new_list,
                            "trigger": f"observed:{event_type}",
                        }
                    )

            if event_type == "arm_analysis_complete":
                lang = context.get("language") or context.get("file_type")
                if lang:
                    clean_lang = lang.strip(".")
                    maybe_add_to_list(
                        "preferred_languages",
                        identity.preferred_languages,
                        clean_lang,
                    )

            if event_type == "arm_generation_complete":
                lang = context.get("language")
                if lang:
                    maybe_add_to_list(
                        "preferred_languages",
                        identity.preferred_languages,
                        lang,
                    )

            if event_type == "masterplan_locked":
                posture = context.get("posture")
                posture_to_risk = {
                    "aggressive": "aggressive",
                    "accelerated": "moderate",
                    "stable": "conservative",
                    "reduced": "conservative",
                }
                inferred_risk = posture_to_risk.get(posture)
                if inferred_risk and identity.risk_tolerance != inferred_risk:
                    changes.append(
                        {
                            "timestamp": now.isoformat(),
                            "dimension": "risk_tolerance",
                            "old_value": identity.risk_tolerance,
                            "new_value": inferred_risk,
                            "trigger": "observed:masterplan_posture",
                        }
                    )
                    identity.risk_tolerance = inferred_risk

            if event_type == "arm_analysis_complete":
                score = context.get("score", 0)
                if score >= 8 and identity.speed_vs_quality != "quality":
                    changes.append(
                        {
                            "timestamp": now.isoformat(),
                            "dimension": "speed_vs_quality",
                            "old_value": identity.speed_vs_quality,
                            "new_value": "quality",
                            "trigger": "observed:high_quality_code",
                        }
                    )
                    identity.speed_vs_quality = "quality"

            if changes:
                log = list(identity.evolution_log or [])
                log.extend(changes)
                identity.evolution_log = log
                identity.last_updated = now
                identity.observation_count = (
                    identity.observation_count or 0
                ) + 1
                self.db.add(identity)
                self.db.commit()
        except Exception as e:
            logger.warning(f"Identity observation failed: {e}")

    def get_context_for_prompt(self) -> str:
        """
        Generate a context string for injecting user
        identity into LLM prompts.
        """
        profile = self.get_profile()
        parts = []

        tone = profile["communication"]["tone"]
        if tone:
            parts.append(f"Communication style: {tone}")

        langs = profile["tools"]["preferred_languages"]
        if langs:
            parts.append(f"Preferred languages: {', '.join(langs)}")

        risk = profile["decision_making"]["risk_tolerance"]
        if risk:
            parts.append(f"Risk tolerance: {risk}")

        style = profile["learning"]["style"]
        detail = profile["learning"]["detail_preference"]
        if style or detail:
            learning = []
            if style:
                learning.append(style)
            if detail:
                learning.append(detail.replace("_", " "))
            parts.append(f"Learning preference: {', '.join(learning)}")

        if not parts:
            return ""

        return "\n\nUser identity context:\n" + "\n".join(
            f"- {p}" for p in parts
        )

    def get_evolution_summary(self) -> dict:
        """
        Summarize how the user's identity has evolved.
        Shows the arc of change over time.
        """
        identity = self.get_or_create()
        log = identity.evolution_log or []

        if not log:
            return {
                "message": (
                    "Identity profile is new. Patterns will emerge as you use "
                    "A.I.N.D.Y."
                ),
                "observation_count": 0,
                "total_changes": 0,
                "dimensions_evolved": [],
                "most_changed_dimension": None,
                "recent_changes": [],
                "evolution_arc": (
                    "No observations yet. Use A.I.N.D.Y. features to build "
                    "your identity profile."
                ),
                "changes": [],
            }

        by_dimension = {}
        for entry in log:
            dim = entry.get("dimension", "unknown")
            if dim not in by_dimension:
                by_dimension[dim] = []
            by_dimension[dim].append(entry)

        most_changed = sorted(
            by_dimension.items(), key=lambda x: len(x[1]), reverse=True
        )

        return {
            "observation_count": identity.observation_count or 0,
            "total_changes": len(log),
            "dimensions_evolved": list(by_dimension.keys()),
            "most_changed_dimension": most_changed[0][0]
            if most_changed
            else None,
            "recent_changes": log[-5:],
            "evolution_arc": (
                f"Your identity has been observed "
                f"{identity.observation_count} times with "
                f"{len(log)} preference updates across "
                f"{len(by_dimension)} dimensions."
            ),
        }

