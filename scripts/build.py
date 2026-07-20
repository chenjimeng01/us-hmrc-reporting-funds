#!/usr/bin/env python3
"""Build the US-domiciled HMRC reporting funds dataset.

Fetches the current 'Approved offshore reporting funds' spreadsheet from
gov.uk, filters rows whose ISIN begins with 'US', and writes:

  docs/funds.json      - the filtered fund list (site data)
  docs/meta.json       - source file name/date, build time, counts
  docs/changelog.json  - per-refresh added/removed share classes
  data/source_meta.json- sha256 + URL of last processed source file

Exits 0 with "unchanged" if the source file hash matches the last run,
so the CI workflow can skip committing.
"""

import hashlib
import io
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PUB_URL = "https://www.gov.uk/government/publications/approved-offshore-reporting-funds"
ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA = ROOT / "data"

UA = {"User-Agent": "us-reporting-funds-tracker (github.com; monthly refresh bot)"}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def find_ods_url() -> str:
    html = fetch(PUB_URL).decode("utf-8", errors="replace")
    links = re.findall(
        r'https://assets\.publishing\.service\.gov\.uk/media/[a-f0-9]+/[^"\s]+\.ods',
        html,
    )
    if not links:
        sys.exit("ERROR: no .ods attachment link found on " + PUB_URL)
    return links[0]


def norm(v):
    s = str(v).strip()
    if not s or s.lower() in ("no data", "nan", "none", "n/a"):
        return None
    return s


def iso_date(v):
    s = norm(v)
    if s is None:
        return None
    try:
        return datetime.strptime(s, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return s  # keep raw value rather than dropping it


def main() -> None:
    ods_url = find_ods_url()
    print("Source file:", ods_url)
    blob = fetch(ods_url)
    sha = hashlib.sha256(blob).hexdigest()

    meta_path = DATA / "source_meta.json"
    prev_meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    if prev_meta.get("sha256") == sha:
        print("unchanged")
        return

    df = pd.read_excel(io.BytesIO(blob), engine="odf")
    total_rows = len(df)
    us = df[df["ISIN No"].astype(str).str.strip().str.upper().str.startswith("US")]

    funds = []
    for _, r in us.iterrows():
        funds.append({
            "ref": norm(r["Reporting Fund Ref"]),
            "parent": norm(r["Parent Fund"]),
            "classRef": norm(r["HMRC Share Class Ref No.’s"]),
            "name": norm(r["Sub Fund Name"]),
            "isin": norm(r["ISIN No"]),
            "cusip": norm(r["CUSIP No"]),
            "from": iso_date(r["Reporting Fund, with effect from"]),
            "ceased": iso_date(r["Ceased to be an RF on"]),
        })
    funds.sort(key=lambda f: ((f["parent"] or "").lower(), (f["name"] or "").lower()))

    # Diff against the previous build for the changelog.
    funds_path = DOCS / "funds.json"
    prev_by_isin = {}
    if funds_path.exists():
        for f in json.loads(funds_path.read_text()):
            prev_by_isin[f["isin"]] = f
    now_by_isin = {f["isin"]: f for f in funds}
    added = [f for k, f in now_by_isin.items() if k not in prev_by_isin]
    removed = [f for k, f in prev_by_isin.items() if k not in now_by_isin]
    newly_ceased = [
        f for k, f in now_by_isin.items()
        if k in prev_by_isin and f["ceased"] and not prev_by_isin[k]["ceased"]
    ]

    source_name = ods_url.rsplit("/", 1)[-1]
    m = re.match(r"(\d{4})(\d{2})(\d{2})", source_name)
    source_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
    build_time = datetime.now(timezone.utc).isoformat(timespec="seconds")

    active = sum(1 for f in funds if not f["ceased"])
    funds_path.write_text(json.dumps(funds, indent=1))
    (DOCS / "meta.json").write_text(json.dumps({
        "sourceUrl": ods_url,
        "sourceFile": source_name,
        "sourceDate": source_date,
        "built": build_time,
        "totalHmrcRows": total_rows,
        "usShareClasses": len(funds),
        "usActive": active,
        "usParentFunds": len({f["parent"] for f in funds}),
    }, indent=1))

    changelog_path = DOCS / "changelog.json"
    changelog = json.loads(changelog_path.read_text()) if changelog_path.exists() else []
    if prev_by_isin:  # skip the very first build - everything would be "added"
        slim = lambda f: {"parent": f["parent"], "name": f["name"], "isin": f["isin"]}
        changelog.insert(0, {
            "date": build_time[:10],
            "sourceFile": source_name,
            "added": [slim(f) for f in added],
            "removed": [slim(f) for f in removed],
            "ceased": [slim(f) for f in newly_ceased],
        })
        changelog_path.write_text(json.dumps(changelog, indent=1))

    DATA.mkdir(exist_ok=True)
    meta_path.write_text(json.dumps({
        "sha256": sha, "url": ods_url, "processed": build_time,
    }, indent=1))

    print(f"built: {len(funds)} US share classes ({active} active), "
          f"+{len(added)} added, -{len(removed)} removed, {len(newly_ceased)} newly ceased")


if __name__ == "__main__":
    main()
