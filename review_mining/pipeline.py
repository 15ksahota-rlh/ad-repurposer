"""
Main entry point for the competitor review mining pipeline.

Usage
-----
    python -m review_mining.pipeline \
        --url "https://www.amazon.co.uk/dp/B0GBW8SBZP/..." \
        --max-reviews 50 \
        --output creative_brief.md

Environment variables
---------------------
    ANTHROPIC_API_KEY  — required for the analysis step.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from .scraper import scrape_reviews
from .analyser import analyse_reviews
from .brief_writer import generate_brief

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mine competitor Amazon reviews and generate an ad creative brief.",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Amazon product URL (must contain the product ASIN).",
    )
    parser.add_argument(
        "--max-reviews",
        type=int,
        default=50,
        metavar="N",
        help="Maximum number of reviews to scrape (default: 50).",
    )
    parser.add_argument(
        "--output",
        default="creative_brief.md",
        help="Output path for the markdown creative brief (default: creative_brief.md).",
    )
    parser.add_argument(
        "--save-reviews",
        metavar="PATH",
        help="Optional path to save raw scraped reviews as JSON.",
    )
    parser.add_argument(
        "--load-reviews",
        metavar="PATH",
        help=(
            "Skip scraping and load reviews from a previously saved JSON file. "
            "Useful for re-running the analysis without re-scraping."
        ),
    )
    return parser.parse_args(argv)


def _load_reviews_from_json(path: str):
    from .scraper import Review
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return [Review(**r) for r in data]


def _save_reviews_to_json(reviews, path: str) -> None:
    from dataclasses import asdict
    with open(path, "w", encoding="utf-8") as fh:
        json.dump([asdict(r) for r in reviews], fh, indent=2, ensure_ascii=False)
    logger.info("Saved %d reviews to %s", len(reviews), path)


def run(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    # ── Step 1: Scrape (or load from cache) ──────────────────────────────────
    if args.load_reviews:
        logger.info("Loading reviews from %s", args.load_reviews)
        reviews = _load_reviews_from_json(args.load_reviews)
        logger.info("Loaded %d reviews.", len(reviews))
    else:
        logger.info("Scraping up to %d reviews from: %s", args.max_reviews, args.url)
        reviews = scrape_reviews(args.url, max_reviews=args.max_reviews)

        if not reviews:
            logger.error(
                "No reviews were scraped. "
                "Amazon may be blocking the request. "
                "Try again later or supply a reviews JSON via --load-reviews."
            )
            sys.exit(1)

        logger.info("Scraped %d reviews.", len(reviews))

        if args.save_reviews:
            _save_reviews_to_json(reviews, args.save_reviews)

    # ── Step 2: Analyse with Claude ───────────────────────────────────────────
    logger.info("Sending reviews to Claude for analysis…")
    result = analyse_reviews(reviews)
    logger.info(
        "Analysis complete — %d pain points, %d praise themes, %d language patterns.",
        len(result.pain_points),
        len(result.praise_themes),
        len(result.language_patterns),
    )

    # ── Step 3: Generate creative brief ──────────────────────────────────────
    output_path = args.output
    logger.info("Writing creative brief to %s…", output_path)
    generate_brief(
        result=result,
        product_url=args.url,
        review_count=len(reviews),
        output_path=output_path,
    )
    logger.info("Done. Creative brief saved to: %s", Path(output_path).resolve())


if __name__ == "__main__":
    run()
