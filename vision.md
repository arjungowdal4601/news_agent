# Vision

## Goal
This project should support a four-stage pipeline:
1. download and filter sitemap URLs into Excel
2. read those Excel URLs, crawl each page, save markdown locally, and write the markdown path back into the workbook
3. route scraped markdown against a user need, save relevant rewritten markdown locally, and write the processed path back into the workbook
4. batch selected processed markdown files sheet by sheet and generate a final technical-newsletter markdown file

## Current Workflow
1. Update the source list and cutoff date in `sitemap_date_finder.py` when needed.
2. Run `python sitemap_date_finder.py`.
3. The script downloads each top-level sitemap into `downloaded_sitemaps/`.
4. The script uses `requests` first and falls back to a browser-impersonated client when a site blocks normal HTTP requests or serves a browser challenge page instead of XML.
5. The script recursively walks `sitemapindex` and `urlset` XML structures.
6. URLs are kept only when `lastmod` is on or after the configured cutoff date.
7. Per-site CSV files are created during processing, merged into a combined Excel workbook in `recent_sitemap_outputs/`, and then deleted when the Excel sheet was fully written.
8. Run `python scrape_excel_urls_to_markdown.py` against the Excel workbook from stage one.
9. By default, the second-stage script uses `recent_sitemap_outputs/recent_urls.xlsx`, auto-detects a URL column such as `link`, and processes all sheets unless a specific sheet is passed.
10. The second-stage script crawls each URL with Crawl4AI, saves raw markdown under `scraped_markdown/`, and writes `markdown_path` plus `scrape_status` back into Excel.
11. The second-stage script saves the workbook after every processed row so it can resume safely.
12. Set `OPENAI_API_KEY` and `USER_NEED` in `.env`, then run `python semantic_router.py`.
13. The third-stage script reads each row's `markdown_path`, uses LangChain with a small OpenAI model to decide whether the article should be selected for the user need, and applies a conservative breakthrough-only threshold that rejects generic car-tech coverage and ordinary vehicle reviews.
14. The workbook is updated with `relevance_score` for every processed row plus explicit selection and save statuses, and matching rows are saved under `processed_selected_markdown/` with only relevant source image URLs retained in the processed markdown.
15. The third-stage script saves the workbook after every processed row so it can resume safely.
16. Run `python build_final_newsletter.py` to read the selected processed markdown files from the workbook, shortlist the strongest news sheet by sheet in batches of 5, and write one final markdown newsletter under `recent_sitemap_outputs/final_newsletters/`.
17. The newsletter stage keeps only news with strong evidence, technical grounding, breakthrough technology, or significant automobile-technology issues, and drops weaker or repetitive items again before writing the final markdown.
18. If one site fails to download, one page fails to crawl, or one LLM call fails, the relevant script logs the error and continues with the rest.

## Active Sources
- `https://www.motortrend.com/`
- `https://www.autonews.com/`
- `https://www.spglobal.com/automotive-insights/en`
- `https://www.automotiveworld.com/`

## Important Files
- `sitemap_date_finder.py`: Stage-one sitemap-to-Excel script.
- `scrape_excel_urls_to_markdown.py`: Stage-two Excel-to-markdown crawler.
- `semantic_router.py`: Stage-three semantic selection and rewrite script.
- `build_final_newsletter.py`: Stage-four newsletter builder that curates selected processed markdown files into one final markdown newsletter.
- `prompts.py`: Shared LangChain prompt template for semantic routing.
- `.env`: Local runtime configuration for the semantic router, including the OpenAI API key, model name, and user need prompt.
- `requirements.txt`: Python dependencies for the project.
- `vision.md`: Project workflow and change log. Update this whenever code or process changes.
- `downloaded_sitemaps/`: Runtime download folder created automatically.
- `recent_sitemap_outputs/`: Runtime output folder created automatically.
- `scraped_markdown/`: Default runtime folder for saved markdown files.
- `processed_selected_markdown/`: Default runtime folder for saved processed markdown files.
- `recent_sitemap_outputs/final_newsletters/`: Runtime folder for generated final newsletter markdown files.

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

### 2026-03-30
- Simplified the second-stage workbook output to keep only `markdown_path` and `scrape_status`.
- Updated the stage-one script to delete merged CSV files after the Excel workbook is successfully written, while keeping truncated CSV outputs when Excel hits its row limit.
- Added `semantic_router.py` as a third-stage script that reads workbook markdown paths, routes articles against `USER_NEED`, and saves rewritten relevant markdown back to disk.
- Added `prompts.py` with the LangChain prompt template used by the semantic router.
- Added `langchain-core` and `langchain-openai` to project requirements.
- Added `.env` loading through `python-dotenv` so the semantic router can read `OPENAI_API_KEY`, `NEWS_AGENT_LLM_MODEL`, and `USER_NEED` from the project root.
- Updated the semantic router so Excel clearly records whether each link was selected, and so processed markdown keeps only relevant source image URLs from the original article.
- Tightened the semantic-router prompt and default `USER_NEED` so selection only passes articles centered on genuine breakthrough automotive technology or major step-change engineering innovation.
- Added `relevance_score` output so every processed row gets a numeric relevance score in Excel, even when the row is not selected.
- Added `build_final_newsletter.py` as a fourth-stage script that processes selected markdown files sheet by sheet in batches of 5 and produces one final markdown newsletter with only the strongest technical news.
- Added newsletter-builder prompt templates to `prompts.py`.
- Added `recent_sitemap_outputs/final_newsletters/` to `.gitignore`.
- Added `processed_selected_markdown/` to `.gitignore`.
