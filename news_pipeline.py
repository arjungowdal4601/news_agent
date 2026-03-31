from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from build_final_newsletter import run_newsletter_stage
from export_newsletter_html import run_html_stage
from scrape_excel_urls_to_markdown import run_scrape_stage
from semantic_router import run_route_stage
from sitemap_date_finder import run_sitemap_stage

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

DEFAULT_CUTOFF_DATE = os.getenv("NEWS_CUTOFF_DATE", "2026-03-25")
DEFAULT_WORKBOOK_PATH = ROOT / "recent_sitemap_outputs" / "recent_urls.xlsx"
DEFAULT_FINAL_DIR = ROOT / "recent_sitemap_outputs" / "final_newsletters"
DEFAULT_FINAL_MARKDOWN = DEFAULT_FINAL_DIR / "automobile_tech_newsletter.md"
DEFAULT_FINAL_HTML = DEFAULT_FINAL_DIR / "automobile_tech_newsletter.html"


@dataclass(frozen=True)
class PipelineConfig:
    cutoff_date: date
    sheet_name: str | None
    headless: bool
    force_sitemaps: bool
    force_scrape: bool
    force_route: bool
    force_newsletter: bool
    force_html: bool
    workbook_path: Path
    scrape_output_dir: str
    route_output_dir: str
    newsletter_output_dir: Path
    html_output_path: Path
    openai_api_key: str
    openai_base_url: str
    router_model: str
    newsletter_model: str
    html_model: str
    user_need: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full automotive news pipeline from sitemap download through final HTML export."
    )
    parser.add_argument(
        "--cutoff-date",
        default=DEFAULT_CUTOFF_DATE,
        help="Cutoff date for sitemap URL inclusion, in YYYY-MM-DD format.",
    )
    parser.add_argument("--sheet-name", help="Limit scrape, route, newsletter, and HTML stages to one workbook sheet.")
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run Crawl4AI in headless mode. Use --no-headless for visible browsing.",
    )
    parser.add_argument("--force-sitemaps", action="store_true", help="Redownload sitemaps and rebuild the workbook.")
    parser.add_argument("--force-scrape", action="store_true", help="Rescrape rows even if markdown already exists.")
    parser.add_argument("--force-route", action="store_true", help="Re-run semantic routing even if rows are already processed.")
    parser.add_argument("--force-newsletter", action="store_true", help="Rebuild the final markdown newsletter.")
    parser.add_argument("--force-html", action="store_true", help="Rebuild the final HTML newsletter.")
    return parser.parse_args()


def load_config(args: argparse.Namespace) -> PipelineConfig:
    cutoff_date = date.fromisoformat(str(args.cutoff_date))
    openai_api_key = os.getenv("NEWS_AGENT_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    user_need = os.getenv("USER_NEED", "").strip()
    if not openai_api_key:
        raise EnvironmentError("Set OPENAI_API_KEY or NEWS_AGENT_OPENAI_API_KEY before running news_pipeline.py.")
    if not user_need or "REPLACE THIS WITH WHAT YOU NEED" in user_need.upper():
        raise ValueError("Set USER_NEED in .env before running news_pipeline.py.")

    return PipelineConfig(
        cutoff_date=cutoff_date,
        sheet_name=args.sheet_name,
        headless=args.headless,
        force_sitemaps=args.force_sitemaps,
        force_scrape=args.force_scrape,
        force_route=args.force_route,
        force_newsletter=args.force_newsletter,
        force_html=args.force_html,
        workbook_path=DEFAULT_WORKBOOK_PATH,
        scrape_output_dir="scraped_markdown",
        route_output_dir="processed_selected_markdown",
        newsletter_output_dir=DEFAULT_FINAL_DIR,
        html_output_path=DEFAULT_FINAL_HTML,
        openai_api_key=openai_api_key,
        openai_base_url=os.getenv("NEWS_AGENT_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL", ""),
        router_model=os.getenv("NEWS_AGENT_LLM_MODEL", "gpt-5.4-nano"),
        newsletter_model=os.getenv("NEWSLETTER_LLM_MODEL") or os.getenv("NEWS_AGENT_LLM_MODEL", "gpt-5.4-nano"),
        html_model=os.getenv("NEWSLETTER_HTML_MODEL", "gpt-5.4"),
        user_need=user_need,
    )


def run_pipeline(config: PipelineConfig) -> None:
    sitemap_changed = run_sitemap_stage(
        cutoff_date=config.cutoff_date,
        workbook_path=config.workbook_path,
        force=config.force_sitemaps,
    )

    scrape_force = config.force_scrape or sitemap_changed
    scrape_changed = run_scrape_stage(
        excel_path=config.workbook_path,
        sheet_name=config.sheet_name,
        output_dir=config.scrape_output_dir,
        force_rescrape=scrape_force,
        headless=config.headless,
    )

    route_force = config.force_route or scrape_force or scrape_changed
    route_changed = run_route_stage(
        excel_path=config.workbook_path,
        sheet_name=config.sheet_name,
        output_dir=config.route_output_dir,
        force_reprocess=route_force,
        user_need=config.user_need,
        api_key=config.openai_api_key,
        model_name=config.router_model,
        base_url=config.openai_base_url,
    )

    newsletter_force = config.force_newsletter or route_force or route_changed or config.sheet_name is not None
    newsletter_changed = run_newsletter_stage(
        excel_path=config.workbook_path,
        sheet_name=config.sheet_name,
        output_dir=config.newsletter_output_dir,
        api_key=config.openai_api_key,
        model_name=config.newsletter_model,
        base_url=config.openai_base_url,
        force_rebuild=newsletter_force,
    )

    html_force = config.force_html or newsletter_force or newsletter_changed or config.sheet_name is not None
    run_html_stage(
        input_markdown=DEFAULT_FINAL_MARKDOWN,
        output_html=config.html_output_path,
        api_key=config.openai_api_key,
        model_name=config.html_model,
        base_url=config.openai_base_url,
        force_rebuild=html_force,
    )


def main() -> None:
    args = parse_args()
    config = load_config(args)
    run_pipeline(config)


if __name__ == "__main__":
    main()
