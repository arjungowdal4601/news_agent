from __future__ import annotations
import csv
import gzip
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests
from openpyxl import Workbook

# ============================================================
# CONFIGURATION
# ============================================================
# Put your four XML files in this folder.
INPUT_DIR = Path(".")

# Top-level XML files you want to process.
INPUT_FILES = [
    "sitemap.xml",
    "sitemap_index.xml",
    "download.xml",
    "XML Sitemap.xml",
]

# Only keep URLs whose lastmod date is ON or AFTER this cutoff date.
# Example: "2026-03-20"
CUTOFF_DATE = "2026-02-20"

# Output folder for filtered CSV + Excel.
OUTPUT_DIR = INPUT_DIR / "recent_sitemap_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# Excel workbook with one sheet per top-level sitemap.
EXCEL_PATH = OUTPUT_DIR / "recent_urls.xlsx"

# If a final URL does not have a <lastmod>, should we keep it?
# Usually False is better because your whole goal is date-based filtering.
KEEP_URLS_WITHOUT_LASTMOD = False

REQUEST_TIMEOUT = 60
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36"
    )
}

# Excel row limit (1 header row + 1,048,575 data rows)
EXCEL_MAX_DATA_ROWS = 1_048_575


# ============================================================
# DATE HELPERS
# ============================================================
def to_date(value: str) -> Optional[date]:
    """
    Convert many common sitemap date formats into a Python date.

    Handles examples like:
    - 2026-03-25
    - 2026-03-25T13:30:49.484Z
    - 2026-03-26T05:46:02+00:00
    - 2026-03-24T19:50:10Z

    Returns None if parsing fails.
    """
    if not value:
        return None

    text = value.strip()
    if not text:
        return None

    # Fast path: many sitemap values start with YYYY-MM-DD.
    if len(text) >= 10:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass

    # Try full datetime parsing.
    try:
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return None


DATE_IN_URL_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def extract_date_from_url(url: str) -> Optional[date]:
    """
    Some sitemap indexes do not provide <lastmod> in the parent sitemap,
    but the child sitemap URL itself contains a date.

    Example:
    https://.../sitemap3/2026-03-19/?outputType=xml
    """
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
    """Remove XML namespace from a tag name."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


ndefault_namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"


def get_namespace(root: ET.Element) -> dict[str, str]:
    """
    Return the XML namespace mapping needed by ElementTree.
    Sitemap files usually use the sitemaps.org namespace.
    """
    if root.tag.startswith("{"):
        return {"sm": root.tag.split("}", 1)[0][1:]}
    return {"sm": ndefault_namespace}


def child_text(parent: ET.Element, tag_name: str, ns: dict[str, str]) -> str:
    """Read a direct child node's text safely."""
    node = parent.find(f"sm:{tag_name}", ns)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def parse_xml_bytes(content: bytes, source_name: str = "") -> ET.Element:
    """
    Parse XML content. If the sitemap is gzipped (.xml.gz), decompress first.
    """
    is_gzip = source_name.lower().endswith(".gz") or content[:2] == b"\x1f\x8b"
    if is_gzip:
        try:
            content = gzip.decompress(content)
        except OSError:
            # Sometimes the server already sends decompressed content.
            pass

    text = content.decode("utf-8-sig", errors="replace").strip()
    return ET.fromstring(text)


# ============================================================
# NETWORK HELPERS
# ============================================================
def fetch_remote_root(url: str, session: requests.Session) -> ET.Element:
    """Download and parse a remote child sitemap."""
    response = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return parse_xml_bytes(response.content, source_name=url)


# ============================================================
# OUTPUT HELPERS
# ============================================================
def safe_stem(name: str) -> str:
    """Create a filesystem-safe base name."""
    raw = Path(name).stem
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in raw).strip("_") or "output"


def safe_sheet_name(name: str) -> str:
    """Create an Excel-safe worksheet name."""
    for ch in ['\\', '/', '*', '[', ']', ':', '?']:
        name = name.replace(ch, "_")
    return name[:31]


def write_result_row(
    link: str,
    lastmod: str,
    csv_writer: csv.DictWriter,
    worksheet,
    stats: dict,
) -> None:
    """Write one filtered URL row to CSV and Excel."""
    csv_writer.writerow({"link": link, "lastmod": lastmod})
    stats["csv_rows"] += 1

    if worksheet is not None and stats["excel_rows"] < EXCEL_MAX_DATA_ROWS:
        worksheet.append([link, lastmod])
        stats["excel_rows"] += 1
    else:
        stats["excel_truncated"] = True


# ============================================================
# FILTERING LOGIC
# ============================================================
def should_keep_final_url(lastmod_text: str, cutoff: date) -> bool:
    """
    Decide whether a final URL row should be kept.

    We compare only the DATE part because your use case is date-based,
    not second-by-second timestamp comparison.
    """
    lastmod_date = to_date(lastmod_text)

    if lastmod_date is None:
        return KEEP_URLS_WITHOUT_LASTMOD

    return lastmod_date >= cutoff



