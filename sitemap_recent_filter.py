from __future__ import annotations

"""
Download top-level sitemap files, expand child sitemaps, filter recent URLs,
and export the results to CSV and Excel.
"""

import csv
import gzip
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet


# ============================================================
# CONFIGURATION
# ============================================================
PROJECT_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = PROJECT_DIR / "downloaded_sitemaps"
OUTPUT_DIR = PROJECT_DIR / "recent_sitemap_outputs"
EXCEL_PATH = OUTPUT_DIR / "recent_urls.xlsx"

BASE_URLS = [
    "https://www.motortrend.com/",
    "https://www.autonews.com/",
    "https://www.spglobal.com/automotive-insights/en",
    "https://www.automotiveworld.com/",
]

# Keep this empty unless you intentionally want to process local XML files
# alongside the downloaded top-level sitemap files.
MANUAL_INPUT_FILES: tuple[str, ...] = ()

CUTOFF_DATE_TEXT = "2026-02-20"
KEEP_URLS_WITHOUT_LASTMOD = False
REQUEST_TIMEOUT_SECONDS = 60
EXCEL_MAX_DATA_ROWS = 1_048_575
OUTPUT_COLUMNS = ("link", "lastmod")
DEFAULT_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
DATE_IN_URL_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36"
    )
}


@dataclass
class ProcessStats:
    csv_rows: int = 0
    excel_rows: int = 0
    excel_truncated: bool = False
    expanded_child_sitemaps: int = 0
    skipped_child_sitemaps: int = 0


# ============================================================
# SETUP HELPERS
# ============================================================
def ensure_runtime_directories() -> None:
    """Create the runtime folders used by the pipeline."""
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)


def create_workbook() -> Workbook:
    """Create an empty workbook that will receive one sheet per sitemap."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    return workbook


# ============================================================
# DATE HELPERS
# ============================================================
def to_date(value: str) -> Optional[date]:
    """Convert common sitemap date formats into a Python date."""
    if not value:
        return None

    text = value.strip()
    if not text:
        return None

    if len(text) >= 10:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass

    try:
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return None


def extract_date_from_url(url: str) -> Optional[date]:
    """Read a date from a child sitemap URL when the parent lacks lastmod."""
    match = DATE_IN_URL_RE.search(url)
    if not match:
        return None

    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


# ============================================================
# XML HELPERS
# ============================================================
def strip_namespace(tag: str) -> str:
    """Remove an XML namespace prefix from a tag name."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def get_namespace(root: ET.Element) -> dict[str, str]:
    """Return the namespace mapping needed for ElementTree lookups."""
    if root.tag.startswith("{"):
        return {"sm": root.tag.split("}", 1)[0][1:]}
    return {"sm": DEFAULT_NAMESPACE}


def get_child_text(parent: ET.Element, tag_name: str, namespace: dict[str, str]) -> str:
    """Safely read text from a direct child node."""
    node = parent.find(f"sm:{tag_name}", namespace)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def parse_xml_bytes(content: bytes, source_name: str = "") -> ET.Element:
    """Parse XML bytes and transparently handle gzip-compressed sitemaps."""
    is_gzip = source_name.lower().endswith(".gz") or content[:2] == b"\x1f\x8b"
    if is_gzip:
        try:
            content = gzip.decompress(content)
        except OSError:
            pass

    text = content.decode("utf-8-sig", errors="replace").strip()
    return ET.fromstring(text)


# ============================================================
# NETWORK HELPERS
# ============================================================
def build_sitemap_url(base_url: str) -> str:
    """Turn a base site URL into its top-level sitemap.xml URL."""
    return base_url.rstrip("/") + "/sitemap.xml"


def build_download_file_name(base_url: str) -> str:
    """Create a stable local filename for a downloaded top-level sitemap."""
    parsed = urlparse(base_url)
    raw_name = f"{parsed.netloc}{parsed.path}".strip("/")
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in raw_name).strip("_")
    return f"{safe_name or 'sitemap'}_sitemap.xml"


