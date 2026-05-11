from __future__ import annotations

from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from apps.arm.models import ArmConfig


def get_config(db: Session) -> ArmConfig | None:
    return db.query(ArmConfig).filter(ArmConfig.id == "default").first()


def upsert_config(db: Session, **fields: Any) -> ArmConfig:
    config = get_config(db)
    if config is None:
        config = ArmConfig(id="default")
        db.add(config)

    for key, value in fields.items():
        if hasattr(ArmConfig, key):
            setattr(config, key, value)

    try:
        db.commit()
        db.refresh(config)
    except SQLAlchemyError:
        db.rollback()
        raise
    return config
