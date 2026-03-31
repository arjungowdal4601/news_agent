from __future__ import annotations

import argparse
import html
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from prompts import newsletter_html_prompt

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

DEFAULT_INPUT_MARKDOWN = Path("recent_sitemap_outputs") / "final_newsletters" / "automobile_tech_newsletter.md"
DEFAULT_OUTPUT_HTML = Path("recent_sitemap_outputs") / "final_newsletters" / "automobile_tech_newsletter.html"
DEFAULT_HTML_MODEL = os.getenv("NEWSLETTER_HTML_MODEL", "gpt-5.4")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert the final newsletter markdown into one styled standalone HTML file."
    )
    parser.add_argument(
        "--input-markdown",
        default=str(DEFAULT_INPUT_MARKDOWN),
        help="Path to the final newsletter markdown file.",
    )
    parser.add_argument(
        "--output-html",
        default=str(DEFAULT_OUTPUT_HTML),
        help="Path to the output HTML file.",
    )
    return parser.parse_args()


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def repair_mojibake(text: str) -> str:
    repaired = text
    suspicious_tokens = ("Ã¢â‚¬", "Ã¢â‚¬â„¢", "Ã¢â‚¬Å“", "Ã¢â‚¬Â", "Ã¢â‚¬â€œ", "Ã¢â‚¬â€", "Ã‚", "Ã…â€š")
    if any(token in repaired for token in suspicious_tokens):
        try:
            candidate = repaired.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
            if candidate and candidate.count("Ã¢") < repaired.count("Ã¢"):
                repaired = candidate
        except UnicodeError:
            pass
    replacements = {
        "Ã¢â‚¬â„¢": "'",
        "Ã¢â‚¬Å“": '"',
        "Ã¢â‚¬Â": '"',
        "Ã¢â‚¬â€œ": "-",
        "Ã¢â‚¬â€": "-",
        "Ã‚ ": " ",
        "Ã‚": "",
    }
    for bad, good in replacements.items():
        repaired = repaired.replace(bad, good)
    return repaired


def init_model(
    *,
    api_key: str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
) -> ChatOpenAI:
    resolved_api_key = normalize_text(api_key or os.getenv("NEWS_AGENT_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"))
    if not resolved_api_key:
        raise EnvironmentError("Set OPENAI_API_KEY or NEWS_AGENT_OPENAI_API_KEY before running export_newsletter_html.py.")

    resolved_model = normalize_text(model_name or DEFAULT_HTML_MODEL) or DEFAULT_HTML_MODEL
    resolved_base_url = normalize_text(base_url or os.getenv("NEWS_AGENT_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL"))
    model_kwargs = {
        "model": resolved_model,
        "api_key": resolved_api_key,
        "max_retries": 2,
        "timeout": 120,
    }
    if resolved_base_url:
        model_kwargs["base_url"] = resolved_base_url
    return ChatOpenAI(**model_kwargs)


def extract_title(markdown_text: str) -> str:
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return "Automotive Tech Newsletter"


def extract_editor_note(markdown_text: str) -> str:
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("*") and stripped.endswith("*"):
            return stripped.strip("*").strip()
    return "This edition keeps only items with strong evidence and meaningful technical relevance."


def strip_html_fences(text: str) -> str:
    cleaned = normalize_text(text)
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```html\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^```\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def build_html_body(model: ChatOpenAI, newsletter_markdown: str) -> str:
    chain = newsletter_html_prompt | model
    response = chain.invoke({"newsletter_markdown": newsletter_markdown})
    content = strip_html_fences(getattr(response, "content", response))
    if not content:
        raise RuntimeError("HTML conversion returned empty content.")
    return content


