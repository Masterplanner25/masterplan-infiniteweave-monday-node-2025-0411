"""Import all app-owned ORM models so they register with SQLAlchemy metadata."""

from apps.analytics.models import *  # noqa: F401,F403
from apps.arm.models import *  # noqa: F401,F403
from apps.authorship.models import *  # noqa: F401,F403
from apps.automation.models import *  # noqa: F401,F403
from apps.freelance.models import *  # noqa: F401,F403
from apps.masterplan.models import *  # noqa: F401,F403
from apps.rippletrace.models import *  # noqa: F401,F403
from apps.search.models import *  # noqa: F401,F403
from apps.tasks.models import *  # noqa: F401,F403
