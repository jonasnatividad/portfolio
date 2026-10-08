"""Generate synthetic CSV exports for a fictional B2B SaaS sales team.

Writes to ../sample_data/:
  companies_2026-09-30.csv   accounts exported from the CRM
  deals_2026-09-30.csv       opportunity export, day 1
  deals_2026-10-01.csv       opportunity export, day 2 (some deals moved stage)

All names are invented from word lists. The files are deliberately a little
messy (stray spaces, mixed-case stages, "$1,200.00" amounts, a duplicate row,
a blank amount) so the clean layer has real work to do.

Usage: python generate_sample_data.py [--seed 7]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "sample_data"

PREFIXES = ["North", "Blue", "Bright", "Granite", "Cedar", "Harbor", "Summit", "Copper", "Lumen", "Maple",
            "Quarry", "Signal", "Tidal", "Vector", "Willow", "Juniper", "Orbit", "Pioneer", "Atlas", "Kestrel"]
SUFFIXES = ["Foods", "Logistics", "Dental", "Robotics", "Outfitters", "Analytics", "Studios", "Clinics",
            "Builders", "Freight", "Labs", "Hospitality", "Supply", "Energy", "Fitness"]
FORMS = ["Inc", "LLC", "Co", "Group", "Ltd"]
INDUSTRIES = {"Foods": "Food & Beverage", "Logistics": "Transportation", "Dental": "Healthcare",
              "Robotics": "Manufacturing", "Outfitters": "Retail", "Analytics": "Software",
              "Studios": "Media", "Clinics": "Healthcare", "Builders": "Construction",
              "Freight": "Transportation", "Labs": "Software", "Hospitality": "Hospitality",
              "Supply": "Wholesale", "Energy": "Energy", "Fitness": "Consumer Services"}
EMPLOYEE_BANDS = ["1-10", "11-50", "51-200", "201-1000", "1000+"]
COUNTRIES = ["US", "US", "US", "CA", "GB", "AU", "DE"]
REPS = ["Avery Stone", "Jordan Lee", "Morgan Diaz", "Riley Chen", "Casey Patel"]
PLANS = {"Starter": (3_000, 9_000), "Growth": (12_000, 40_000), "Enterprise": (60_000, 180_000)}
STAGES = ["Prospecting", "Discovery", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]


def messy_stage(stage: str, rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.1:
        return stage.upper()
    if roll < 0.2:
        return f" {stage.lower()} "
    return stage


def messy_amount(amount: int, rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.15:
        return f"${amount:,.2f}"
    if roll < 0.18:
        return ""
    return str(amount)


def make_companies(rng: random.Random, n: int = 60) -> list[dict]:
    names: set[str] = set()
    rows = []
    while len(rows) < n:
        prefix, suffix = rng.choice(PREFIXES), rng.choice(SUFFIXES)
        name = f"{prefix} {suffix} {rng.choice(FORMS)}"
        if name in names:
            continue
        names.add(name)
        created = dt.date(2025, 1, 1) + dt.timedelta(days=rng.randint(0, 600))
        rows.append({
            "company_id": f"C{1000 + len(rows)}",
            "company_name": name if rng.random() > 0.1 else f"  {name}",
            "industry": INDUSTRIES[suffix],
            "employee_band": rng.choice(EMPLOYEE_BANDS),
            "country": rng.choice(COUNTRIES),
            "account_owner": rng.choice(REPS),
            "created_date": created.isoformat(),
        })
    return rows


def make_deals(rng: random.Random, companies: list[dict], n: int = 180) -> list[dict]:
    rows = []
    for i in range(n):
        company = rng.choice(companies)
        plan = rng.choices(list(PLANS), weights=[5, 4, 1])[0]
        low, high = PLANS[plan]
        created = dt.date(2026, 1, 5) + dt.timedelta(days=rng.randint(0, 260))
        stage = rng.choices(STAGES, weights=[14, 14, 12, 8, 18, 14])[0]
        close = created + dt.timedelta(days=rng.randint(14, 120))
        rows.append({
            "deal_id": f"D{5000 + i}",
            "company_id": company["company_id"],
            "deal_name": f"{company['company_name'].strip()} - {plan}",
            "plan": plan,
            "stage": stage,
            "amount_usd": round(rng.randint(low, high), -2),
            "owner": company["account_owner"],
            "created_date": created.isoformat(),
            "expected_close_date": close.isoformat(),
            "last_updated_at": f"2026-09-30T{rng.randint(8, 18):02d}:{rng.randint(0, 59):02d}:00Z",
        })
    return rows


def advance(rng: random.Random, deals: list[dict]) -> list[dict]:
    """Day-2 export: about 15% of open deals move one stage forward or are lost."""
    out = []
    for d in deals:
        d = dict(d)
        if d["stage"] not in ("Closed Won", "Closed Lost") and rng.random() < 0.15:
            idx = STAGES.index(d["stage"])
            d["stage"] = "Closed Lost" if rng.random() < 0.25 else STAGES[min(idx + 1, 4)]
            d["last_updated_at"] = f"2026-10-01T{rng.randint(8, 18):02d}:{rng.randint(0, 59):02d}:00Z"
        out.append(d)
    return out


def write_deals(path: Path, deals: list[dict], rng: random.Random) -> None:
    rows = []
    for d in deals:
        r = dict(d)
        r["stage"] = messy_stage(r["stage"], rng)
        r["amount_usd"] = messy_amount(int(r["amount_usd"]), rng)
        rows.append(r)
    rows.append(dict(rows[3]))  # an exact duplicate, as real exports sometimes contain
    write_csv(path, rows)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path.name}: {len(rows)} rows")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    rng = random.Random(args.seed)

    companies = make_companies(rng)
    deals_day1 = make_deals(rng, companies)
    deals_day2 = advance(rng, deals_day1)

    write_csv(OUT / "companies_2026-09-30.csv", companies)
    write_deals(OUT / "deals_2026-09-30.csv", deals_day1, rng)
    write_deals(OUT / "deals_2026-10-01.csv", deals_day2, rng)


if __name__ == "__main__":
    main()
