"""
Demo mode — generates realistic sample leads for all 3 districts.
Use this to test the full pipeline (scoring, Sheets push, alerts)
without needing access to government APIs.

Run:  python demo_data.py
"""

import os
import pandas as pd
from datetime import datetime, timedelta
import random

import config

random.seed(42)

# ── Sample company names ──────────────────────────────────────────────────────

MFG_NAMES = [
    "Kaveri Rice Mills Pvt Ltd", "Nagapattinam Cashew Processing Ltd",
    "Delta Prawn Feeds Industries", "Velankanni Sea Foods Pvt Ltd",
    "Mayiladuthurai Textile Mills", "Thiruvarur Agro Products Ltd",
    "Cauvery Coir Industries Pvt Ltd", "Poompuhar Handicrafts Ltd",
    "Sirkazhi Salt Works Pvt Ltd", "Nagore Boat Building Pvt Ltd",
    "Papanasam Paper Mills Ltd", "Kumbakonam Brass Works Pvt Ltd",
    "Delta Aqua Hatcheries Pvt Ltd", "Vedaranyam Salt Packers Ltd",
    "Tranquebar Handloom Weavers Ltd",
]

SVC_NAMES = [
    "Nagapattinam IT Solutions Pvt Ltd", "Poompuhar Digital Services",
    "Delta Coastal Logistics Ltd", "Cauvery Transport & Cargo",
    "Mayiladuthurai Agri Consultants", "Thiruvarur Health Services Pvt Ltd",
    "Nagapattinam Education Trust", "Velankanni Tourism Pvt Ltd",
    "Sirkazhi Micro Finance Ltd", "Kumbakonam Software Solutions",
]

TRADE_NAMES = [
    "Nagapattinam Traders Association", "Delta Marine Exports",
    "Thiruvarur Fertilizer Distributors", "Mayiladuthurai Auto Parts",
    "Cauvery Hardware Merchants", "Poompuhar Wholesale Market",
]

CONSTRUCT_NAMES = [
    "Nagapattinam Civil Contractors", "Delta Infra Builders Pvt Ltd",
    "Cauvery Bridge Constructions Ltd", "Thiruvarur Housing Projects",
]

TALUKS = {
    "Nagapattinam": ["Nagapattinam", "Kilvelur", "Vedaranyam", "Nagore", "Sirkazhi"],
    "Thiruvarur":   ["Thiruvarur", "Papanasam", "Nannilam", "Mannargudi", "Valangaiman"],
    "Mayiladuthurai": ["Mayiladuthurai", "Sirkazhi", "Poompuhar", "Tranquebar", "Sembanarkoil"],
}

DIRECTORS = [
    "R. Murugesan", "K. Selvaraj", "S. Palanivel", "A. Krishnamoorthy",
    "P. Ramasamy", "V. Sundaram", "M. Arumugam", "T. Natarajan",
    "C. Subramaniam", "G. Venkatesan", "L. Balasubramanian", "N. Annamalai",
]


def _rand_cin():
    return f"U{random.randint(10000,99999)}TN{random.randint(2010,2025)}PTC{random.randint(100000,999999)}"


def _rand_udyam():
    return f"UDYAM-TN-{random.randint(10,35):02d}-{random.randint(1000000,9999999):07d}"


def _rand_date(start_year=2020, end_year=2026):
    start = datetime(start_year, 1, 1)
    end   = datetime(end_year, 4, 30)
    delta = (end - start).days
    return (start + timedelta(days=random.randint(0, delta))).strftime("%d/%m/%Y")


def _rand_capital():
    tiers = [
        (50_000,   500_000),    # small
        (500_001,  2_000_000),  # medium
        (2_000_001, 10_000_000), # above 10L
        (10_000_001, 50_000_000),
    ]
    lo, hi = random.choice(tiers)
    return random.randint(lo, hi)


def _rand_email(name):
    slug = name.lower().split()[0].replace(".", "")
    return f"{slug}@{random.choice(['gmail.com','yahoo.com','business.in','company.co.in'])}"


def _rand_phone():
    return f"+91{random.choice(['94','95','96','97','98','99'])}{random.randint(10000000,99999999)}"


# ── Generators ────────────────────────────────────────────────────────────────

def _make_mca_record(name, sector, district):
    has_contact = random.random() > 0.35
    return {
        "SOURCE": "MCA21",
        "DISTRICT": district,
        "TALUK": random.choice(TALUKS[district]),
        "SECTOR": sector,
        "COMPANY_NAME": name,
        "CIN_OR_UDYAM_NO": _rand_cin(),
        "INCORPORATION_DATE": _rand_date(2020, 2026),
        "AUTHORIZED_CAPITAL": _rand_capital(),
        "DIRECTOR_NAMES": random.choice(DIRECTORS),
        "EMAIL": _rand_email(name) if has_contact else "",
        "PHONE": _rand_phone() if has_contact else "",
        "ADDRESS": f"{random.randint(1,100)}, {random.choice(['Gandhi Nagar','Anna Salai','Nehru Street','Station Road'])}, {district} - {random.randint(609000,614100)}",
        "HAS_GST": random.choice(["true", "true", "true", "false"]),
        "GEM_REGISTERED": False,
        "BANK_PRODUCT": "",
        "SCORE": 0,
    }


