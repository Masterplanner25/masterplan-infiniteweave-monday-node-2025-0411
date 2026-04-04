"""
Scheduled Execution Agent — A.I.N.D.Y. example project

Sets up a self-running daily intelligence agent. After `python main.py setup`,
the server runs the briefing autonomously every morning at 09:00 with no
further involvement.

Usage:
    python main.py setup  [--cron EXPR] [--webhook URL]
    python main.py run-now
    python main.py status
    python main.py cancel
    python main.py history [--limit N]

Environment:
    AINDY_BASE_URL   Server URL (default: http://localhost:8000)
    AINDY_API_KEY    Platform API key (required)
"""
# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SDK_PATH = Path(__file__).resolve().parents[2] / "sdk"
if SDK_PATH.exists() and str(SDK_PATH) not in sys.path:
    sys.path.insert(0, str(SDK_PATH))

from aindy import AINDYClient, AINDYError
from briefing import print_briefing_box, print_briefing_history

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL    = os.environ.get("AINDY_BASE_URL", "http://localhost:8000")
API_KEY     = os.environ.get("AINDY_API_KEY", "")
CONFIG_FILE = Path(__file__).parent / "data" / "schedule_config.json"
NODUS_FILE  = Path(__file__).parent / "nodus" / "daily_briefing.nodus"

# ── Helpers ───────────────────────────────────────────────────────────────────

def header() -> None:
    print("\n" + "━" * 45)
    print("  Scheduled Execution Agent")
    print("━" * 45)


def make_client() -> AINDYClient:
    if not API_KEY:
        print("ERROR: Set AINDY_API_KEY environment variable.")
        sys.exit(1)
    return AINDYClient(base_url=BASE_URL, api_key=API_KEY)


def load_config() -> dict:
    with open(CONFIG_FILE) as f:
        return json.load(f)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_setup(client: AINDYClient, cron_override: str | None, webhook_override: str | None) -> None:
    config = load_config()
    sched  = config["schedule"]
    wh     = config["webhook"]

    cron_expr   = cron_override or sched["cron_expr"]
    namespace   = sched["namespace"]
    webhook_url = webhook_override or wh["callback_url"]

    # 1. Upload Nodus script
    print("\n[setup] Uploading Nodus script...")
    with open(NODUS_FILE) as f:
        source = f.read()
    client.nodus.upload_script("daily_briefing", source, overwrite=True)
    print("  ✓ daily_briefing uploaded")

    # 2. Seed sample memory data
    print("\n[setup] Seeding sample memory data...")
    seed_count = 0
    for node in config.get("seed_nodes", []):
        try:
            client.memory.write(
                path=node["path"],
                content=node["content"],
                tags=node.get("tags", []),
                node_type=node.get("node_type", "outcome"),
                extra=node.get("extra", {}),
            )
            seed_count += 1
        except AINDYError as e:
            print(f"  ✗ Seed failed: {e.message}")
    print(f"  ✓ {seed_count} nodes written to {namespace}/")

    # 3. Create the cron schedule
    print("\n[setup] Creating cron schedule...")
    try:
        # Cancel any existing schedule with the same name
        try:
            client.delete(f"/platform/nodus/schedule/{sched['name']}")
        except AINDYError:
            pass

        schedule = client.post("/platform/nodus/schedule", {
            "name":      sched["name"],
            "flow_name": "daily_briefing",
            "cron_expr": cron_expr,
            "state":     {"namespace": namespace},
        })
        print("  ✓ Schedule created")
        print(f"    name:     {schedule.get('name', sched['name'])}")
        print(f"    cron:     {cron_expr}")
        print(f"    next run: {schedule.get('next_run_at', 'calculated at next tick')}")
    except AINDYError as e:
        print(f"  ✗ Schedule failed: {e.message}")

    # 4. Subscribe webhook
    print("\n[setup] Subscribing webhook...")
    if "webhook.site/replace" in webhook_url:
        print("  ⚠ Webhook URL not configured.")
        print("    Edit data/schedule_config.json → webhook.callback_url")
        print("    or run: python main.py setup --webhook https://your-url/hook")
    else:
        try:
            client.post("/platform/webhooks", {
                "event_type":   wh["event_type"],
                "callback_url": webhook_url,
                "secret":       wh.get("secret", ""),
            })
            print(f"  ✓ Webhook registered for {wh['event_type']}")
            print(f"    delivery: {webhook_url}")
        except AINDYError as e:
            print(f"  ✗ Webhook failed: {e.message}")

    print(f"\nDone. The agent will run {_cron_description(cron_expr)}.")
    print("Run `python main.py run-now` to test immediately.")