def wrap_html_document(title: str, editor_note: str, body_html: str) -> str:
    generated_at = datetime.now().strftime("%B %d, %Y %H:%M")
    safe_title = html.escape(repair_mojibake(title))
    safe_editor_note = html.escape(repair_mojibake(editor_note))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    :root {{
      --bg: #eef2f6;
      --panel: #ffffff;
      --ink: #122033;
      --muted: #56657a;
      --accent: #0c6cf2;
      --accent-soft: #dce9ff;
      --rule: #d7dfeb;
      --shadow: 0 18px 40px rgba(18, 32, 51, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at top left, rgba(12,108,242,0.10), transparent 28%),
        linear-gradient(180deg, #f5f8fb 0%, var(--bg) 100%);
      color: var(--ink);
      font-family: "Segoe UI", "Trebuchet MS", sans-serif;
      line-height: 1.6;
    }}
    .page {{
      max-width: 980px;
      margin: 0 auto;
      padding: 40px 20px 64px;
    }}
    .hero {{
      background: linear-gradient(135deg, #10233f 0%, #0c6cf2 100%);
      color: #fff;
      border-radius: 28px;
      padding: 36px 34px;
      box-shadow: var(--shadow);
      margin-bottom: 28px;
    }}
    .eyebrow {{
      margin: 0 0 8px;
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      opacity: 0.8;
    }}
    h1 {{
      margin: 0 0 14px;
      font-size: clamp(30px, 4vw, 46px);
      line-height: 1.08;
      font-family: Georgia, "Times New Roman", serif;
    }}
    .editor-note {{
      margin: 0;
      max-width: 760px;
      font-size: 17px;
      color: rgba(255,255,255,0.92);
    }}
    .meta {{
      margin-top: 16px;
      font-size: 13px;
      color: rgba(255,255,255,0.78);
    }}
    .newsletter {{
      display: grid;
      gap: 24px;
    }}
    .sheet-section {{
      background: var(--panel);
      border: 1px solid var(--rule);
      border-radius: 24px;
      padding: 26px;
      box-shadow: var(--shadow);
    }}
    .sheet-section > h2 {{
      margin: 0 0 18px;
      padding-bottom: 12px;
      border-bottom: 2px solid var(--accent-soft);
      font-size: 22px;
      font-family: Georgia, "Times New Roman", serif;
    }}
    .story {{
      background: #f9fbfe;
      border: 1px solid #e4ebf3;
      border-radius: 18px;
      padding: 18px 18px 14px;
      margin-top: 16px;
    }}
    .story:first-of-type {{ margin-top: 0; }}
    .story h3 {{
      margin: 0 0 10px;
      font-size: 20px;
      line-height: 1.25;
    }}
    .story ul {{
      margin: 0 0 12px 18px;
      padding: 0;
    }}
    .story li {{
      margin-bottom: 8px;
    }}
    .source {{
      margin: 10px 0 0;
      font-size: 14px;
      color: var(--muted);
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
      word-break: break-word;
    }}
    a:hover {{ text-decoration: underline; }}
    .footer {{
      margin-top: 24px;
      color: var(--muted);
      font-size: 13px;
      text-align: center;
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <p class="eyebrow">Automobile Tech Briefing</p>
      <h1>{safe_title}</h1>
      <p class="editor-note">{safe_editor_note}</p>
      <p class="meta">Generated {generated_at}</p>
    </header>
    <div class="newsletter">
      {body_html}
    </div>
    <p class="footer">Standalone HTML newsletter file generated from the final markdown edition.</p>
  </main>
</body>
</html>
"""


def run_html_stage(
    *,
    input_markdown: Path | str = DEFAULT_INPUT_MARKDOWN,
    output_html: Path | str = DEFAULT_OUTPUT_HTML,
    api_key: str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
    force_rebuild: bool = True,
) -> bool:
    input_markdown_path = Path(input_markdown).resolve()
    output_html_path = Path(output_html).resolve()

    if not input_markdown_path.exists():
        raise FileNotFoundError(f"Newsletter markdown not found: {input_markdown_path}")
    if output_html_path.exists() and not force_rebuild:
        print(f"[SKIP] HTML newsletter already exists: {output_html_path}")
        return False

    output_html_path.parent.mkdir(parents=True, exist_ok=True)
    newsletter_markdown = repair_mojibake(input_markdown_path.read_text(encoding="utf-8"))
    title = extract_title(newsletter_markdown)
    editor_note = extract_editor_note(newsletter_markdown)
    body_html = build_html_body(init_model(api_key=api_key, model_name=model_name, base_url=base_url), newsletter_markdown)
    final_html = wrap_html_document(title, editor_note, body_html)
    output_html_path.write_text(final_html, encoding="utf-8")
    print(f"[DONE] HTML newsletter saved to: {output_html_path}")
    return True


def main() -> None:
    args = parse_args()
    run_html_stage(
        input_markdown=args.input_markdown,
        output_html=args.output_html,
        force_rebuild=True,
    )


if __name__ == "__main__":
    main()
