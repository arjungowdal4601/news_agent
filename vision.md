# Vision

## Goal
This project should take a fixed list of automotive news site URLs, download each site's top-level `sitemap.xml`, expand any child sitemaps, filter URLs by `lastmod`, and export the recent links to CSV and Excel.

## Current Workflow
1. Update the source list and cutoff date in `sitemap_recent_filter.py` when needed.
2. Run `python sitemap_recent_filter.py`.
3. The script downloads each top-level sitemap into `downloaded_sitemaps/`.
4. The script recursively walks `sitemapindex` and `urlset` XML structures.
5. URLs are kept only when `lastmod` is on or after the configured cutoff date.
6. Per-site CSV files and a combined Excel workbook are written to `recent_sitemap_outputs/`.
7. If one site fails to download, the script logs the error and continues with the rest.

## Active Sources
- `https://www.motortrend.com/`
- `https://www.autonews.com/`
- `https://www.spglobal.com/automotive-insights/en`
- `https://www.automotiveworld.com/`

## Important Files
- `sitemap_recent_filter.py`: Main automation script.
- `vision.md`: Project workflow and change log. Update this whenever code or process changes.
- `downloaded_sitemaps/`: Runtime download folder created automatically.
- `recent_sitemap_outputs/`: Runtime output folder created automatically.

## Maintenance Rule
Whenever any code or workflow changes, update this file in the same change.

Always update:
- `Current Workflow`
- `Active Sources`
- `Important Files`
- `Change Log`

## Known Issue
- On March 26, 2026, `https://www.spglobal.com/automotive-insights/en/sitemap.xml` returned HTTP 403 from this environment. The script now skips that site without stopping the full run.

## Change Log

### 2026-03-26
- Removed the old manually downloaded XML files and their old output files.
- Switched the pipeline to auto-download top-level sitemap files from the configured base URLs.
- Simplified the project so the script is the main source of truth for the workflow.
- Added `.gitignore` so generated downloads and outputs do not clutter the repo.
- Added this `vision.md` file as the project working note and update log.
