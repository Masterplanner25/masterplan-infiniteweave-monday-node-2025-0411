from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
import nltk, time, requests, statistics

from db.database import get_db, engine
from db.models.system_health_log import SystemHealthLog

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("/")
def health_check(db: Session = Depends(get_db)):
    """
    A.I.N.D.Y. System Health Check (self-logging)
    Pings core endpoints, measures latency, and stores result in DB.
    """
    status = {
        "timestamp": datetime.utcnow().isoformat(),
        "version": "A.I.N.D.Y. v1.0.0",
        "components": {},
        "api_endpoints": {},
        "status": "unknown"
    }

    # --- Component checks ----------------------------------------------------
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status["components"]["database"] = "connected"
    except Exception as e:
        status["components"]["database"] = f"error: {str(e)}"

    try:
        nltk.data.find("tokenizers/punkt")
        nltk.data.find("tokenizers/punkt_tab")
        status["components"]["nltk"] = "available"
    except LookupError:
        status["components"]["nltk"] = "missing"

    try:
        import seo_services
        status["components"]["seo_analyzer"] = (
            "ready" if hasattr(seo_services, "seo_analysis") else "not loaded"
        )
    except Exception as e:
        status["components"]["seo_analyzer"] = f"error: {str(e)}"

    try:
        import memory_persistence
        status["components"]["memory_bridge"] = (
            "ready" if hasattr(memory_persistence, "MemoryNodeDAO") else "not loaded"
        )
    except Exception as e:
        status["components"]["memory_bridge"] = f"error: {str(e)}"

    # --- Live endpoint pings -------------------------------------------------
    base_url = "http://127.0.0.1:8000"
    endpoints = {
        "calculate_twr": {"url": f"{base_url}/calculate_twr", "payload": {"returns": [0.1, 0.05, 0.2]}},
        "seo_analyze": {"url": f"{base_url}/tools/seo/analyze", "payload": {"text": "AI Search Optimization", "top_n": 3}},
        "seo_meta": {"url": f"{base_url}/tools/seo/meta", "payload": {"url": "https://example.com"}}
    }

    latencies = []
    for name, cfg in endpoints.items():
        start = time.time()
        try:
            r = requests.post(cfg["url"], json=cfg["payload"], timeout=5)
            elapsed = round((time.time() - start) * 1000, 2)
            latencies.append(elapsed)
            status["api_endpoints"][name] = {
                "status_code": r.status_code,
                "latency_ms": elapsed,
                "result": "ok" if r.status_code == 200 else "fail"
            }
        except Exception as e:
            elapsed = round((time.time() - start) * 1000, 2)
            status["api_endpoints"][name] = {"error": str(e), "latency_ms": elapsed, "result": "fail"}

    # --- Summary -------------------------------------------------------------
    criticals = [v for v in status["components"].values() if "error" in str(v).lower() or v == "missing"]
    fails = [v for v in status["api_endpoints"].values() if v.get("result") != "ok"]
    status["status"] = "healthy" if not criticals and not fails else "degraded"
    avg_latency = statistics.mean(latencies) if latencies else 0
    status["avg_latency_ms"] = avg_latency

    # --- Log to database -----------------------------------------------------
    try:
        log = SystemHealthLog(
            status=status["status"],
            components=status["components"],
            api_endpoints=status["api_endpoints"],
            avg_latency_ms=avg_latency
        )
        db.add(log)
        db.commit()
    except Exception as e:
        print(f"[HealthLog] DB logging error: {e}")

    return status