def fetch_bytes(url: str, session: requests.Session) -> bytes:
    """Download raw bytes from a sitemap URL."""
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.content


def fetch_remote_root(url: str, session: requests.Session) -> ET.Element:
    """Download and parse a remote child sitemap."""
    return parse_xml_bytes(fetch_bytes(url, session), source_name=url)


def download_top_level_sitemap(base_url: str, session: requests.Session) -> Path:
    """Download one site's top-level sitemap.xml to disk."""
    sitemap_url = build_sitemap_url(base_url)
    download_path = DOWNLOAD_DIR / build_download_file_name(base_url)
    download_path.write_bytes(fetch_bytes(sitemap_url, session))
    print(f"[FETCH] {sitemap_url} -> {download_path}")
    return download_path


def collect_input_files(session: requests.Session) -> list[Path]:
    """Build the list of top-level sitemap files to process."""
    input_files: list[Path] = []

    for base_url in BASE_URLS:
        try:
            input_files.append(download_top_level_sitemap(base_url, session))
        except Exception as exc:
            print(f"[ERROR] Failed to download sitemap for {base_url}: {exc}")

    for file_name in MANUAL_INPUT_FILES:
        file_path = PROJECT_DIR / file_name
        if not file_path.exists():
            print(f"[SKIP] File not found: {file_path}")
            continue
        input_files.append(file_path)

    return input_files


# ============================================================
# OUTPUT HELPERS
# ============================================================
def safe_stem(name: str) -> str:
    """Create a filesystem-safe output stem."""
    raw_stem = Path(name).stem
    safe_stem_name = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_"
        for ch in raw_stem
    ).strip("_")
    return safe_stem_name or "output"


def safe_sheet_name(name: str) -> str:
    """Create an Excel-safe worksheet name."""
    cleaned_name = name
    for character in ['\\', '/', '*', '[', ']', ':', '?']:
        cleaned_name = cleaned_name.replace(character, "_")
    return cleaned_name[:31]


def write_result_row(
    link: str,
    lastmod: str,
    csv_writer: csv.DictWriter,
    worksheet: Worksheet,
    stats: ProcessStats,
) -> None:
    """Write one filtered URL to the CSV and Excel outputs."""
    csv_writer.writerow({"link": link, "lastmod": lastmod})
    stats.csv_rows += 1

    if stats.excel_rows < EXCEL_MAX_DATA_ROWS:
        worksheet.append([link, lastmod])
        stats.excel_rows += 1
    else:
        stats.excel_truncated = True


# ============================================================
# FILTERING RULES
# ============================================================
def should_keep_final_url(lastmod_text: str, cutoff_date: date) -> bool:
    """Keep a final URL when its lastmod date is on or after the cutoff."""
    lastmod_date = to_date(lastmod_text)
    if lastmod_date is None:
        return KEEP_URLS_WITHOUT_LASTMOD
    return lastmod_date >= cutoff_date


def should_expand_child_sitemap(
    child_url: str,
    parent_lastmod_text: str,
    cutoff_date: date,
) -> bool:
    """
    Decide whether a child sitemap is worth opening.

    Order of checks:
    1. Parent sitemap lastmod
    2. Date embedded in the child sitemap URL
    3. Expand anyway if there is not enough metadata to skip safely
    """
    parent_lastmod_date = to_date(parent_lastmod_text)
    if parent_lastmod_date is not None:
        return parent_lastmod_date >= cutoff_date

    child_date_from_url = extract_date_from_url(child_url)
    if child_date_from_url is not None:
        return child_date_from_url >= cutoff_date

    return True