def _make_udyam_record(name, sector, district):
    has_contact = random.random() > 0.4
    return {
        "SOURCE": "Udyam",
        "DISTRICT": district,
        "TALUK": random.choice(TALUKS[district]),
        "SECTOR": sector,
        "COMPANY_NAME": name,
        "CIN_OR_UDYAM_NO": _rand_udyam(),
        "INCORPORATION_DATE": _rand_date(2019, 2026),
        "AUTHORIZED_CAPITAL": 0.0,
        "DIRECTOR_NAMES": random.choice(DIRECTORS),
        "EMAIL": _rand_email(name) if has_contact else "",
        "PHONE": _rand_phone() if has_contact else "",
        "ADDRESS": f"Plot {random.randint(1,50)}, SIDCO Industrial Estate, {district}",
        "HAS_GST": random.choice(["true", "true", "false"]),
        "GEM_REGISTERED": False,
        "BANK_PRODUCT": "",
        "SCORE": 0,
    }


def _make_gem_record(name, sector, district):
    return {
        "SOURCE": "GeM",
        "DISTRICT": district,
        "TALUK": random.choice(TALUKS[district]),
        "SECTOR": sector,
        "COMPANY_NAME": name,
        "CIN_OR_UDYAM_NO": _rand_udyam(),
        "INCORPORATION_DATE": _rand_date(2021, 2026),
        "AUTHORIZED_CAPITAL": 0.0,
        "DIRECTOR_NAMES": random.choice(DIRECTORS),
        "EMAIL": _rand_email(name),
        "PHONE": _rand_phone(),
        "ADDRESS": f"{random.randint(1,80)}, Main Road, {district}",
        "HAS_GST": "true",
        "GEM_REGISTERED": True,
        "BANK_PRODUCT": "",
        "SCORE": 0,
    }


# ── Public entry point ────────────────────────────────────────────────────────

def generate_demo_data():
    """
    Create realistic sample CSVs for all three sources.
    Returns (df_mca, df_mfg, df_svc, df_gem).
    """
    os.makedirs(config.DATA_DIR, exist_ok=True)
    all_districts = config.DISTRICTS

    # ── MCA records ───────────────────────────────────────────
    mca_rows = []
    for district in all_districts:
        for name in random.sample(MFG_NAMES, 5):
            mca_rows.append(_make_mca_record(name + f" ({district[:3]})", "Manufacturing", district))
        for name in random.sample(SVC_NAMES, 3):
            mca_rows.append(_make_mca_record(name + f" ({district[:3]})", "Services", district))
        for name in random.sample(TRADE_NAMES, 2):
            mca_rows.append(_make_mca_record(name + f" ({district[:3]})", "Trading", district))
        for name in random.sample(CONSTRUCT_NAMES, 1):
            mca_rows.append(_make_mca_record(name + f" ({district[:3]})", "Construction", district))

    df_mca = pd.DataFrame(mca_rows)
    df_mca.to_csv(config.MCA_CSV_OUT, index=False, encoding="utf-8-sig")
    df_mca.to_json(config.MCA_JSON_OUT, orient="records", indent=2, force_ascii=False)
    print(f"[Demo] MCA     : {len(df_mca)} records → {config.MCA_CSV_OUT}")

    # ── Udyam Manufacturing ────────────────────────────────────
    mfg_rows = []
    for district in all_districts:
        for name in random.sample(MFG_NAMES, 6):
            mfg_rows.append(_make_udyam_record(name + f" [Udyam-{district[:3]}]", "Manufacturing", district))

    df_mfg = pd.DataFrame(mfg_rows)
    df_mfg.to_csv(config.UDYAM_MFG_CSV_OUT, index=False, encoding="utf-8-sig")
    print(f"[Demo] MSME Mfg: {len(df_mfg)} records → {config.UDYAM_MFG_CSV_OUT}")

    # ── Udyam Services ─────────────────────────────────────────
    svc_rows = []
    for district in all_districts:
        for name in random.sample(SVC_NAMES, 4):
            svc_rows.append(_make_udyam_record(name + f" [Udyam-{district[:3]}]", "Services", district))

    df_svc = pd.DataFrame(svc_rows)
    df_svc.to_csv(config.UDYAM_SVC_CSV_OUT, index=False, encoding="utf-8-sig")
    print(f"[Demo] MSME Svc: {len(df_svc)} records → {config.UDYAM_SVC_CSV_OUT}")

    # ── GeM sellers ────────────────────────────────────────────
    gem_rows = []
    gem_pool = MFG_NAMES[:6] + SVC_NAMES[:4] + TRADE_NAMES[:3]
    for district in all_districts:
        for name in random.sample(gem_pool, 5):
            sector = ("Manufacturing" if name in MFG_NAMES
                      else "Services" if name in SVC_NAMES else "Trading")
            gem_rows.append(_make_gem_record(name + f" [GeM-{district[:3]}]", sector, district))

    df_gem = pd.DataFrame(gem_rows)
    df_gem.to_csv(config.GEM_CSV_OUT, index=False, encoding="utf-8-sig")
    print(f"[Demo] GeM     : {len(df_gem)} records → {config.GEM_CSV_OUT}")

    total = len(df_mca) + len(df_mfg) + len(df_svc) + len(df_gem)
    print(f"\n[Demo] Total sample records generated: {total}")
    return df_mca, df_mfg, df_svc, df_gem


if __name__ == "__main__":
    print("Generating demo data for pipeline test ...\n")
    generate_demo_data()
    print("\nNow run:  python main.py --task score")
    print("     then: python main.py --task push")
