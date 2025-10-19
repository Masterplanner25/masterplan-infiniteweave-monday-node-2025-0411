import logging
from fastapi import FastAPI
from routes.main_router import router
from fastapi_cache import FastAPICache
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from config import Base  # Import the Base from your config.py
from fastapi_cache.backends.inmemory import InMemoryBackend  
from fastapi import FastAPI
from services import task_services
from config import SessionLocal
import threading
from routes.seo_routes import router as seo_router
from routes.task_router import router as task_router
from routes.bridge_router import router as bridge_router
from routes.authorship_router import router as authorship_router
from routes.rippletrace_router import router as rippletrace_router
from routes.network_bridge_router import router as network_bridge_router
from routes.db_verify_router import router as db_verify_router
from routes.task_router import router as task_router

# For in-memory caching
# If you want to use Redis (uncomment and configure):
# from fastapi_cache.backends.redis import RedisBackend
# from redis import asyncio as aioredis


# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="A.I.N.D.Y. Memory Bridge")
app.include_router(router)
app.include_router(seo_router, prefix="/tools", tags=["SEO"])
app.include_router(bridge_router)
app.include_router(task_router)
app.include_router(authorship_router)
app.include_router(rippletrace_router)
app.include_router(db_verify_router)
app.include_router(task_router)
app.include_router(network_bridge_router)

# CORS (Cross-Origin Resource Sharing) for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Engagement(Base):
    __tablename__ = "engagements"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    likes = Column(Integer)
    shares = Column(Integer)
    comments = Column(Integer)
    clicks = Column(Integer)
    time_on_page = Column(Float)
    total_views = Column(Integer)
    # Add other engagement-related columns

class AIEfficiency(Base):
    __tablename__ = "ai_efficiencies"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    ai_contributions = Column(Integer)
    human_contributions = Column(Integer)
    total_tasks = Column(Integer)
    # Add other AI efficiency columns

class Impact(Base):
    __tablename__ = "impacts"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    reach = Column(Integer)
    engagement = Column(Integer)
    conversion = Column(Integer)
    # Add other impact-related columns

class Efficiency(Base):
    __tablename__ = "efficiencies"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    focused_effort = Column(Float)
    ai_utilization = Column(Float)
    time = Column(Float)
    capital = Column(Float)
    # Add other efficiency columns

class RevenueScaling(Base):
    __tablename__ = "revenue_scalings"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    ai_leverage = Column(Float)
    content_distribution = Column(Float)
    time = Column(Float)
    audience_engagement = Column(Float)
    # Add other revenue scaling columns

class ExecutionSpeed(Base):
    __tablename__ = "execution_speeds"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    ai_automations = Column(Float)
    systemized_workflows = Column(Float)
    decision_lag = Column(Float)
    # Add other execution speed columns

class AttentionValue(Base):
    __tablename__ = "attention_values"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    content_output = Column(Float)
    platform_presence = Column(Float)
    time = Column(Float)
    # Add other attention value columns

class EngagementRate(Base):
    __tablename__ = "engagement_rates"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    total_interactions = Column(Float)
    total_views = Column(Integer)
    # Add other engagement rate columns

class BusinessGrowth(Base):
    __tablename__ = "business_growths"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    revenue = Column(Float)
    expenses = Column(Float)
    scaling_friction = Column(Float)
    # Add other business growth columns

class MonetizationEfficiency(Base):
    __tablename__ = "monetization_efficiencies"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    total_revenue = Column(Float)
    audience_size = Column(Float)
    # Add other monetization efficiency columns

class AIProductivityBoost(Base):
    __tablename__ = "ai_productivity_boosts"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    tasks_with_ai = Column(Float)
    tasks_without_ai = Column(Float)
    time_saved = Column(Float)
    # Add other AI productivity boost columns

class LostPotential(Base):
    __tablename__ = "lost_potentials"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    missed_opportunities = Column(Float)
    time_delayed = Column(Float)
    gains_from_action = Column(Float)
    # Add other lost potential columns

class DecisionEfficiency(Base):
    __tablename__ = "decision_efficiencies"

    id = Column(Integer, primary_key=True, index=True)  # Added primary key
    automated_decisions = Column(Float)
    manual_decisions = Column(Float)
    processing_time = Column(Float)
    # Add other decision efficiency columns

@app.middleware("http")
async def log_requests(request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response: {response.status_code}")
    return response

@app.on_event("startup")
async def startup():
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache") # Initialize with in-memory

    # To use Redis, uncomment the following and adjust the Redis URL:
    # redis = aioredis.from_url("redis://localhost")
    # FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")

@app.on_event("startup")
async def start_background_tasks():
    db = SessionLocal()
    threading.Thread(target=task_services.check_reminders, args=(db,), daemon=True).start()
    threading.Thread(target=task_services.handle_recurrence, args=(db,), daemon=True).start()
    
@app.get("/")
def home():
    return {"message": "A.I.N.D.Y. API is running!"}