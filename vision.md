# Vision

## Goal
This project should support a two-stage pipeline:
1. download and filter sitemap URLs into Excel
2. read those Excel URLs, crawl each page, save markdown locally, and write the markdown path back into the workbook

## Current Workflow
1. Update the source list and cutoff date in `sitemap_date_finder.py` when needed.
2. Run `python sitemap_date_finder.py`.
3. The script downloads each top-level sitemap into `downloaded_sitemaps/`.
4. The script uses `requests` first and falls back to a browser-impersonated client when a site blocks normal HTTP requests or serves a browser challenge page instead of XML.
5. The script recursively walks `sitemapindex` and `urlset` XML structures.
6. URLs are kept only when `lastmod` is on or after the configured cutoff date.
7. Per-site CSV files and a combined Excel workbook are written to `recent_sitemap_outputs/`.
8. Run `python scrape_excel_urls_to_markdown.py` against the Excel workbook from stage one.
9. By default, the second-stage script uses `recent_sitemap_outputs/recent_urls.xlsx`, auto-detects a URL column such as `link`, and processes all sheets unless a specific sheet is passed.
10. The second-stage script crawls each URL with Crawl4AI, saves raw markdown under `scraped_markdown/`, and writes the relative markdown path plus scrape metadata back into Excel.
11. The second-stage script saves the workbook after every processed row so it can resume safely.
12. If one site fails to download or one page fails to crawl, the relevant script logs the error and continues with the rest.

## Active Sources
- `https://www.motortrend.com/`
- `https://www.autonews.com/`
- `https://www.spglobal.com/automotive-insights/en`
- `https://www.automotiveworld.com/`

## Important Files
- `sitemap_date_finder.py`: Stage-one sitemap-to-Excel script.
- `scrape_excel_urls_to_markdown.py`: Stage-two Excel-to-markdown crawler.
- `requirements.txt`: Minimal Python dependencies for the project.
- `vision.md`: Project workflow and change log. Update this whenever code or process changes.
- `downloaded_sitemaps/`: Runtime download folder created automatically.
- `recent_sitemap_outputs/`: Runtime output folder created automatically.
- `scraped_markdown/`: Default runtime folder for saved markdown files.

## Maintenance Rule
Whenever any code or workflow changes, update this file in the same change.

Always update:
- `Current Workflow`
- `Active Sources`
- `Important Files`
- `Change Log`

## Known Behavior
- Some sites may return HTTP 403 or a 200 HTML browser-challenge page to plain `requests` traffic. The script retries those downloads with a browser-impersonated client.

## Change Log

### 2026-03-26
- Removed the old manually downloaded XML files and their old output files.
- Switched the pipeline to auto-download top-level sitemap files from the configured base URLs.
- Simplified the project so the script is the main source of truth for the workflow.
- Added `.gitignore` so generated downloads and outputs do not clutter the repo.
- Added this `vision.md` file as the project working note and update log.
- Added a compact fallback for Akamai-blocked sites like `spglobal.com` using `curl_cffi`.
- Extended the fallback so HTML challenge pages are retried too, not just HTTP 403 responses.

### 2026-03-27
- Added `scrape_excel_urls_to_markdown.py` as a second-stage script that reads Excel URLs, crawls them with Crawl4AI, saves markdown locally, and writes results back into the workbook.
- Added `crawl4ai` to project requirements.
- Added `scraped_markdown/` to `.gitignore`.
- Made the second-stage script runnable with no required CLI flags in this repo by defaulting to the stage-one workbook, auto-detecting the URL column, and processing all sheets when no sheet is specified.
