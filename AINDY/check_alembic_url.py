from AINDY.alembic.config import Config

config = Config("alembic.ini")
print("✅ Alembic detected URL:")
print(config.get_main_option("sqlalchemy.url"))
