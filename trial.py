import asyncio
from pathlib import Path
from typing import List
from urllib.parse import urlparse
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
import requests
from xml.etree import ElementTree

async def crawl_sequential(urls: List[str]):
    print("\n=== Sequential Crawling with Session Reuse ===")

    browser_config = BrowserConfig(
        headless=True,
        # For better performance in Docker or low-memory environments:
        extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
    )

    session_id = "session1"  # Reuse the same session across all URLs
    output_dir = Path("markdown_output")
    output_dir.mkdir(exist_ok=True)

    # Create the crawler (opens the browser)
    crawler = AsyncWebCrawler(config=browser_config)
    await crawler.start()

    try:
        for url in urls:
            crawl_config = CrawlerRunConfig(
                markdown_generator=DefaultMarkdownGenerator(),
                session_id=session_id
            )

            result = await crawler.arun(
                url=url,
                config=crawl_config
            )

            if result.success and result.markdown:
                parsed = urlparse(url)

                if parsed.path.strip("/"):
                    filename = f"{parsed.netloc}_{parsed.path.strip('/').replace('/', '_')}.md"
                else:
                    filename = f"{parsed.netloc}_index.md"

                file_path = output_dir / filename

                markdown_text = (
                    result.markdown.raw_markdown
                    if hasattr(result.markdown, "raw_markdown")
                    else str(result.markdown)
                )

                file_path.write_text(markdown_text, encoding="utf-8")
                print(f"Successfully crawled and saved: {file_path}")
            else:
                print(f"Failed: {url} - Error: {result.error_message}")
    finally:
        await crawler.close()

def get_pydantic_ai_docs_urls():
    """
    Fetches all URLs from the Pydantic AI documentation.
    Uses the sitemap (https://www.automotiveworld.com/sitemap.xml) to get these URLs.
    
    Returns:
        List[str]: List of URLs
    """
    sitemap_url = "https://www.automotiveworld.com/sitemap.xml"
    try:
        response = requests.get(sitemap_url, timeout=30)
        response.raise_for_status()

        # Parse the XML
        root = ElementTree.fromstring(response.content)

        # Extract all URLs from the sitemap
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = [loc.text for loc in root.findall('.//ns:loc', namespace)]

        return urls
    except Exception as e:
        print(f"Error fetching sitemap: {e}")
        return []

async def main():
    urls = get_pydantic_ai_docs_urls()
    if urls:
        print(f"Found {len(urls)} URLs to crawl")
        await crawl_sequential(urls)
    else:
        print("No URLs found to crawl")

if __name__ == "__main__":
    asyncio.run(main())