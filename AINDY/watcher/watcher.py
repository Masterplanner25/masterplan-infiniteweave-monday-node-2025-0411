"""
watcher.py — A.I.N.D.Y. Watcher main loop.

Usage:
    python -m watcher.watcher [--dry-run] [--poll-interval N] [--log-level LEVEL]

    --dry-run           Log signals instead of sending HTTP requests
    --poll-interval N   Override polling interval in seconds (default: 5)
    --log-level LEVEL   DEBUG|INFO|WARNING|ERROR (default: INFO)

Signals:
    SIGINT / SIGTERM → graceful shutdown (flushes remaining signals)

Environment:
    All settings can be configured via environment variables.
    See watcher/config.py for the full list.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from typing import Optional

# Ensure watcher package is importable when run as __main__
_WATCHER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WATCHER_ROOT not in sys.path:
    sys.path.insert(0, _WATCHER_ROOT)

from watcher import classifier, config
from watcher.session_tracker import SessionTracker
from watcher.signal_emitter import SignalEmitter
from watcher.window_detector import get_active_window


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )


def _build_emitter(cfg: config.WatcherConfig) -> SignalEmitter:
    return SignalEmitter(
        api_url=cfg.signals_endpoint,
        api_key=cfg.api_key,
        flush_interval=cfg.flush_interval,
        batch_size=cfg.batch_size,
        dry_run=cfg.dry_run,
    )


def _build_tracker(cfg: config.WatcherConfig) -> SessionTracker:
    return SessionTracker(
        confirmation_delay=cfg.confirmation_delay,
        distraction_timeout=cfg.distraction_timeout,
        recovery_delay=cfg.recovery_delay,
        heartbeat_interval=cfg.heartbeat_interval,
    )


def run(cfg: config.WatcherConfig) -> None:
    """
    Main sampling loop. Blocks until SIGINT/SIGTERM or KeyboardInterrupt.
    """
    logger = logging.getLogger("watcher.main")
    emitter = _build_emitter(cfg)
    tracker = _build_tracker(cfg)

    shutdown_requested = False

    def _on_signal(signum, frame):  # noqa: ARG001
        nonlocal shutdown_requested
        logger.info("Shutdown signal received (%s)", signum)
        shutdown_requested = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    emitter.start()
    logger.info(
        "A.I.N.D.Y. Watcher started | poll=%.1fs | dry_run=%s | endpoint=%s",
        cfg.poll_interval,
        cfg.dry_run,
        cfg.signals_endpoint,
    )

    try:
        while not shutdown_requested:
            try:
                window = get_active_window()
                result = classifier.classify(window)
                events = tracker.update(result)
                if events:
                    emitter.emit_many(events)
                    for e in events:
                        logger.debug(
                            "Event: %s | session=%s | app=%s | state=%s",
                            e.signal_type,
                            e.session_id,
                            e.app_name,
                            tracker.state,
                        )
            except Exception as exc:
                # Never crash the main loop
                logger.error("Watcher loop error (non-fatal): %s", exc)

            time.sleep(cfg.poll_interval)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down")
    finally:
        logger.info("Flushing remaining signals...")
        emitter.stop(drain_timeout=10.0)
        logger.info("A.I.N.D.Y. Watcher stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="A.I.N.D.Y. Watcher")
    parser.add_argument("--dry-run", action="store_true", help="Log signals only, no HTTP")
    parser.add_argument("--poll-interval", type=float, default=None, help="Polling interval (seconds)")
    parser.add_argument("--log-level", default=None, help="Logging level")
    args = parser.parse_args()

    cfg = config.load()

    # CLI overrides
    if args.dry_run:
        os.environ["AINDY_WATCHER_DRY_RUN"] = "true"
        cfg = config.load()
    if args.poll_interval is not None:
        cfg.poll_interval = args.poll_interval
    if args.log_level is not None:
        cfg.log_level = args.log_level.upper()

    _configure_logging(cfg.log_level)
    logger = logging.getLogger("watcher.main")

    errors = config.validate(cfg)
    if errors:
        for err in errors:
            logger.error("Config error: %s", err)
        sys.exit(1)

    run(cfg)


if __name__ == "__main__":
    main()
