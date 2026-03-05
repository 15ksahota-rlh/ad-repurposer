"""
Convert an AnalysisResult into a markdown creative brief.
"""

from datetime import date

from .analyser import AnalysisResult


_STAR_BAR_WIDTH = 20


def _star_bar(count: int, total: int) -> str:
    """Return a simple ASCII bar proportional to count/total."""
    if total == 0:
        return ""
    filled = round(_STAR_BAR_WIDTH * count / total)
    return "█" * filled + "░" * (_STAR_BAR_WIDTH - filled)


def _quote_block(quotes: list[str]) -> str:
    return "\n".join(f'> "{q}"' for q in quotes)


def generate_brief(
    result: AnalysisResult,
    product_url: str,
    review_count: int,
    output_path: str = "creative_brief.md",
) -> str:
    """
    Render a markdown creative brief from an AnalysisResult and write it to disk.

    Returns the markdown string.
    """
    today = date.today().strftime("%d %B %Y")
    total_reviews = sum(result.star_distribution.values())

    # ── Header ──────────────────────────────────────────────────────────────
    lines: list[str] = [
        "# Competitor Review Mining — Creative Brief",
        "",
        f"**Generated:** {today}  ",
        f"**Source URL:** {product_url}  ",
        f"**Reviews analysed:** {review_count}  ",
        "",
        "---",
        "",
    ]

    # ── Executive Summary ────────────────────────────────────────────────────
    lines += [
        "## Executive Summary",
        "",
        result.overall_sentiment,
        "",
        "---",
        "",
    ]

    # ── Star Rating Distribution ─────────────────────────────────────────────
    lines += [
        "## Star Rating Distribution",
        "",
        "| Stars | Count | Distribution |",
        "|-------|-------|--------------|",
    ]
    for star in range(5, 0, -1):
        count = result.star_distribution.get(star, 0)
        bar = _star_bar(count, total_reviews)
        lines.append(f"| {'★' * star} | {count} | `{bar}` |")
    lines += ["", "---", ""]

    # ── Pain Points ──────────────────────────────────────────────────────────
    lines += [
        "## Pain Points",
        "",
        "_Recurring frustrations and unmet needs — your opportunity gaps._",
        "",
    ]
    for i, pain in enumerate(result.pain_points, 1):
        freq = pain.get("frequency", "—")
        lines += [
            f"### {i}. {pain.get('theme', 'Unknown theme')}",
            f"**Frequency:** ~{freq} reviews  ",
            "",
            pain.get("description", ""),
            "",
            "**Customer voice:**",
            _quote_block(pain.get("example_quotes", [])),
            "",
        ]
    lines += ["---", ""]

    # ── Praise Themes ────────────────────────────────────────────────────────
    lines += [
        "## Praise Themes",
        "",
        "_What customers love — validate, mirror, and amplify these in your ads._",
        "",
    ]
    for i, praise in enumerate(result.praise_themes, 1):
        freq = praise.get("frequency", "—")
        lines += [
            f"### {i}. {praise.get('theme', 'Unknown theme')}",
            f"**Frequency:** ~{freq} reviews  ",
            "",
            praise.get("description", ""),
            "",
            "**Customer voice:**",
            _quote_block(praise.get("example_quotes", [])),
            "",
        ]
    lines += ["---", ""]

    # ── Language Patterns ────────────────────────────────────────────────────
    lines += [
        "## Language Patterns",
        "",
        "_Verbatim vocabulary and emotional registers to borrow directly in copy._",
        "",
    ]
    for i, pattern in enumerate(result.language_patterns, 1):
        register = pattern.get("emotional_register", "")
        lines += [
            f"### {i}. {pattern.get('pattern', 'Unknown pattern')}",
            f"**Emotional register:** `{register}`  ",
            "",
            "**Examples from reviews:**",
        ]
        for ex in pattern.get("examples", []):
            lines.append(f'- "{ex}"')
        lines.append("")
    lines += ["---", ""]

    # ── Strategic Recommendations ────────────────────────────────────────────
    lines += [
        "## Strategic Recommendations for Ad Copy",
        "",
        "Based on the analysis above, prioritise the following angles:",
        "",
    ]

    # Derive quick recommendations from the data
    if result.pain_points:
        top_pain = result.pain_points[0]
        lines += [
            f"1. **Address the #1 pain point upfront** — _{top_pain.get('theme')}_  ",
            (
                "   Open hooks should immediately signal that your product solves "
                f"what competitors fail at: {top_pain.get('description', '')}"
            ),
            "",
        ]

    if result.praise_themes:
        top_praise = result.praise_themes[0]
        lines += [
            f"2. **Lead with the strongest benefit** — _{top_praise.get('theme')}_  ",
            (
                "   Mirror the exact language customers use when they're delighted: "
                + ", ".join(
                    f'"{q}"' for q in top_praise.get("example_quotes", [])[:2]
                )
            ),
            "",
        ]

    if result.language_patterns:
        aspirational = [
            p
            for p in result.language_patterns
            if p.get("emotional_register") == "aspirational"
        ]
        if aspirational:
            lines += [
                "3. **Use aspirational framing** — customers are buying an outcome, "
                "not a product.  ",
                "   Lift phrases like: "
                + ", ".join(
                    f'"{ex}"'
                    for ex in aspirational[0].get("examples", [])[:2]
                ),
                "",
            ]

    lines += [
        "4. **Social proof integration** — Verified purchase counts and helpful-vote "
        "leaders signal trustworthiness; reflect this credibility in ad testimonials.",
        "",
        "5. **A/B test angles:**",
        "   - Pain-led hook vs. benefit-led hook",
        "   - Transformation story vs. feature-focused",
        "   - Question opener vs. statement opener",
        "",
        "---",
        "",
        "_Brief auto-generated by the competitor review mining pipeline._",
    ]

    markdown = "\n".join(lines)

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(markdown)

    return markdown