def cmd_run_now(client: AINDYClient) -> None:
    config    = load_config()
    namespace = config["schedule"]["namespace"]

    print("\n[run-now] Triggering daily briefing...")
    result = client.nodus.run_script(
        script_name="daily_briefing",
        input={"namespace": namespace},
    )

    status   = result.get("nodus_status") or result.get("status")
    duration = result.get("duration_ms", "?")
    print(f"  Status:    {status}")
    print(f"  Duration:  {duration}ms")

    if status in ("success", "SUCCESS"):
        print("\n  Briefing written to memory:")
        print_briefing_box(result.get("output_state", {}))
        ev_count = result.get("events_emitted", 0)
        print("  Event emitted: daily.briefing.ready")
        if ev_count:
            print("  Webhook queued: checking subscriptions...")
    else:
        err = result.get("error") or result.get("output_state", {})
        print(f"  Error: {err}")


def cmd_status(client: AINDYClient) -> None:
    config    = load_config()
    sched     = config["schedule"]
    namespace = sched["namespace"]

    print()
    try:
        jobs = client.get("/platform/nodus/schedule")
        job  = next(
            (j for j in jobs.get("jobs", []) if j["name"] == sched["name"]),
            None,
        )
        if not job:
            print("No active schedule. Run `python main.py setup`.")
            return

        print(f"Schedule:   {job['name']}")
        print(f"Cron:       {job['cron_expr']}")
        print(f"Next run:   {job.get('next_run_at', '—')}")
        print(f"Last run:   {job.get('last_run_at', 'never')}")
        print(f"Active:     {'yes' if job.get('is_active') else 'no'}")
    except AINDYError as e:
        print(f"Could not fetch schedule: {e.message}")
        return

    # Show recent briefings from memory
    print("\nRecent briefings:")
    try:
        result = client.memory.read(f"{namespace}/briefings/*", limit=5)
        print_briefing_history(result["data"]["nodes"])
    except AINDYError as e:
        print(f"  Could not read briefings: {e.message}")


def cmd_cancel(client: AINDYClient) -> None:
    config = load_config()
    name   = config["schedule"]["name"]

    print(f"\nCancelling schedule '{name}'...")
    try:
        client.delete(f"/platform/nodus/schedule/{name}")
        print("  ✓ Schedule cancelled.")
    except AINDYError as e:
        print(f"  ✗ {e.message}")


def cmd_history(client: AINDYClient, limit: int) -> None:
    config    = load_config()
    namespace = config["schedule"]["namespace"]

    print(f"\nBriefing history (last {limit}):")
    try:
        result = client.memory.read(
            path=f"{namespace}/briefings/*",
            limit=limit,
        )
        print_briefing_history(result["data"]["nodes"], limit=limit)
    except AINDYError as e:
        print(f"  Could not read history: {e.message}")


# ── Cron description ──────────────────────────────────────────────────────────

def _cron_description(expr: str) -> str:
    known = {
        "0 9 * * *":    "every morning at 09:00",
        "0 9,18 * * *": "at 09:00 and 18:00 every day",
        "0 9 * * MON":  "every Monday at 09:00",
        "0 0 1 * *":    "on the 1st of each month",
        "* * * * *":    "every minute (demo mode)",
        "*/5 * * * *":  "every 5 minutes",
        "*/30 * * * *": "every 30 minutes",
    }
    return known.get(expr, f"on schedule: {expr}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scheduled Execution Agent — A.I.N.D.Y. example",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("setup",   help="First-time setup: upload script, seed data, create schedule")
    sp.add_argument("--cron",    default=None, help='Override cron expression, e.g. "* * * * *"')
    sp.add_argument("--webhook", default=None, help="Override webhook delivery URL")

    sub.add_parser("run-now",  help="Trigger the briefing immediately")
    sub.add_parser("status",   help="Show schedule status and recent briefings")
    sub.add_parser("cancel",   help="Cancel the cron schedule")

    hp = sub.add_parser("history", help="Show briefing history")
    hp.add_argument("--limit", type=int, default=10)

    args = parser.parse_args()

    header()
    client = make_client()

    if args.command == "setup":
        cmd_setup(client, cron_override=args.cron, webhook_override=args.webhook)
    elif args.command == "run-now":
        cmd_run_now(client)
    elif args.command == "status":
        cmd_status(client)
    elif args.command == "cancel":
        cmd_cancel(client)
    elif args.command == "history":
        cmd_history(client, limit=args.limit)


if __name__ == "__main__":
    main()
