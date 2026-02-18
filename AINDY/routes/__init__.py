from .seo_routes import router as seo_router
from .task_router import router as task_router
from .bridge_router import router as bridge_router
from .authorship_router import router as authorship_router
from .rippletrace_router import router as rippletrace_router
from .network_bridge_router import router as network_bridge_router
from .db_verify_router import router as db_verify_router
from .research_results_router import router as research_router
from .main_router import router as main_router
from .freelance_router import router as freelance_router
from .arm_router import router as arm_router
from .leadgen_router import router as leadgen_router
from .dashboard_router import router as dashboard_router
from .health_router import router as health_router
from .health_dashboard_router import router as health_dashboard_router
from .social_router import router as social_router
from .analytics_router import router as analytics_router
from routes.genesis_router import router as genesis_router


ROUTERS = [
    seo_router,
    task_router,
    bridge_router,
    authorship_router,
    rippletrace_router,
    network_bridge_router,
    db_verify_router,
    research_router,
    main_router,
    freelance_router,
    arm_router,
    leadgen_router,
    dashboard_router,
    health_router,
    health_dashboard_router,
    social_router,
    analytics_router,
    genesis_router
    
]

