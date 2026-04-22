"""Explicit model imports for Alembic discovery. Add new models here when creating them."""

from apps.analytics.models import (  # noqa: F401
    AIEfficiency,
    AIProductivityBoost,
    AttentionValue,
    BusinessGrowth,
    CalculationResult,
    CanonicalMetricDB,
    DecisionEfficiency,
    Efficiency,
    Engagement,
    EngagementRate,
    ExecutionSpeed,
    Impact,
    LostPotential,
    MonetizationEfficiency,
    RevenueScaling,
    ScoreHistory,
    ScoreSnapshotDB,
    UserScore,
)
from apps.arm.models import (  # noqa: F401
    ARMConfig,
    ARMLog,
    ARMRun,
    AnalysisResult,
    ArmConfig,
    CodeGeneration,
)
from apps.authorship.models import AuthorDB  # noqa: F401
from apps.automation.models import (  # noqa: F401
    AutomationLog,
    BridgeUserEvent,
    LearningRecordDB,
    LearningThresholdDB,
    LoopAdjustment,
    UserFeedback,
)
from apps.freelance.models import (  # noqa: F401
    ClientFeedback,
    FreelanceOrder,
    RevenueMetrics,
)
from apps.masterplan.models import (  # noqa: F401
    GenesisSessionDB,
    Goal,
    GoalState,
    MasterPlan,
)
from apps.rippletrace.models import (  # noqa: F401
    DropPointDB,
    PingDB,
    PlaybookDB,
    RippleEdge,
    StrategyDB,
)
from apps.search.models import (  # noqa: F401
    LeadGenResult,
    ResearchResult,
    SearchHistory,
)
from apps.tasks.models import Task  # noqa: F401