def should_expand_child_sitemap(loc: str, parent_lastmod_text: str, cutoff: date) -> bool:
    """
    Decide whether a child sitemap is worth opening.

    This is where most of the speed improvement comes from.

    Priority:
    1. Use parent <lastmod> if present.
    2. If parent <lastmod> is missing, try to extract a date from the child sitemap URL.
    3. If neither is available, expand it anyway because we cannot safely skip it.
    """
    parent_lastmod_date = to_date(parent_lastmod_text)
    if parent_lastmod_date is not None:
        return parent_lastmod_date >= cutoff

    child_date_from_url = extract_date_from_url(loc)
    if child_date_from_url is not None:
        return child_date_from_url >= cutoff

    # Example: a "latest" sitemap URL has no clear date in the URL.
    # We keep it because it is likely to contain recent content.
    return True


# ============================================================
# CORE RECURSIVE WALKER
# ============================================================
def walk_sitemap(
    root: ET.Element,
    session: requests.Session,
    cutoff: date,
    csv_writer: csv.DictWriter,
    worksheet,
    stats: dict,
    visited_sitemaps: set[str],
) -> None:
    """
    Recursively process either:
    - a <urlset>   -> final URLs
    - a <sitemapindex> -> child sitemaps
    """
    ns = get_namespace(root)
    root_type = strip_namespace(root.tag)

    if root_type == "urlset":
        for url_node in root.findall("./sm:url", ns):
            link = child_text(url_node, "loc", ns)
            lastmod = child_text(url_node, "lastmod", ns)

            if not link:
                continue

            if should_keep_final_url(lastmod, cutoff):
                write_result_row(link, lastmod, csv_writer, worksheet, stats)

        return

    if root_type == "sitemapindex":
        for sitemap_node in root.findall("./sm:sitemap", ns):
            child_loc = child_text(sitemap_node, "loc", ns)
            parent_lastmod = child_text(sitemap_node, "lastmod", ns)

            if not child_loc:
                continue

            if child_loc in visited_sitemaps:
                continue

            if not should_expand_child_sitemap(child_loc, parent_lastmod, cutoff):
                stats["skipped_child_sitemaps"] += 1
                continue

            visited_sitemaps.add(child_loc)
            stats["expanded_child_sitemaps"] += 1

            try:
                child_root = fetch_remote_root(child_loc, session)
                walk_sitemap(
                    root=child_root,
                    session=session,
                    cutoff=cutoff,
                    csv_writer=csv_writer,
                    worksheet=worksheet,
                    stats=stats,
                    visited_sitemaps=visited_sitemaps,
                )
            except Exception as exc:
                print(f"[WARN] Could not open child sitemap: {child_loc} -> {exc}")

        return

    raise ValueError(f"Unsupported sitemap root tag: {root.tag}")


# ============================================================
# TOP-LEVEL FILE PROCESSOR
# ============================================================
def process_top_level_file(file_path: Path, workbook: Workbook, session: requests.Session, cutoff: date) -> None:
    """
    Process one of your uploaded top-level XML files and generate:
    - one filtered CSV
    - one Excel sheet in the shared workbook
    """
    stem = safe_stem(file_path.name)
    csv_path = OUTPUT_DIR / f"{stem}_after_{cutoff.isoformat()}.csv"

    worksheet = workbook.create_sheet(title=safe_sheet_name(stem))
    worksheet.append(["link", "lastmod"])

    stats = {
        "csv_rows": 0,
        "excel_rows": 0,
        "excel_truncated": False,
        "expanded_child_sitemaps": 0,
        "skipped_child_sitemaps": 0,
    }

    visited_sitemaps: set[str] = set()

    root = parse_xml_bytes(file_path.read_bytes(), source_name=file_path.name)

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["link", "lastmod"])
        writer.writeheader()

        walk_sitemap(
            root=root,
            session=session,
            cutoff=cutoff,
            csv_writer=writer,
            worksheet=worksheet,
            stats=stats,
            visited_sitemaps=visited_sitemaps,
        )

    print(
        f"[DONE] {file_path.name} -> rows={stats['csv_rows']}, "
        f"expanded_child_sitemaps={stats['expanded_child_sitemaps']}, "
        f"skipped_child_sitemaps={stats['skipped_child_sitemaps']}"
    )
    print(f"       CSV saved to: {csv_path}")

    if stats["excel_truncated"]:
        print(
            f"[WARN] Excel sheet for {file_path.name} hit Excel's row limit. "
            f"Use the CSV as the full output."
        )


# ============================================================
# MAIN
# ============================================================
def main() -> None:
    cutoff = date.fromisoformat(CUTOFF_DATE)

    workbook = Workbook()
    workbook.remove(workbook.active)

    with requests.Session() as session:
        for file_name in INPUT_FILES:
            file_path = INPUT_DIR / file_name

            if not file_path.exists():
                print(f"[SKIP] File not found: {file_path}")
                continue

            try:
                process_top_level_file(
                    file_path=file_path,
                    workbook=workbook,
                    session=session,
                    cutoff=cutoff,
                )
            except Exception as exc:
                print(f"[ERROR] Failed to process {file_name}: {exc}")

    workbook.save(EXCEL_PATH)
    print(f"[DONE] Excel workbook saved to: {EXCEL_PATH}")


if __name__ == "__main__":
    main()
