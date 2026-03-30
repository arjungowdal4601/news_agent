from __future__ import annotations

import csv
import gzip
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from openpyxl import Workbook

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

ROOT = Path(__file__).resolve().parent
DOWNLOAD_DIR = ROOT / "downloaded_sitemaps"
OUTPUT_DIR = ROOT / "recent_sitemap_outputs"
EXCEL_PATH = OUTPUT_DIR / "recent_urls.xlsx"
BASE_URLS = [
    "https://www.motortrend.com/",
    "https://www.autonews.com/",
    "https://www.spglobal.com/automotive-insights/en",
    "https://www.automotiveworld.com/",
]

CUTOFF_DATE_TEXT = "2026-03-25"
KEEP_URLS_WITHOUT_LASTMOD = False
TIMEOUT = 60
MAX_EXCEL_ROWS = 1_048_575
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36"
    )
}


@dataclass
class Stats:
    csv_rows: int = 0
    excel_rows: int = 0
    expanded: int = 0
    skipped: int = 0
    truncated: bool = False


def to_date(text: str) -> date | None:
    text = text.strip() if text else ""
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def date_in_url(url: str) -> date | None:
    match = DATE_RE.search(url)
    return to_date(match.group(1)) if match else None


def xml_root(content: bytes, source: str = "") -> ET.Element:
    if source.lower().endswith(".gz") or content[:2] == b"\x1f\x8b":
        try:
            content = gzip.decompress(content)
        except OSError:
            pass
    return ET.fromstring(content.decode("utf-8-sig", errors="replace").strip())


def ns(root: ET.Element) -> dict[str, str]:
    return {"sm": root.tag.split("}", 1)[0][1:] if root.tag.startswith("{") else NS}


def text(node: ET.Element, tag: str, namespace: dict[str, str]) -> str:
    child = node.find(f"sm:{tag}", namespace)
    return child.text.strip() if child is not None and child.text else ""


def is_xml_response(response) -> bool:
    body = response.content.lstrip()
    if body.startswith(b"\xef\xbb\xbf"):
        body = body[3:]
    return body[:32].lower().startswith((b"<?xml", b"<urlset", b"<sitemapindex"))


def fetch_bytes(url: str, session: requests.Session) -> bytes:
    response = session.get(url, timeout=TIMEOUT)
    if response.ok and is_xml_response(response):
        return response.content

    if curl_requests is None:
        response.raise_for_status()
        return response.content

    response = curl_requests.get(url, headers=dict(session.headers), impersonate="chrome136", timeout=TIMEOUT)
    response.raise_for_status()
    return response.content


def file_name(base_url: str) -> str:
    parsed = urlparse(base_url)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", f"{parsed.netloc}{parsed.path}").strip("_")
    return f"{slug or 'sitemap'}_sitemap.xml"


def keep_url(lastmod: str, cutoff: date) -> bool:
    parsed = to_date(lastmod)
    return KEEP_URLS_WITHOUT_LASTMOD if parsed is None else parsed >= cutoff


def expand_child(child_url: str, parent_lastmod: str, cutoff: date) -> bool:
    return (to_date(parent_lastmod) or date_in_url(child_url) or cutoff) >= cutoff


def write_row(writer: csv.DictWriter, sheet, stats: Stats, link: str, lastmod: str) -> None:
    writer.writerow({"link": link, "lastmod": lastmod})
    stats.csv_rows += 1
    if stats.excel_rows < MAX_EXCEL_ROWS:
        sheet.append([link, lastmod])
        stats.excel_rows += 1
    else:
        stats.truncated = True


def walk(root: ET.Element, session: requests.Session, cutoff: date, writer: csv.DictWriter, sheet, stats: Stats, seen: set[str]) -> None:
    namespace = ns(root)
    kind = root.tag.split("}", 1)[-1]

    if kind == "urlset":
        for node in root.findall("./sm:url", namespace):
            link, lastmod = text(node, "loc", namespace), text(node, "lastmod", namespace)
            if link and keep_url(lastmod, cutoff):
                write_row(writer, sheet, stats, link, lastmod)
        return

    if kind != "sitemapindex":
        raise ValueError(f"Unsupported sitemap root tag: {root.tag}")

    for node in root.findall("./sm:sitemap", namespace):
        child_url, parent_lastmod = text(node, "loc", namespace), text(node, "lastmod", namespace)
        if not child_url or child_url in seen:
            continue
        if not expand_child(child_url, parent_lastmod, cutoff):
            stats.skipped += 1
            continue
        seen.add(child_url)
        stats.expanded += 1
        try:
            walk(xml_root(fetch_bytes(child_url, session), child_url), session, cutoff, writer, sheet, stats, seen)
        except Exception as exc:
            print(f"[WARN] Could not open child sitemap: {child_url} -> {exc}")


def process_file(path: Path, workbook: Workbook, session: requests.Session, cutoff: date) -> tuple[Path, bool]:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", path.stem).strip("_") or "output"
    csv_path = OUTPUT_DIR / f"{stem}_after_{cutoff.isoformat()}.csv"
    sheet = workbook.create_sheet(title=stem[:31])
    sheet.append(["link", "lastmod"])
    stats = Stats()

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["link", "lastmod"])
        writer.writeheader()
        walk(xml_root(path.read_bytes(), path.name), session, cutoff, writer, sheet, stats, set())

    print(f"[DONE] {path.name} -> rows={stats.csv_rows}, expanded_child_sitemaps={stats.expanded}, skipped_child_sitemaps={stats.skipped}")
    print(f"       CSV saved to: {csv_path}")
    if stats.truncated:
        print(f"[WARN] Excel sheet for {path.name} hit Excel's row limit. Use the CSV as the full output.")
    return csv_path, stats.truncated


def download_top_level_sitemaps(session: requests.Session) -> list[Path]:
    files: list[Path] = []
    for base_url in BASE_URLS:
        sitemap_url = base_url.rstrip("/") + "/sitemap.xml"
        path = DOWNLOAD_DIR / file_name(base_url)
        try:
            path.write_bytes(fetch_bytes(sitemap_url, session))
            print(f"[FETCH] {sitemap_url} -> {path}")
            files.append(path)
        except Exception as exc:
            print(f"[ERROR] Failed to download sitemap for {base_url}: {exc}")
    return files


def main() -> None:
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    cutoff = date.fromisoformat(CUTOFF_DATE_TEXT)
    workbook = Workbook()
    workbook.remove(workbook.active)

    with requests.Session() as session:
        session.headers.update(HEADERS)
        files = download_top_level_sitemaps(session)
        if not files:
            print("[ERROR] No sitemap files were downloaded.")
            return
        csv_outputs: list[tuple[Path, bool]] = []
        for path in files:
            try:
                csv_outputs.append(process_file(path, workbook, session, cutoff))
            except Exception as exc:
                print(f"[ERROR] Failed to process {path.name}: {exc}")

    workbook.save(EXCEL_PATH)
    print(f"[DONE] Excel workbook saved to: {EXCEL_PATH}")

    for csv_path, truncated in csv_outputs:
        if truncated:
            print(f"[KEEP] CSV retained because the Excel sheet was truncated: {csv_path}")
            continue
        try:
            csv_path.unlink(missing_ok=True)
            print(f"[CLEANUP] Deleted merged CSV: {csv_path}")
        except Exception as exc:
            print(f"[WARN] Could not delete CSV {csv_path}: {exc}")


if __name__ == "__main__":
    main()
