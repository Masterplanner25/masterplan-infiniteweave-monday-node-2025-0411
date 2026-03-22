import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
import nltk, time, requests, statistics, os, logging

from db.database import get_db, engine
from db.models.system_health_log import SystemHealthLog

router = APIRouter(prefix="/health", tags=["Health"])
logger = logging.getLogger(__name__)

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
        from services import seo_services
        status["components"]["seo_analyzer"] = (
            "ready" if hasattr(seo_services, "seo_analysis") else "not loaded"
        )
    except Exception as e:
        status["components"]["seo_analyzer"] = f"error: {str(e)}"

    try:
        from services import memory_persistence
        status["components"]["memory_bridge"] = (
            "ready" if hasattr(memory_persistence, "MemoryNodeDAO") else "not loaded"
        )
    except Exception as e:
        status["components"]["memory_bridge"] = f"error: {str(e)}"

    # --- Live endpoint pings -------------------------------------------------
    base_url = os.getenv("HEALTH_CHECK_BASE_URL", "http://127.0.0.1:8000")
    auth_token = os.getenv("HEALTH_CHECK_TOKEN")
    auth_headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else None
    endpoints = {
        "calculate_twr": {
            "url": f"{base_url}/calculate_twr",
            "payload": {
                "task_name": "health_check",
                "time_spent": 1.0,
                "task_complexity": 1,
                "skill_level": 1,
                "ai_utilization": 1,
                "task_difficulty": 1,
            },
            "requires_auth": True,
        },
        "seo_analyze": {
            "url": f"{base_url}/seo/analyze",
            "payload": {"text": "AI Search Optimization", "top_n": 3},
            "requires_auth": True,
        },
        "seo_meta": {
            "url": f"{base_url}/seo/meta",
            "payload": {"text": "AI Search Optimization", "limit": 160},
            "requires_auth": True,
        },
        "memory_metrics": {
            "url": f"{base_url}/memory/metrics",
            "method": "get",
            "payload": None,
            "requires_auth": True,
        },
    }

    latencies = []
    for name, cfg in endpoints.items():
        start = time.time()
        try:
            if cfg.get("requires_auth") and not auth_headers:
                status["api_endpoints"][name] = {"result": "skipped_auth"}
                continue
            method = cfg.get("method", "post").lower()
            if method == "get":
                r = requests.get(cfg["url"], headers=auth_headers, timeout=5)
            else:
                r = requests.post(cfg["url"], json=cfg["payload"], headers=auth_headers, timeout=5)
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
    fails = [
        v for v in status["api_endpoints"].values()
        if v.get("result") not in ("ok", "skipped_auth")
    ]
    status["status"] = "healthy" if not criticals and not fails else "degraded"
    avg_latency = statistics.mean(latencies) if latencies else 0
    status["avg_latency_ms"] = avg_latency
    log_payload = {
        "event": "health_check",
        "route": "/health",
        "status": status["status"],
        "avg_latency_ms": avg_latency,
        "components_ok": sum(1 for v in status["components"].values() if "error" not in str(v).lower() and v != "missing"),
        "components_total": len(status["components"]),
        "endpoints_failed": sum(
            1
            for v in status["api_endpoints"].values()
            if v.get("result") not in ("ok", "skipped_auth")
        ),
        "endpoints_total": len(status["api_endpoints"]),
    }
    logger.info(json.dumps(log_payload, ensure_ascii=False))

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
        logger.warning("[HealthLog] DB logging error: %s", e)

    return status
