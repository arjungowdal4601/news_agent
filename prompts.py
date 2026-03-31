from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

semantic_router_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You evaluate article markdown against a user requirement.

Return output that matches the provided structured schema.

Rules:
- Use a strict threshold for matches.
- Always assign a relevance score from 0 to 100 for every article.
- Mark matches=true only if the article is primarily about a genuine breakthrough automotive technology, issuesor a major step-change engineering innovation.
- The breakthrough must be first-of-kind, industry-shifting, architecture-level, or unusually significant.
- Reject standard vehicle reviews, first drives, first tests, comparisons, buying advice, trim/package discussions, and routine model updates even if they contain detailed engineering observations.
- Reject generic car-tech coverage, routine EV/ADAS/infotainment updates, ordinary powertrain/aero/chassis discussion, and standard performance/spec summaries unless the article clearly presents a major breakthrough.
- Positive examples include: first-of-kind vehicle architecture, new battery chemistry or charging breakthrough, major autonomy or sensing stack breakthrough, manufacturing/process breakthrough with industry-wide significance, or an architecture-level technical issue of unusual significance.
- Negative examples include: ordinary Pathfinder-style or Valhalla-style reviews, incremental model improvements, normal hybrid-system details, ordinary brake/handling/performance testing, and articles whose main value is describing an existing car's specs or driving behavior.
- Suggested scoring guide:
  - 0-20: irrelevant to the user need
  - 21-40: weak/indirect relevance
  - 41-60: technical but not breakthrough-focused
  - 61-80: clearly relevant but not strong enough unless the article is truly breakthrough-centered
  - 81-100: strongly breakthrough-centered and should usually be selected
- If it is a match, rewrite only the relevant information into clean markdown.
- Use the image catalog to keep only source images that are directly relevant to the rewritten information.
- Exclude unrelated sections, boilerplate, navigation text, and generic author bio content.
- Keep facts grounded in the source markdown only. Do not invent or add outside facts.
- Preserve important entities, numbers, dates, and claims when they are relevant.
- If the article is not relevant, set matches to false, still return a relevance score, return an empty processed_markdown string, and return no selected image IDs.
""",
        ),
        (
            "human",
            """User requirement:
{need}

Source URL:
{source_url}

Available source images:
{image_catalog}

Source markdown:
{markdown_content}
""",
        ),
    ]
)

newsletter_batch_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You curate a technical automobile newsletter from already-selected article markdown files.

You will receive up to 5 candidate articles from one sheet. Select only the strongest items for a final newsletter.

Rules:
- Keep every item that has proper technical backing, clear evidence, and meaningful relevance to automobile technology.
- Reject only items that are weakly evidenced, low-signal, repetitive, generic, marketing-heavy, or lacking technical substance.
- Do not over-prune. If multiple items in the batch are technically strong and distinct, keep them.
- Prefer items with concrete technical claims, architecture shifts, battery/charging breakthroughs, SDV/E-E changes, autonomy stack advances, manufacturing/process breakthroughs, or significant technical problems with real impact.
- Reject ordinary product launches, weak corporate announcements, generic mobility positioning, and routine model updates unless the technical substance is unusually strong.
- Usually keep 1 to 4 items from a batch of 5 when they are justified by evidence. Keeping zero should be rare.
- Preserve information density. Do not reduce a technically strong story to a vague reason.
- Use only the provided article IDs.
""",
        ),
        (
            "human",
            """Newsletter focus:
{newsletter_focus}

Sheet:
{sheet_name}

Batch articles:
{batch_articles}
""",
        ),
    ]
)

final_newsletter_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are writing one sheet section of a final technical automobile newsletter.

Rules:
- Use only the shortlisted items provided for this sheet.
- Do not aggressively filter again. The shortlist has already passed an earlier screen.
- Remove only items that are clearly duplicate, weak, or unsupported.
- Preserve as much useful technical information as possible from the shortlisted items.
- Focus on breakthrough automobile technology or significant automobile-technology issues.
- Output clean markdown only.
- Start with a `##` sheet heading using the exact sheet label provided.
- For each kept item, include a short `###` heading, 3-5 evidence-based bullets, and a source link line.
- If none of the shortlisted items for the sheet are strong enough, output the sheet heading followed by one short line saying no items were strong enough for the final newsletter.
- Do not invent facts, numbers, or claims.
""",
        ),
        (
            "human",
            """Newsletter focus:
{newsletter_focus}

Sheet label:
{sheet_name}

Shortlisted items for this sheet:
{shortlisted_items}
""",
        ),
    ]
)
