"""
main.py — IOB Nagapattinam RO Lead Generation Pipeline
Run all tasks in sequence with full logging and summary reporting.

Usage:
    python main.py                    # Run full pipeline
    python main.py --task mca         # Run only MCA fetch
    python main.py --task udyam       # Run only Udyam fetch
    python main.py --task gem         # Run only GeM fetch
    python main.py --task score       # Score + merge existing CSVs
    python main.py --task push        # Push existing master_leads.csv to Sheets
    python main.py --task alert       # Send test alert
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime

import pandas as pd

import config
from alerts import send_alerts

# ── Logging setup ─────────────────────────────────────────────────────────────

os.makedirs(config.LOGS_DIR, exist_ok=True)
os.makedirs(config.DATA_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.PIPELINE_LOG, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")


# ── Banner ────────────────────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════════╗
║   Indian Overseas Bank — Nagapattinam Regional Office    ║
║          Automated Lead Generation Pipeline              ║
║   Districts: Nagapattinam | Thiruvarur | Mayiladuthurai  ║
╚══════════════════════════════════════════════════════════╝
"""


# ── Individual task runners ───────────────────────────────────────────────────

def run_mca() -> pd.DataFrame:
    from fetch_mca import fetch_mca_data
    print("\n" + "="*58)
    print("  TASK 1 — MCA21 Company Registrations")
    print("="*58)
    df = fetch_mca_data()
    logger.info("MCA fetch complete: %d records", len(df))
    return df


def run_udyam() -> tuple[pd.DataFrame, pd.DataFrame]:
    from fetch_udyam import fetch_udyam_data
    print("\n" + "="*58)
    print("  TASK 2 — Udyam MSME Registrations")
    print("="*58)
    df_mfg, df_svc = fetch_udyam_data()
    logger.info("Udyam fetch complete: %d manufacturing, %d services",
                len(df_mfg), len(df_svc))
    return df_mfg, df_svc


def run_gem() -> pd.DataFrame:
    from fetch_gem import fetch_gem_data
    print("\n" + "="*58)
    print("  TASK 3 — GeM Portal Sellers")
    print("="*58)
    df = fetch_gem_data()
    logger.info("GeM fetch complete: %d records", len(df))
    return df


def run_score(df_mca, df_mfg, df_svc, df_gem) -> pd.DataFrame:
    from score_leads import build_master_leads
    print("\n" + "="*58)
    print("  TASK 4 — Scoring & Building Master Leads")
    print("="*58)
    master = build_master_leads(df_mca, df_mfg, df_svc, df_gem)
    logger.info("Scoring complete: %d total leads", len(master))
    return master


def run_push(master: pd.DataFrame) -> int:
    from push_to_sheets import push_to_sheets
    print("\n" + "="*58)
    print("  TASK 5 — Pushing to Google Sheets")
    print("="*58)
    n = push_to_sheets(master)
    logger.info("Google Sheets push: %d new rows", n)
    return n


# ── Full pipeline ─────────────────────────────────────────────────────────────

def run_full_pipeline() -> dict:
    start = time.time()
    print(BANNER)
    logger.info("Pipeline started at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Task 1
    df_mca = run_mca()

    # Task 2
    df_mfg, df_svc = run_udyam()

    # Task 3
    df_gem = run_gem()

    # Task 4
    master = run_score(df_mca, df_mfg, df_svc, df_gem)

    # Task 5
    sheets_count = run_push(master)

    elapsed = round(time.time() - start, 1)

    # Build summary for alerts
    top5 = master.head(5).to_dict("records") if not master.empty else []
    summary = {
        "mca_count":   len(df_mca),
        "msme_count":  len(df_mfg) + len(df_svc),
        "gem_count":   len(df_gem),
        "total_leads": len(master),
        "top5":        top5,
        "run_time":    f"{elapsed}s",
        "sheets_new":  sheets_count,
    }

    logger.info(
        "Pipeline complete in %ss — MCA:%d MSME:%d GeM:%d Total:%d Sheets:%d",
        elapsed, summary["mca_count"], summary["msme_count"],
        summary["gem_count"], summary["total_leads"], sheets_count,
    )

    # Task 6 partial — send alerts
    print("\n" + "="*58)
    print("  TASK 6 — Sending Alerts")
    print("="*58)
    send_alerts(summary)

    print(f"\n{'='*58}")
    print(f"  Pipeline finished in {elapsed}s")
    print(f"  Log: {config.PIPELINE_LOG}")
    print(f"{'='*58}\n")

    return summary


# ── CLI entry point ───────────────────────────────────────────────────────────

def _load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


def main():
    parser = argparse.ArgumentParser(
        description="IOB Nagapattinam Lead Generation Pipeline"
    )
    parser.add_argument(
        "--task",
        choices=["mca", "udyam", "gem", "score", "push", "alert", "all"],
        default="all",
        help="Which task to run (default: all)",
    )
    args = parser.parse_args()

    if args.task == "all":
        run_full_pipeline()

    elif args.task == "mca":
        run_mca()

    elif args.task == "udyam":
        run_udyam()

    elif args.task == "gem":
        run_gem()

    elif args.task == "score":
        df_mca = _load_csv(config.MCA_CSV_OUT)
        df_mfg = _load_csv(config.UDYAM_MFG_CSV_OUT)
        df_svc = _load_csv(config.UDYAM_SVC_CSV_OUT)
        df_gem = _load_csv(config.GEM_CSV_OUT)
        run_score(df_mca, df_mfg, df_svc, df_gem)

    elif args.task == "push":
        master = _load_csv(config.MASTER_LEADS_CSV_OUT)
        run_push(master)

    elif args.task == "alert":
        master = _load_csv(config.MASTER_LEADS_CSV_OUT)
        top5 = master.head(5).to_dict("records") if not master.empty else []
        send_alerts({
            "mca_count": 0, "msme_count": 0, "gem_count": 0,
            "total_leads": len(master), "top5": top5, "run_time": "test",
        })


if __name__ == "__main__":
    main()
