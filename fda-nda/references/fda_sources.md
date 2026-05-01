# FDA Source Notes

This skill is restricted to official FDA sources.

## CDER

- Year page: `https://www.fda.gov/drugs/novel-drug-approvals-fda/novel-drug-approvals-<year>`
- Annual report PDF: linked on the year page as `Advancing Health Through Innovation: New Drug Therapy Approvals <year>`
- openFDA metadata: `https://api.fda.gov/drug/drugsfda.json`

Field mapping used by the bundled script:

- `brand_name`, `generic_name`, `approval_date`, `indication_en`:
  CDER year-page table
- `manufacturer_en`, `sponsor_en`, `application_number`:
  openFDA `drug/drugsfda` endpoint
- `regulatory_flags_en` and `significance_hint_en`:
  CDER annual report PDF

## CBER

- Year page: `https://www.fda.gov/vaccines-blood-biologics/development-approval-process-cber/<year>-biological-license-application-approvals`
- Product page: first-column link on each approval row

Field mapping used by the bundled script:

- `approval_date`, initial `indication_en`:
  CBER year-page table
- `brand_name`, `generic_name`, `manufacturer_en`, `application_number`:
  product page
- `significance_hint_en`, `modality_hint_en`:
  product page plus conservative modality inference

## Translation Rules

When converting raw output into the final workbook:

- Keep `generic_name` and `brand_name` in their original English spellings.
- Translate all other descriptive fields into concise Chinese.
- Base `significance_zh` only on official FDA evidence already present in the raw JSON.
- Avoid unsupported superiority claims. If evidence is limited to regulatory flags,
  describe the value as regulatory significance instead of absolute clinical superiority.
