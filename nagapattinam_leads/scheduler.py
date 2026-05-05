"""
Task 6 — Scheduler
Runs the full pipeline automatically at 6:00 AM IST every day.

Two modes:
  1. APScheduler (default) — long-running Python process in the background.
     Start once, keep running:  nohup python scheduler.py &
  2. Cron setup helper         — prints the exact crontab line to add.

Usage:
    python scheduler.py              # Start APScheduler daemon
    python scheduler.py --mode cron  # Print crontab instructions
    python scheduler.py --run-now    # Run pipeline immediately, then start scheduler
"""

import argparse
import logging
import os
import sys
import subprocess
from datetime import datetime

import config

os.makedirs(config.LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.PIPELINE_LOG, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("scheduler")

PIPELINE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
PYTHON_EXE      = sys.executable


# ── Job function ──────────────────────────────────────────────────────────────

def run_pipeline_job():
    """APScheduler calls this at 6 AM daily."""
    logger.info("Scheduler triggered pipeline at %s",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    try:
        from main import run_full_pipeline
        summary = run_full_pipeline()
        logger.info(
            "Scheduled run complete — MCA:%d MSME:%d GeM:%d Total:%d",
            summary.get("mca_count", 0),
            summary.get("msme_count", 0),
            summary.get("gem_count", 0),
            summary.get("total_leads", 0),
        )
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)


# ── APScheduler daemon ────────────────────────────────────────────────────────

def start_apscheduler(run_now: bool = False):
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.error(
            "APScheduler not installed. Run: pip install apscheduler"
        )
        sys.exit(1)

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")

    scheduler.add_job(
        run_pipeline_job,
        trigger=CronTrigger(
            hour=config.SCHEDULE_HOUR,
            minute=config.SCHEDULE_MINUTE,
            timezone="Asia/Kolkata",
        ),
        id="lead_pipeline",
        name="IOB Nagapattinam Lead Generation",
        misfire_grace_time=3600,    # allow up to 1h late start
        coalesce=True,              # skip accumulated misfires
    )

    print(f"""
╔══════════════════════════════════════════════════════════╗
║        IOB Lead Pipeline Scheduler Started               ║
║  Next run: Daily at {config.SCHEDULE_HOUR:02d}:{config.SCHEDULE_MINUTE:02d} IST                      ║
║  Log file: {config.PIPELINE_LOG:<44}║
║  Stop    : Ctrl+C                                        ║
╚══════════════════════════════════════════════════════════╝
""")

    logger.info(
        "Scheduler started. Next run at %02d:%02d IST daily.",
        config.SCHEDULE_HOUR, config.SCHEDULE_MINUTE,
    )

    if run_now:
        logger.info("--run-now flag set: running pipeline immediately …")
        run_pipeline_job()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped by user.")
        scheduler.shutdown()


# ── Cron helper ───────────────────────────────────────────────────────────────

def print_cron_instructions():
    script_dir = os.path.dirname(os.path.abspath(PIPELINE_SCRIPT))
    log_path   = config.PIPELINE_LOG
    cron_line  = (
        f"{config.SCHEDULE_MINUTE} {config.SCHEDULE_HOUR} * * * "
        f"cd {script_dir} && {PYTHON_EXE} {PIPELINE_SCRIPT} "
        f">> {log_path} 2>&1"
    )
    print(f"""
To install this pipeline as a cron job, run:

    crontab -e

Then add this line at the bottom (runs daily at {config.SCHEDULE_HOUR:02d}:{config.SCHEDULE_MINUTE:02d} IST):

    {cron_line}

Save and exit. Verify with:

    crontab -l

To view logs:

    tail -f {log_path}

IMPORTANT: Make sure your .env file is sourced in the cron environment.
Add this line ABOVE the cron job line:

    SHELL=/bin/bash
    BASH_ENV={script_dir}/.env

Or add a wrapper script that loads the .env before calling main.py.
""")


# ── Systemd unit helper ───────────────────────────────────────────────────────

def print_systemd_instructions():
    script_dir = os.path.dirname(os.path.abspath(PIPELINE_SCRIPT))
    unit = f"""\
[Unit]
Description=IOB Nagapattinam Lead Generation Pipeline
After=network.target

[Service]
Type=simple
WorkingDirectory={script_dir}
EnvironmentFile={script_dir}/.env
ExecStart={PYTHON_EXE} {script_dir}/scheduler.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
"""
    print(f"""
To install as a systemd service (Linux only):

1. Save the following to /etc/systemd/system/iob-leads.service:

{unit}

2. Enable and start:
    sudo systemctl daemon-reload
    sudo systemctl enable iob-leads
    sudo systemctl start iob-leads

3. Check status:
    sudo systemctl status iob-leads
    journalctl -u iob-leads -f
""")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="IOB Lead Pipeline Scheduler"
    )
    parser.add_argument(
        "--mode",
        choices=["apscheduler", "cron", "systemd"],
        default="apscheduler",
        help="Scheduling backend to use",
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run pipeline immediately, then start scheduler",
    )
    args = parser.parse_args()

    if args.mode == "cron":
        print_cron_instructions()
    elif args.mode == "systemd":
        print_systemd_instructions()
    else:
        start_apscheduler(run_now=args.run_now)
