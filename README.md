# US-Domiciled Funds with UK HMRC Reporting Fund Status

Static site tracking the funds on HMRC's [approved offshore reporting funds](https://www.gov.uk/government/publications/approved-offshore-reporting-funds)
list whose ISIN begins with `US` (i.e. US-domiciled funds and ETFs).

## How it works

- `scripts/build.py` scrapes the gov.uk publication page for the current
  `.ods` attachment, downloads it, filters rows with a `US` ISIN prefix and
  writes `docs/funds.json`, `docs/meta.json` and `docs/changelog.json`
  (added / removed / newly-ceased share classes per refresh).
  It exits early ("unchanged") when the source file's SHA-256 matches
  `data/source_meta.json` from the last run.
- `docs/index.html` is a self-contained searchable table (search, sort,
  active/ceased filter, CSV download, changelog) served via GitHub Pages
  from the `docs/` folder.
- `.github/workflows/refresh.yml` runs on the 1st and 16th of each month
  (and on manual dispatch), rebuilds, and commits only when the HMRC file
  changed — the push triggers a Pages redeploy automatically.

## Local development

```bash
python3 -m venv .venv && .venv/bin/pip install pandas odfpy
.venv/bin/python scripts/build.py
python3 -m http.server -d docs 8080   # then open http://localhost:8080
```

Data: HMRC, Open Government Licence v3.0. Informational only, not advice.