# ============================================================
# CORE WALKER
# ============================================================
def walk_sitemap(
    root: ET.Element,
    session: requests.Session,
    cutoff_date: date,
    csv_writer: csv.DictWriter,
    worksheet: Worksheet,
    stats: ProcessStats,
    visited_sitemaps: set[str],
) -> None:
    """Recursively process either a urlset or a sitemapindex."""
    namespace = get_namespace(root)
    root_type = strip_namespace(root.tag)

    if root_type == "urlset":
        for url_node in root.findall("./sm:url", namespace):
            link = get_child_text(url_node, "loc", namespace)
            lastmod = get_child_text(url_node, "lastmod", namespace)

            if link and should_keep_final_url(lastmod, cutoff_date):
                write_result_row(link, lastmod, csv_writer, worksheet, stats)
        return

    if root_type == "sitemapindex":
        for sitemap_node in root.findall("./sm:sitemap", namespace):
            child_url = get_child_text(sitemap_node, "loc", namespace)
            parent_lastmod = get_child_text(sitemap_node, "lastmod", namespace)

            if not child_url or child_url in visited_sitemaps:
                continue

            if not should_expand_child_sitemap(child_url, parent_lastmod, cutoff_date):
                stats.skipped_child_sitemaps += 1
                continue

            visited_sitemaps.add(child_url)
            stats.expanded_child_sitemaps += 1

            try:
                child_root = fetch_remote_root(child_url, session)
                walk_sitemap(
                    root=child_root,
                    session=session,
                    cutoff_date=cutoff_date,
                    csv_writer=csv_writer,
                    worksheet=worksheet,
                    stats=stats,
                    visited_sitemaps=visited_sitemaps,
                )
            except Exception as exc:
                print(f"[WARN] Could not open child sitemap: {child_url} -> {exc}")
        return

    raise ValueError(f"Unsupported sitemap root tag: {root.tag}")


# ============================================================
# TOP-LEVEL PROCESSING
# ============================================================
def process_top_level_file(
    file_path: Path,
    workbook: Workbook,
    session: requests.Session,
    cutoff_date: date,
) -> None:
    """Process one top-level sitemap file and export filtered results."""
    output_stem = safe_stem(file_path.name)
    csv_path = OUTPUT_DIR / f"{output_stem}_after_{cutoff_date.isoformat()}.csv"

    worksheet = workbook.create_sheet(title=safe_sheet_name(output_stem))
    worksheet.append(list(OUTPUT_COLUMNS))

    stats = ProcessStats()
    visited_sitemaps: set[str] = set()
    root = parse_xml_bytes(file_path.read_bytes(), source_name=file_path.name)

    with csv_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(OUTPUT_COLUMNS))
        writer.writeheader()
        walk_sitemap(
            root=root,
            session=session,
            cutoff_date=cutoff_date,
            csv_writer=writer,
            worksheet=worksheet,
            stats=stats,
            visited_sitemaps=visited_sitemaps,
        )

    print(
        f"[DONE] {file_path.name} -> rows={stats.csv_rows}, "
        f"expanded_child_sitemaps={stats.expanded_child_sitemaps}, "
        f"skipped_child_sitemaps={stats.skipped_child_sitemaps}"
    )
    print(f"       CSV saved to: {csv_path}")

    if stats.excel_truncated:
        print(
            f"[WARN] Excel sheet for {file_path.name} hit Excel's row limit. "
            f"Use the CSV as the full output."
        )


# ============================================================
# MAIN
# ============================================================
def main() -> None:
    ensure_runtime_directories()
    cutoff_date = date.fromisoformat(CUTOFF_DATE_TEXT)
    workbook = create_workbook()

    with requests.Session() as session:
        session.headers.update(HEADERS)
        input_files = collect_input_files(session)
        if not input_files:
            print("[ERROR] No sitemap files were downloaded or found locally.")
            return

        for file_path in input_files:
            try:
                process_top_level_file(
                    file_path=file_path,
                    workbook=workbook,
                    session=session,
                    cutoff_date=cutoff_date,
                )
            except Exception as exc:
                print(f"[ERROR] Failed to process {file_path.name}: {exc}")

    workbook.save(EXCEL_PATH)
    print(f"[DONE] Excel workbook saved to: {EXCEL_PATH}")


if __name__ == "__main__":
    main()
