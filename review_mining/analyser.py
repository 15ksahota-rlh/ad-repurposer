"""
Analyse scraped reviews with the Anthropic API.

Extracts:
  - Pain points  (recurring frustrations, unmet needs)
  - Praise themes (what customers love and why)
  - Language patterns (verbatim phrases, vocabulary, emotional hooks)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import anthropic

from .scraper import Review

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

# Maximum characters sent per batch to stay well within token limits.
_BATCH_CHAR_LIMIT = 60_000


@dataclass
class AnalysisResult:
    pain_points: list[dict]          # [{theme, description, example_quotes}]
    praise_themes: list[dict]        # [{theme, description, example_quotes}]
    language_patterns: list[dict]    # [{pattern, examples, emotional_register}]
    star_distribution: dict          # {1: n, 2: n, …, 5: n}
    overall_sentiment: str           # short prose summary
    raw_json: dict = field(default_factory=dict)


def _format_reviews_for_prompt(reviews: list[Review]) -> str:
    """Serialise reviews into a compact, numbered text block for the prompt."""
    lines: list[str] = []
    for i, r in enumerate(reviews, 1):
        verified_tag = "[Verified]" if r.verified else "[Unverified]"
        helpful_tag = f"[{r.helpful_votes} helpful votes]" if r.helpful_votes else ""
        lines.append(
            f"--- Review {i} | {r.rating}★ {verified_tag} {helpful_tag} ---\n"
            f"Title: {r.title}\n"
            f"{r.body}"
        )
    return "\n\n".join(lines)


def _star_distribution(reviews: list[Review]) -> dict[int, int]:
    dist: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in reviews:
        star = int(round(r.rating))
        if star in dist:
            dist[star] += 1
    return dist


_SYSTEM_PROMPT = """\
You are an expert consumer-insights analyst and direct-response copywriter. \
Your job is to mine Amazon reviews for strategic ad-copy intelligence. \
You must respond with valid JSON only — no markdown, no prose outside the JSON object."""

_USER_PROMPT_TEMPLATE = """\
Below are {n} Amazon customer reviews for a competitor product. \
Analyse them thoroughly and return a single JSON object with exactly \
these keys:

"pain_points": array of objects, each with:
  - "theme": concise label (≤6 words)
  - "description": 1-2 sentence explanation of the recurring frustration
  - "frequency": rough count of reviews mentioning this
  - "example_quotes": array of 2-3 verbatim short phrases from actual reviews

"praise_themes": array of objects, each with:
  - "theme": concise label (≤6 words)
  - "description": 1-2 sentence explanation of what customers love
  - "frequency": rough count of reviews mentioning this
  - "example_quotes": array of 2-3 verbatim short phrases from actual reviews

"language_patterns": array of objects, each with:
  - "pattern": name of the pattern (e.g. "before/after transformation", "social proof phrasing")
  - "examples": array of 2-4 verbatim phrases that illustrate it
  - "emotional_register": one of ["aspirational", "relief", "trust", "urgency", "delight", "frustration"]

"overall_sentiment": a single paragraph (3-5 sentences) summarising the \
dominant buyer psychology, unmet desires, and emotional triggers visible \
in these reviews. Focus on what an ad copywriter needs to know.

Return only valid JSON. No extra keys, no markdown fences.

REVIEWS:
{reviews_text}
"""


def _call_claude(client: anthropic.Anthropic, reviews_text: str, n: int) -> dict:
    prompt = _USER_PROMPT_TEMPLATE.format(n=n, reviews_text=reviews_text)
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = message.content[0].text.strip()

    # Strip accidental markdown fences Claude might still produce
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse error. Raw response:\n%s", raw_text)
        raise ValueError("Claude returned invalid JSON.") from exc


def _merge_batches(batches: list[dict]) -> dict:
    """Merge multiple batch analysis dicts into a single consolidated result."""
    if len(batches) == 1:
        return batches[0]

    merged: dict = {
        "pain_points": [],
        "praise_themes": [],
        "language_patterns": [],
        "overall_sentiment": "",
    }

    seen_pain: set[str] = set()
    seen_praise: set[str] = set()
    seen_patterns: set[str] = set()
    sentiments: list[str] = []

    for batch in batches:
        for item in batch.get("pain_points", []):
            key = item.get("theme", "").lower()
            if key not in seen_pain:
                seen_pain.add(key)
                merged["pain_points"].append(item)

        for item in batch.get("praise_themes", []):
            key = item.get("theme", "").lower()
            if key not in seen_praise:
                seen_praise.add(key)
                merged["praise_themes"].append(item)

        for item in batch.get("language_patterns", []):
            key = item.get("pattern", "").lower()
            if key not in seen_patterns:
                seen_patterns.add(key)
                merged["language_patterns"].append(item)

        if batch.get("overall_sentiment"):
            sentiments.append(batch["overall_sentiment"])

    merged["overall_sentiment"] = " ".join(sentiments)
    return merged


def analyse_reviews(
    reviews: list[Review],
    api_key: Optional[str] = None,
) -> AnalysisResult:
    """
    Send reviews to Claude and return a structured AnalysisResult.

    Parameters
    ----------
    reviews:
        List of Review objects from the scraper.
    api_key:
        Anthropic API key. Falls back to the ANTHROPIC_API_KEY env var.
    """
    if not reviews:
        raise ValueError("No reviews to analyse.")

    resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not resolved_key:
        raise EnvironmentError(
            "Anthropic API key not found. "
            "Set ANTHROPIC_API_KEY or pass api_key= explicitly."
        )

    client = anthropic.Anthropic(api_key=resolved_key)
    star_dist = _star_distribution(reviews)

    # Split into batches if the text is very long
    batches: list[dict] = []
    current_batch: list[Review] = []
    current_chars = 0

    for review in reviews:
        review_chars = len(review.body) + len(review.title)
        if current_chars + review_chars > _BATCH_CHAR_LIMIT and current_batch:
            logger.info("Sending batch of %d reviews to Claude.", len(current_batch))
            text = _format_reviews_for_prompt(current_batch)
            batches.append(_call_claude(client, text, len(current_batch)))
            current_batch = []
            current_chars = 0
        current_batch.append(review)
        current_chars += review_chars

    if current_batch:
        logger.info("Sending final batch of %d reviews to Claude.", len(current_batch))
        text = _format_reviews_for_prompt(current_batch)
        batches.append(_call_claude(client, text, len(current_batch)))

    merged = _merge_batches(batches)

    return AnalysisResult(
        pain_points=merged.get("pain_points", []),
        praise_themes=merged.get("praise_themes", []),
        language_patterns=merged.get("language_patterns", []),
        star_distribution=star_dist,
        overall_sentiment=merged.get("overall_sentiment", ""),
        raw_json=merged,
    )

