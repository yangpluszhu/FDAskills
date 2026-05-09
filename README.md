# FDAskills

AI-powered FDA regulatory intelligence skills built on [Claude Agent SDK](https://docs.anthropic.com/en/docs/agents-and-tools/claude-agent-sdk).

Two end-to-end automation skills that transform natural-language instructions into structured regulatory intelligence deliverables — no manual browsing, no copy-paste, no spreadsheets by hand.

## Skills

### `/fda-nda` — FDA New Drug Approval Tracker

Collects recent FDA drug and biologic approvals from **5 official FDA sources**, translates descriptive fields into Chinese, and exports a structured Excel workbook.

**What it does:**

```
"Get FDA new drug approvals from the last 12 months"
    → fdaNDA.xlsx (Chinese summary with regulatory flags, significance, and source URLs)
```

**Data sources (all official FDA):**

| Source | Type | Data Extracted |
|--------|------|----------------|
| CDER Novel Drug Approvals page | HTML table | Brand name, generic name, indication, approval date |
| CDER Annual Report PDF | PDF text | 7 regulatory flags (first-in-class, breakthrough, priority review, etc.) |
| openFDA `drug/drugsfda` API | JSON | Manufacturer, sponsor, application number |
| CBER BLA Approvals page | HTML table | Biologic approvals with dates |
| CBER product detail pages | HTML | Brand name, proper name, manufacturer, indications |

**Pipeline (7 stages):**

1. Parse user time window (supports `12 months`, `6个月`, `1 year`)
2. Multi-source parallel collection across CDER + CBER + openFDA
3. Cross-source entity alignment (fuzzy name normalization + deduplication)
4. Regulatory flag extraction from PDF (7 categories with regex-based section parsing)
5. Evidence-constrained significance generation (built-in anti-hallucination guardrails)
6. Multi-stage medical translation (prefix detection → 100+ domain term replacement → Chinese punctuation normalization)
7. Formatted Excel output (auto row-height, frozen header, hyperlinks to FDA sources)

**Key technical detail — anti-hallucination:**

The `translate_significance()` function only generates claims when official FDA evidence exists. It explicitly forbids unsupported superiority claims like "best efficacy" or "better than all competitors." If evidence is limited to regulatory flags, the output says so.

### `/fdaGuide` — FDA Guidance Document Downloader

Automates downloading FDA guidance PDFs with multi-dimensional filtering and automatic pagination.

**What it does:**

```
"Download all GCP guidance documents from CDER"
    → Batch PDF download + JSON metadata manifest
```

**Filter dimensions (combine with AND logic):**

- **Product** — Drugs, Devices, Biologics, etc.
- **FDA Organization** — CDER, CDRH, CBER, CVM, CFSAN, etc.
- **Topic** — 60+ topics including GCP, RWD/RWE, Postmarket, Premarket, etc.

**Pipeline (6 stages):**

1. Launch headless Chromium, load FDA guidance search page
2. Apply filters sequentially (Product → Organization → Topic) with DataTables AJAX sync
3. Automatic pagination traversal until last page
4. Anti-detection PDF download via in-browser `fetch()` with proper headers
5. File integrity verification (existence + non-zero size check)
6. JSON manifest generation (title, classification, URL, page number, filename)

**Key technical detail — anti-detection:**

Downloads use `page.evaluate()` to execute `fetch()` inside the browser context, inheriting the browser's session cookies and headers. This avoids triggering FDA's bot detection while remaining fully respectful (2-second delay between downloads).

## Quick Start

### Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and configured
- Python 3.10+ (for `/fda-nda`)
- Node.js 18+ with Playwright (for `/fdaGuide`)

### Install Skills

Clone this repo into your Claude skills directory:

```bash
# Clone
git clone https://github.com/yangpluszhu/FDAskills.git

# Copy skill directories to Claude skills path
cp -r FDAskills/fda-nda ~/.claude/skills/fda-nda
cp -r FDAskills/fdaGuide ~/.claude/skills/fdaGuide
```

### Install Dependencies

```bash
# For fda-nda
pip install requests beautifulsoup4 pypdf openpyxl lxml

# For fdaGuide
cd fdaGuide
npm install playwright
npx playwright install chromium
```

### Usage

Invoke through Claude Code:

```
> /fda-nda "Get FDA approvals from the last 12 months"

> /fdaGuide "Download all GCP guidance documents for Drugs from CDER"
```

Or run scripts directly:

```bash
# fda-nda
python fda-nda/scripts/run_fda_nda.py --period "12 months" --output-dir . --keep-json

# fdaGuide
node fdaGuide/scripts/download_fda_by_topic.js --topic "Good Clinical Practice (GCP)" --product "Drugs" --organization "CDER"
```

## Output Examples

### `/fda-nda` Output

| 药物类型 | 通用名 | 商品名 | 生产商 | 适应症 | 批准日期 | 上市意义或价值 |
|---------|--------|--------|--------|--------|---------|--------------|
| 化学药 | voonmetazugene ... | ... | FDA官方披露生产商：... | 用于治疗... | 2025-03-15 | FDA将其认定为首创新机制产品... |

### `/fdaGuide` Output

```
1_Use_of_Real-World_Evidence_to_Support_Regulatory_Decision-Making.pdf
2_E9_Statistical_Principles_for_Clinical_Trials.pdf
...
CDER_Drugs_GCP_all_documents_list.json    # Metadata manifest
page_CDER_Drugs_GCP_filtered.png          # Search page screenshot
```

## Architecture

```
Agent Layer (Claude Agent SDK)
  └─ Natural language understanding → Task routing → Result delivery

Tool Layer (Claude Code Skills)
  ├─ /fda-nda          /fdaGuide
  │   SKILL.md           SKILL.md
  │   └─ scripts/        └─ scripts/
  │       ├─ fetch_recent_fda_approvals.py    download_fda_by_topic.js
  │       ├─ run_fda_nda.py
  │       └─ write_fda_nda_xlsx.py

Execution Layer
  ├─ Python + curl + openFDA API + PDF parsing
  └─ Node.js + Playwright + Chromium headless
```

## Project Structure

```
FDAskills/
├── fda-nda/                    # FDA NDA approval tracking skill
│   ├── SKILL.md                # Skill definition & workflow
│   ├── agents/
│   │   └── openai.yaml         # Agent interface config
│   ├── references/
│   │   └── fda_sources.md      # FDA source URL & field mapping docs
│   └── scripts/
│       ├── run_fda_nda.py              # End-to-end runner + translation
│       ├── fetch_recent_fda_approvals.py  # Multi-source data collection
│       └── write_fda_nda_xlsx.py       # Excel workbook generation
├── fdaGuide/                   # FDA guidance document downloader skill
│   ├── SKILL.md                # Skill definition & usage docs
│   └── scripts/
│       └── download_fda_by_topic.js    # Playwright automation script
└── .gitignore
```

## Technical Highlights

| Feature | `/fda-nda` | `/fdaGuide` |
|---------|-----------|------------|
| Language | Python (~1,200 LOC) | Node.js (~640 LOC) |
| FDA data sources | 5 (CDER HTML + PDF + openFDA + CBER HTML + Product pages) | 1 (FDA search page + auto-pagination) |
| Regulatory flag categories | 7 (first-in-class, breakthrough, priority, accelerated, orphan, first-cycle, first-in-US) | — |
| Medical translation dictionary | 100+ domain terms + 40+ indication overrides | — |
| Filter dimensions | — | 3 (Product × Organization × Topic) |
| Anti-hallucination | Evidence-constrained generation | — |
| Anti-detection | Rate-limited curl | In-browser fetch API |
| Output formats | Excel (.xlsx) + JSON | Batch PDF + JSON manifest |
| Graceful degradation | Skips unavailable sources, exports partial results | Skips existing files, reports failures |

## License

MIT
