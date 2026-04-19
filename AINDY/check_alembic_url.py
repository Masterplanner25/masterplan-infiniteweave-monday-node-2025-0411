import logging

from AINDY.alembic.config import Config

logger = logging.getLogger(__name__)

config = Config("alembic.ini")
logger.info("✅ Alembic detected URL:")
logger.info("%s", config.get_main_option("sqlalchemy.url"))
