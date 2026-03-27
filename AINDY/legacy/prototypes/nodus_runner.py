import os
import uuid
from datetime import datetime
from fastapi import FastAPI, Request, BackgroundTasks, Depends, HTTPException
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from tenacity import retry, stop_after_attempt, wait_exponential
from apscheduler.schedulers.background import BackgroundScheduler

# --- CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/dbname")
API_KEY = os.getenv("API_KEY", "super-secret-key")
API_KEY_NAME = "X-API-KEY"

# --- DATABASE SETUP ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class AutomationLog(Base):
    __tablename__ = "automation_logs"
    id = Column(Integer, primary_key=True)
    source = Column(String)
    payload = Column(JSON)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)

# --- SECURITY ---
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
async def validate_key(header: str = Depends(api_key_header)):
    if header != API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return header

# --- APP & SCHEDULER ---
app = FastAPI(title="DIY Automation Engine")
scheduler = BackgroundScheduler()

# --- THE WORKER (With Retries) ---
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def execute_logic(data):
    # This simulates a 'Node' in n8n
    print(f"Executing task for: {data.get('user', 'Unknown')}")
    # Logic: e.g., requests.post("https://slack.com/api/...", json=data)
    return True

def run_worker_task(log_id, data):
    db = SessionLocal()
    log = db.query(AutomationLog).get(log_id)
    try:
        execute_logic(data)
        log.status = "Success"
    except Exception as e:
        log.status = f"Failed: {str(e)}"
    db.commit()
    db.close()

# --- ENDPOINTS ---
@app.post("/webhook/{source}", dependencies=[Depends(validate_key)])
async def trigger_webhook(source: str, request: Request, bg: BackgroundTasks):
    payload = await request.json()
    db = SessionLocal()
    new_log = AutomationLog(source=source, payload=payload, status="Pending")
    db.add(new_log)
    db.commit()
    db.refresh(new_log)
    bg.add_task(run_worker_task, new_log.id, payload)
    return {"execution_id": new_log.id, "status": "queued"}

@app.post("/replay/{log_id}", dependencies=[Depends(validate_key)])
async def replay(log_id: int, bg: BackgroundTasks):
    db = SessionLocal()
    log = db.query(AutomationLog).get(log_id)
    if not log: raise HTTPException(404)
    log.status = "Replaying"
    db.commit()
    bg.add_task(run_worker_task, log.id, log.payload)
    return {"message": "Replay started"}

# --- CRON JOBS ---
def weekly_report():
    print("Running scheduled weekly report...")

scheduler.add_job(weekly_report, 'cron', day_of_week='mon', hour=9)
scheduler.start()