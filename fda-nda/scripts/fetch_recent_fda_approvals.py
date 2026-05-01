#!/usr/bin/env python3
"""
Collect recently approved FDA drugs from official FDA sources.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


FDA_BASE = "https://www.fda.gov"
CDER_PAGE_TEMPLATE = FDA_BASE + "/drugs/novel-drug-approvals-fda/novel-drug-approvals-{year}"
CBER_PAGE_TEMPLATE = (
    FDA_BASE
    + "/vaccines-blood-biologics/development-approval-process-cber/"
    + "{year}-biological-license-application-approvals"
)
OPENFDA_URL = "https://api.fda.gov/drug/drugsfda.json"
FDA_SLEEP_SECONDS = 0.35


def normalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_name(value: str) -> str:
    normalized = normalize_ws(value).lower()
    normalized = normalized.replace("\u00a0", " ")
    normalized = normalized.replace("*", " ")
    normalized = normalized.replace("–", "-")
    normalized = normalized.replace("—", "-")
    normalized = re.sub(r"\([^)]*\)", " ", normalized)
    normalized = normalized.replace("/", " ")
    normalized = re.sub(r"[^a-z0-9+-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def aliases_for_name(value: str) -> set[str]:
    base = normalize_name(value)
    aliases = {base}
    if " co pack" in base:
        aliases.add(base.replace(" co pack", "").strip())
    if " co packaged" in base:
        aliases.add(base.replace(" co packaged", "").strip())
    if " qlex" in base:
        aliases.add(base.replace(" qlex", "").strip())
    return {alias for alias in aliases if alias}


def parse_mdy(value: str) -> date:
    return datetime.strptime(value.strip(), "%m/%d/%Y").date()


def subtract_months(anchor: date, months: int) -> date:
    year = anchor.year
    month = anchor.month - months
    while month <= 0:
        year -= 1
        month += 12
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = (next_month - datetime.resolution).day
    day = min(anchor.day, last_day)
    return date(year, month, day)


def date_in_window(value: date, start_date: date, end_date: date) -> bool:
    return start_date <= value <= end_date


def absolute_fda_url(href: str | None) -> str | None:
    if not href:
        return None
    if href.startswith("http://") or href.startswith("https://"):
        return href.replace("http://", "https://", 1)
    return urljoin(FDA_BASE, href)


def choose_curl() -> str | None:
    for candidate in ("curl.exe", "curl"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def fetch_fda_html(url: str) -> str | None:
    curl_bin = choose_curl()
    if not curl_bin:
        raise RuntimeError("curl is required to fetch FDA web pages reliably in this environment.")

    result = subprocess.run(
        [curl_bin, "-L", "-s", url],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return None
    body = result.stdout or ""
    lowered = body.lower()
    if not body.strip():
        return None
    if "abuse detection apology" in lowered:
        return None
    if lowered.strip() == "not found":
        return None
    if "<title>404" in lowered or "page not found" in lowered:
        return None
    time.sleep(FDA_SLEEP_SECONDS)
    return body


def download_file(url: str, output_path: Path) -> bool:
    curl_bin = choose_curl()
    if not curl_bin:
        raise RuntimeError("curl is required to download FDA files reliably in this environment.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [curl_bin, "-L", "-s", "-o", str(output_path), url],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    time.sleep(FDA_SLEEP_SECONDS)
    return result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0


def clean_cell_text(cell: BeautifulSoup, drop_links: bool = False) -> str:
    cloned = BeautifulSoup(str(cell), "lxml")
    target = cloned.find("td") or cloned
    if drop_links:
        for anchor in target.find_all("a"):
            anchor.decompose()
    text = target.get_text("\n", strip=True)
    lines = [normalize_ws(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def query_openfda_brand(
    session: requests.Session,
    brand_name: str,
    generic_name: str,
) -> dict[str, Any] | None:
    queries: list[str] = []
    if brand_name:
        queries.append(f'openfda.brand_name.exact:"{brand_name.upper()}"')
        plain_brand = brand_name.replace("*", "").strip()
        if plain_brand.upper() != brand_name.upper():
            queries.append(f'openfda.brand_name.exact:"{plain_brand.upper()}"')
    if generic_name:
        queries.append(f'openfda.generic_name.exact:"{generic_name.upper()}"')

    for query in queries:
        try:
            response = session.get(
                OPENFDA_URL,
                params={"search": query, "limit": 1},
                timeout=20,
            )
            if response.status_code != 200:
                continue
            payload = response.json()
            results = payload.get("results") or []
            if results:
                time.sleep(0.1)
                return results[0]
        except Exception:
            continue
    return None


def original_openfda_submission(result: dict[str, Any]) -> dict[str, Any] | None:
    submissions = result.get("submissions") or []
    originals = [
        item
        for item in submissions
        if str(item.get("submission_type", "")).upper() == "ORIG"
        and str(item.get("submission_status", "")).upper() == "AP"
        and item.get("submission_status_date")
    ]
    if not originals:
        return None
    return min(originals, key=lambda item: item["submission_status_date"])


def report_list_membership(section_text: str, trade_names: list[str]) -> set[str]:
    section_normalized = normalize_name(section_text)
    matched: set[str] = set()
    for trade_name in trade_names:
        for alias in aliases_for_name(trade_name):
            if alias and alias in section_normalized:
                matched.add(normalize_name(trade_name))
                break
    return matched


def find_section(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.S)
    return match.group(1).strip() if match else ""


def parse_bullet_highlights(section_text: str, trade_names: list[str]) -> dict[str, str]:
    highlights: dict[str, str] = {}
    if not section_text:
        return highlights
    blocks = [normalize_ws(block) for block in section_text.split("●")]
    blocks = [block for block in blocks if block]
    trade_aliases: list[tuple[str, str]] = []
    for trade_name in trade_names:
        for alias in aliases_for_name(trade_name):
            trade_aliases.append((alias, trade_name))
    trade_aliases.sort(key=lambda item: len(item[0]), reverse=True)

    for block in blocks:
        block_normalized = normalize_name(block)
        for alias, trade_name in trade_aliases:
            if block_normalized.startswith(alias):
                highlights[normalize_name(trade_name)] = block
                break
    return highlights


def parse_cder_report(report_url: str | None, year: int, trade_names: list[str]) -> dict[str, Any]:
    if not report_url:
        return {"flags_by_name": {}, "highlights_by_name": {}, "report_url": None}

    cache_dir = Path(tempfile.gettempdir()) / "fda_nda_skill_cache"
    pdf_path = cache_dir / f"cder_novel_report_{year}.pdf"
    if not pdf_path.exists():
        if not download_file(report_url, pdf_path):
            return {"flags_by_name": {}, "highlights_by_name": {}, "report_url": report_url}

    try:
        reader = PdfReader(str(pdf_path))
        full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return {"flags_by_name": {}, "highlights_by_name": {}, "report_url": report_url}

    category_patterns = {
        "first-in-class": (
            rf"Novel drugs approved in {year} that CDER identified as first-in-class were:\s*(.*?)\s*"
            r"Notable examples of novel first-in-class approvals include:"
        ),
        "orphan drug": (
            rf"Novel drugs approved in {year} with\s+orphan drug designation were:\s*(.*?)\s*"
            r"\*Approved without a trade name"
        ),
        "fast track": (
            r"Drugs granted fast track status were:\s*(.*?)\s*"
            r"\*Approved without a trade name"
        ),
        "breakthrough therapy": (
            r"Drugs designated with breakthrough therapy status were:\s*(.*?)\s*"
            r"\* Approved without a trade name\."
        ),
        "priority review": (
            r"Drugs designated priority review were:\s*(.*?)\s*Accelerated Approval"
        ),
        "accelerated approval": (
            r"The novel drugs approved via accelerated approval were:\s*(.*?)\s*"
            r"Overall Use of Expedited Development"
        ),
        "first cycle approval": (
            rf"Novel drugs approved in {year} on the first cycle were:\s*(.*?)\s*"
            r"Approval in the U\.S\."
        ),
        "first approved in us": (
            rf"Novel drugs of {year} approved first in the U\.S\. were:\s*(.*?)\s*First Cycle"
        ),
    }

    flags_by_name: dict[str, set[str]] = {normalize_name(name): set() for name in trade_names}
    for flag_name, pattern in category_patterns.items():
        section_text = find_section(full_text, pattern)
        for trade_key in report_list_membership(section_text, trade_names):
            flags_by_name.setdefault(trade_key, set()).add(flag_name)

    notable_sections = [
        find_section(
            full_text,
            r"Notable examples of novel first-in-class approvals include:\s*(.*?)\s*Drugs for Rare Diseases",
        ),
        find_section(
            full_text,
            rf"Examples of novel approvals of {year} for rare diseases include:\s*(.*?)\s*Other Novel Drug Approvals",
        ),
        find_section(
            full_text,
            rf"Other Novel Drug Approvals\s*(.*?)\s*Innovation: Use of Expedited Development",
        ),
    ]

    highlights_by_name: dict[str, str] = {}
    for section in notable_sections:
        for trade_key, highlight in parse_bullet_highlights(section, trade_names).items():
            highlights_by_name.setdefault(trade_key, highlight)

    return {
        "flags_by_name": {key: sorted(value) for key, value in flags_by_name.items() if value},
        "highlights_by_name": highlights_by_name,
        "report_url": report_url,
    }


def build_cder_significance_hint(
    brand_name: str,
    flags: list[str],
    highlight: str | None,
) -> str:
    if highlight:
        return highlight

    parts: list[str] = []
    if "first-in-class" in flags:
        parts.append("FDA identified it as a first-in-class novel approval.")
    if "breakthrough therapy" in flags:
        parts.append("FDA granted breakthrough therapy designation.")
    if "priority review" in flags:
        parts.append("FDA granted priority review, indicating potential meaningful clinical improvement.")
    if "accelerated approval" in flags:
        parts.append("FDA used the accelerated approval pathway.")
    if "orphan drug" in flags:
        parts.append("FDA listed it among orphan-drug approvals for rare diseases.")
    if "first approved in us" in flags:
        parts.append("FDA approved it in the United States before any other country.")
    if "first cycle approval" in flags:
        parts.append("FDA approved it on the first review cycle.")

    if not parts:
        parts.append(
            f"FDA included {brand_name} in the year's official novel drug approvals list."
        )
    return " ".join(parts)


def collect_cder_records(
    year: int,
    start_date: date,
    end_date: date,
    session: requests.Session,
    warnings: list[str],
) -> list[dict[str, Any]]:
    page_url = CDER_PAGE_TEMPLATE.format(year=year)
    html = fetch_fda_html(page_url)
    if not html:
        warnings.append(f"CDER page unavailable for {year}: {page_url}")
        return []

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        warnings.append(f"CDER table missing for {year}: {page_url}")
        return []

    report_url = None
    for anchor in soup.find_all("a", href=True):
        text = normalize_ws(anchor.get_text(" ", strip=True))
        href = anchor.get("href")
        if "Advancing Health Through Innovation" in text and "/media/" in (href or ""):
            report_url = absolute_fda_url(href)
            break

    rows = table.find_all("tr")[1:]
    provisional: list[dict[str, Any]] = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 5:
            continue
        raw_date = normalize_ws(cells[3].get_text(" ", strip=True))
        if not raw_date:
            continue
        approval_dt = parse_mdy(raw_date)
        if not date_in_window(approval_dt, start_date, end_date):
            continue

        brand_name = clean_cell_text(cells[1], drop_links=False).splitlines()[0]
        generic_name = clean_cell_text(cells[2], drop_links=False).splitlines()[0]

        use_cell = BeautifulSoup(str(cells[4]), "lxml").find("td")
        label_link = cells[1].find("a", href=True)
        snapshot_link = None
        if use_cell:
            for anchor in use_cell.find_all("a", href=True):
                if "snapshot" in normalize_ws(anchor.get_text(" ", strip=True)).lower():
                    snapshot_link = absolute_fda_url(anchor["href"])
            for anchor in use_cell.find_all("a"):
                anchor.decompose()
        indication_en = clean_cell_text(use_cell or cells[4], drop_links=False).replace("\n", " ")

        provisional.append(
            {
                "brand_name": normalize_ws(brand_name),
                "generic_name": normalize_ws(generic_name),
                "approval_date": approval_dt.isoformat(),
                "indication_en": normalize_ws(indication_en),
                "label_url": absolute_fda_url(label_link["href"]) if label_link else None,
                "snapshot_url": snapshot_link,
                "page_url": page_url,
            }
        )

    trade_names = [item["brand_name"] for item in provisional]
    report_context = parse_cder_report(report_url, year, trade_names)

    records: list[dict[str, Any]] = []
    for item in provisional:
        openfda_result = query_openfda_brand(
            session,
            brand_name=item["brand_name"],
            generic_name=item["generic_name"],
        )
        original_submission = original_openfda_submission(openfda_result or {})
        application_number = (openfda_result or {}).get("application_number")
        sponsor_name = (openfda_result or {}).get("sponsor_name")
        manufacturer_name = None
        openfda_block = (openfda_result or {}).get("openfda") or {}
        manufacturer_names = openfda_block.get("manufacturer_name") or []
        if manufacturer_names:
            manufacturer_name = manufacturer_names[0]

        trade_key = normalize_name(item["brand_name"])
        flags = (report_context["flags_by_name"].get(trade_key) or [])
        highlight = report_context["highlights_by_name"].get(trade_key)
        source_urls = [
            item["page_url"],
            report_context.get("report_url"),
            item.get("label_url"),
            item.get("snapshot_url"),
        ]
        if original_submission:
            for doc in original_submission.get("application_docs") or []:
                if doc.get("url"):
                    source_urls.append(doc["url"])

        records.append(
            {
                "source_center": "CDER",
                "official_program": "Novel Drug Approvals",
                "drug_category": "biologic"
                if str(application_number or "").upper().startswith("BLA")
                else "chemical drug",
                "brand_name": item["brand_name"],
                "generic_name": item["generic_name"],
                "manufacturer_en": manufacturer_name or sponsor_name or "",
                "sponsor_en": sponsor_name or "",
                "indication_en": item["indication_en"],
                "approval_date": item["approval_date"],
                "application_number": application_number or "",
                "regulatory_flags_en": flags,
                "significance_hint_en": build_cder_significance_hint(
                    item["brand_name"], flags, highlight
                ),
                "modality_hint_en": "",
                "source_urls": sorted({url for url in source_urls if url}),
                "official_evidence_en": {
                    "report_highlight": highlight or "",
                    "openfda_original_submission": original_submission or {},
                },
            }
        )

    return records


def is_non_drug_cber_entry(brand_name: str, indication: str) -> bool:
    blob = normalize_name(f"{brand_name} {indication}")
    blocked_terms = [
        "in vitro detection",
        "blood grouping reagent",
        "anti human globulin",
        "automated c3d plate",
        "manual tube test",
    ]
    return any(term in blob for term in blocked_terms)


def cber_modality_hint(brand_name: str, generic_name: str, indication: str) -> str:
    blob = normalize_name(f"{brand_name} {generic_name} {indication}")
    normalized_generic = normalize_name(generic_name)
    if "vaccine" in blob or "active immunization" in blob:
        if "mrna" in blob:
            return "mRNA vaccine"
        if "recombinant" in blob:
            return "recombinant vaccine"
        if "adjuvanted" in blob:
            return "adjuvanted vaccine"
        return "vaccine"
    if (
        re.search(r"\b[a-z]+gene\b", normalized_generic)
        or any(marker in normalized_generic for marker in ("parvovec", "autotemcel"))
        or "gene therapy" in blob
    ):
        return "gene therapy biologic"
    if generic_name.lower().endswith("cel") or "allograft" in blob:
        return "cell or tissue-based biologic"
    if "globulin" in blob:
        return "immune globulin biologic"
    if "fibrinogen" in blob or "coagulation factor" in blob:
        return "coagulation-factor replacement biologic"
    return "biologic"


def cber_category(brand_name: str, generic_name: str, indication: str) -> str:
    blob = normalize_name(f"{brand_name} {generic_name} {indication}")
    if "vaccine" in blob or "active immunization" in blob:
        return "vaccine"
    return "biologic"


def build_cber_significance_hint(
    category: str,
    modality_hint: str,
    indication: str,
) -> str:
    parts: list[str] = []
    if category == "vaccine":
        parts.append(
            "FDA licensed it as a vaccine product, adding an officially approved immunization option."
        )
    elif "gene therapy" in modality_hint:
        parts.append(
            "FDA licensed it as a gene-therapy biologic, highlighting a mechanism-based treatment approach."
        )
    elif "cell or tissue-based" in modality_hint:
        parts.append(
            "FDA licensed it as a cell- or tissue-based biologic rather than a conventional small-molecule therapy."
        )
    elif "globulin" in modality_hint:
        parts.append("FDA licensed it as an immune-globulin biologic.")
    elif "coagulation-factor" in modality_hint:
        parts.append("FDA licensed it as a coagulation-factor replacement biologic.")
    else:
        parts.append("FDA licensed it as a biologic product through CBER.")

    if "accelerated approval" in indication.lower():
        parts.append("The official indication text notes an accelerated-approval component.")
    return " ".join(parts)


def parse_cber_product_page(product_url: str) -> dict[str, Any]:
    html = fetch_fda_html(product_url)
    if not html:
        return {}

    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main") or soup
    text = normalize_ws(main.get_text("\n", strip=True))
    fields: dict[str, Any] = {}
    patterns = {
        "application_number": r"STN:\s*(BLA\s*[0-9/]+)",
        "proper_name": r"Proper Name:\s*(.*?)\s*Tradename:",
        "tradename": r"Tradename:\s*(.*?)\s*Manufacturer:",
        "manufacturer": r"Manufacturer:\s*(.*?)\s*Indications:",
        "indications": r"Indications:\s*(.*?)\s*Product Information",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.S)
        if match:
            fields[key] = normalize_ws(match.group(1))

    source_urls = [product_url]
    for anchor in main.find_all("a", href=True):
        label = normalize_ws(anchor.get_text(" ", strip=True)).lower()
        href = absolute_fda_url(anchor.get("href"))
        if not href:
            continue
        if any(
            marker in label
            for marker in (
                "package insert",
                "approval letter",
                "summary basis for regulatory action",
                "related documents",
                "supporting documents",
            )
        ):
            source_urls.append(href)

    fields["source_urls"] = sorted({url for url in source_urls if url})
    return fields


def collect_cber_records(
    year: int,
    start_date: date,
    end_date: date,
    warnings: list[str],
) -> list[dict[str, Any]]:
    page_url = CBER_PAGE_TEMPLATE.format(year=year)
    html = fetch_fda_html(page_url)
    if not html:
        warnings.append(f"CBER page unavailable for {year}: {page_url}")
        return []

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        warnings.append(f"CBER table missing for {year}: {page_url}")
        return []

    records: list[dict[str, Any]] = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 5:
            continue
        raw_date = clean_cell_text(cells[4], drop_links=False).replace("\n", " ")
        if not raw_date:
            continue
        try:
            approval_dt = parse_mdy(raw_date)
        except ValueError:
            continue
        if not date_in_window(approval_dt, start_date, end_date):
            continue

        indication_en = clean_cell_text(cells[1], drop_links=False).replace("\n", " ")
        first_cell_text = clean_cell_text(cells[0], drop_links=False)
        if is_non_drug_cber_entry(first_cell_text, indication_en):
            continue

        first_link = cells[0].find("a", href=True)
        product_url = absolute_fda_url(first_link["href"]) if first_link else None
        product_page = parse_cber_product_page(product_url) if product_url else {}

        brand_name = product_page.get("tradename")
        generic_name = product_page.get("proper_name")
        manufacturer_en = product_page.get("manufacturer")
        application_number = product_page.get("application_number", "")

        if not brand_name or not generic_name:
            lines = [line for line in first_cell_text.splitlines() if line]
            if not brand_name and lines:
                brand_name = lines[0]
            if not generic_name and len(lines) > 1:
                generic_name = lines[1]

        if not manufacturer_en:
            manufacturer_en = clean_cell_text(cells[3], drop_links=False).splitlines()[0]

        category = cber_category(brand_name or "", generic_name or "", indication_en)
        modality_hint = cber_modality_hint(brand_name or "", generic_name or "", indication_en)
        source_urls = [page_url, product_url]
        source_urls.extend(product_page.get("source_urls") or [])

        records.append(
            {
                "source_center": "CBER",
                "official_program": "Biological License Application Approvals",
                "drug_category": category,
                "brand_name": normalize_ws(brand_name or ""),
                "generic_name": normalize_ws(generic_name or ""),
                "manufacturer_en": normalize_ws(manufacturer_en or ""),
                "sponsor_en": normalize_ws(manufacturer_en or ""),
                "indication_en": normalize_ws(indication_en),
                "approval_date": approval_dt.isoformat(),
                "application_number": normalize_ws(application_number),
                "regulatory_flags_en": [],
                "significance_hint_en": build_cber_significance_hint(
                    category,
                    modality_hint,
                    indication_en,
                ),
                "modality_hint_en": modality_hint,
                "source_urls": sorted({url for url in source_urls if url}),
                "official_evidence_en": {
                    "product_page_snapshot": {
                        "brand_name": brand_name or "",
                        "generic_name": generic_name or "",
                        "manufacturer": manufacturer_en or "",
                    }
                },
            }
        )

    return records


def deduplicate_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        key = (
            normalize_name(record.get("brand_name", "")),
            record.get("approval_date", ""),
            normalize_ws(record.get("application_number", "")),
        )
        if key not in unique:
            unique[key] = record
    return list(unique.values())


def sorted_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda item: (
            item.get("approval_date", ""),
            item.get("brand_name", "").lower(),
        ),
        reverse=True,
    )


def collect_records(months: int, as_of: date) -> dict[str, Any]:
    start_date = subtract_months(as_of, months)
    years = range(start_date.year, as_of.year + 1)
    warnings: list[str] = []
    session = requests.Session()

    records: list[dict[str, Any]] = []
    for year in years:
        records.extend(collect_cder_records(year, start_date, as_of, session, warnings))
        records.extend(collect_cber_records(year, start_date, as_of, warnings))

    final_records = sorted_records(deduplicate_records(records))
    return {
        "as_of": as_of.isoformat(),
        "months": months,
        "start_date": start_date.isoformat(),
        "end_date": as_of.isoformat(),
        "record_count": len(final_records),
        "warnings": warnings,
        "records": final_records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect recent FDA approvals from official sources.")
    parser.add_argument("--months", type=int, required=True, help="Lookback window in months.")
    parser.add_argument(
        "--as-of",
        dest="as_of",
        default=date.today().isoformat(),
        help="Anchor date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--output",
        default="-",
        help="Output JSON path. Use '-' to print to stdout.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.months <= 0:
        raise SystemExit("--months must be a positive integer.")
    as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date()
    payload = collect_records(args.months, as_of)

    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output == "-":
        print(rendered)
    else:
        output_path = Path(args.output).resolve()
        output_path.write_text(rendered, encoding="utf-8")
        print(f"Wrote {payload['record_count']} records to {output_path}")
        if payload["warnings"]:
            print("Warnings:")
            for warning in payload["warnings"]:
                print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
