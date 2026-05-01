---
name: fda-nda
description: Fetch recent FDA new approvals from official FDA sources and export them as fdaNDA.xlsx. Use when the user asks for FDA recently approved drugs, biologics, or vaccines within a time window like 6 months or 12 months, mentions fdaNDA, or wants a Chinese summary table of FDA new approvals saved in the current directory.
---

# FDA NDA

## Overview

Use this skill to gather recent FDA approvals from official FDA pages only, translate the descriptive fields into Chinese, and save the result as `fdaNDA.xlsx` in the current working directory.

Keep `generic_name` and `brand_name` in English. Translate every other descriptive field into concise Chinese.

The authoritative output is `fdaNDA.xlsx`.
Do not treat `fdaNDA.sample.xlsx` as the final deliverable unless the user explicitly asks for a sample copy.

## Workflow

1. Parse the user input into a positive month count.
   Accept examples like `12 months`, `last 6 months`, or `recent 9 months`.

2. Run the bundled end-to-end script.

```powershell
python "C:\Users\Lenovo\.claude\skills\fda-nda\scripts\run_fda_nda.py" --period "12 months" --output-dir "." --keep-json
```

3. The end-to-end script already:
   - collects raw FDA records
   - converts them into Chinese summary rows
   - writes `.\fdaNDA.xlsx`
   - optionally saves `.\fdaNDA.raw.json` and `.\fdaNDA.curated.json`

4. The collector stage filters by date and merges:
   - CDER annual novel-drug approvals pages
   - CDER annual report PDF flags
   - openFDA sponsor/application metadata
   - CBER biologics approval pages
   - linked CBER product pages

5. The final workbook rows must include these fields:
   - `drug_type_zh`
   - `generic_name`
   - `brand_name`
   - `manufacturer_zh`
   - `indication_zh`
   - `approval_date`
   - `significance_zh`
   - `source_urls`

   If `manufacturer_en` is blank, do one manual FDA-only supplement pass before finalizing:
   - search official FDA pages for the product name
   - prefer an FDA approval letter, FDA product page, or Drugs@FDA/openFDA result
   - then fill `manufacturer_zh`

6. Confirm `.\fdaNDA.xlsx` exists and tell the user where it was written.

## Translation Rules

- Keep `generic_name` and `brand_name` unchanged.
- Translate `manufacturer_zh`, `indication_zh`, and `significance_zh` into Chinese.
- For manufacturer cells, a Chinese wrapper around the official company name is acceptable.
- Keep `approval_date` in ISO format `YYYY-MM-DD` unless the user asks for another date format.
- If `manufacturer_en` is missing after the collector step, fill it from another official FDA page before exporting.

## Significance Rules

Build `significance_zh` only from the official evidence already present in the raw JSON.

- Prefer `official_evidence_en.report_highlight` when it exists.
- Otherwise use `regulatory_flags_en` and `modality_hint_en`.
- Do not invent head-to-head superiority claims.
- If the evidence only shows regulatory importance, say so explicitly.

Good patterns:
- State that FDA identified a product as first-in-class when the raw flags say so.
- State that a product used breakthrough, priority, or accelerated review when the raw flags say so.
- State that a product is notable for being a gene therapy, biologic platform, or vaccine platform when the raw evidence supports it.

Avoid:
- claims like "best efficacy"
- claims like "better than all competitors"
- any comparison not supported by the raw FDA evidence

## If The Collector Returns Warnings

- Read [fda_sources.md](references/fda_sources.md) only if you need to verify source coverage.
- If a current-year FDA page is unavailable, tell the user the workbook reflects all currently reachable official pages returned by the script.
- Still export the workbook if valid records were collected.

## Output Standard

The final workbook should include Chinese column headers and Chinese descriptions for all non-name fields.
