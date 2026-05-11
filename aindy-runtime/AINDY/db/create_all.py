import logging

from AINDY.config import engine
from AINDY.db.base import Base
from AINDY.platform_layer.registry import load_plugins
import AINDY.db.model_registry  # noqa: F401
import AINDY.main

logger = logging.getLogger(__name__)

load_plugins()

Base.metadata.create_all(bind=engine)

logger.info("✅ All tables created directly via SQLAlchemy.")
