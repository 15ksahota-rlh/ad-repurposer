"""
Amazon review scraper using BeautifulSoup.

Fetches the top reviews from an Amazon product page, handling pagination
to collect up to `max_reviews` reviews.
"""

import time
import random
import logging
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Rotate a small set of realistic User-Agent strings to reduce bot detection.
_USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.3 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
]


@dataclass
class Review:
    title: str
    rating: float          # 1–5 stars
    body: str
    verified: bool
    helpful_votes: int


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/webp,*/*;q=0.8"
            ),
            "Connection": "keep-alive",
            "DNT": "1",
        }
    )
    return session


def _reviews_url(asin: str, page: int = 1) -> str:
    """Return the Amazon.co.uk all-reviews URL for a given ASIN and page."""
    return (
        f"https://www.amazon.co.uk/product-reviews/{asin}"
        f"?ie=UTF8&reviewerType=all_reviews&pageNumber={page}"
        f"&sortBy=helpful"
    )


def _extract_asin(url: str) -> str:
    """Pull the ASIN out of a standard Amazon product or review URL."""
    for segment in url.split("/"):
        if segment.startswith("B0") and len(segment) == 10:
            return segment
        if segment == "dp" or segment == "product-reviews":
            continue
    # Fallback: look for /dp/<ASIN> pattern
    parts = url.split("/dp/")
    if len(parts) > 1:
        return parts[1].split("/")[0].split("?")[0]
    raise ValueError(f"Cannot extract ASIN from URL: {url}")


def _parse_reviews_from_page(soup: BeautifulSoup) -> list[Review]:
    """Parse all review cards present on a single reviews page."""
    reviews: list[Review] = []

    for card in soup.select("[data-hook='review']"):
        # --- Title ---
        title_el = card.select_one("[data-hook='review-title'] span:not([class])")
        title = title_el.get_text(strip=True) if title_el else ""

        # --- Star rating ---
        rating_el = card.select_one("[data-hook='review-star-rating'] span.a-icon-alt")
        rating = 0.0
        if rating_el:
            try:
                rating = float(rating_el.get_text(strip=True).split(" ")[0])
            except ValueError:
                pass

        # --- Body ---
        body_el = card.select_one("[data-hook='review-body'] span")
        body = body_el.get_text(strip=True) if body_el else ""

        # --- Verified purchase ---
        verified_el = card.select_one("[data-hook='avp-badge']")
        verified = verified_el is not None

        # --- Helpful votes ---
        helpful_el = card.select_one("[data-hook='helpful-vote-statement']")
        helpful_votes = 0
        if helpful_el:
            text = helpful_el.get_text(strip=True)
            digits = "".join(c for c in text if c.isdigit())
            helpful_votes = int(digits) if digits else 0

        if body:
            reviews.append(
                Review(
                    title=title,
                    rating=rating,
                    body=body,
                    verified=verified,
                    helpful_votes=helpful_votes,
                )
            )

    return reviews


def scrape_reviews(
    url: str,
    max_reviews: int = 50,
    delay_range: tuple[float, float] = (2.0, 4.5),
) -> list[Review]:
    """
    Scrape up to `max_reviews` reviews from an Amazon product URL.

    Parameters
    ----------
    url:
        Any Amazon product or review URL containing the product ASIN.
    max_reviews:
        Maximum number of reviews to collect (default 50).
    delay_range:
        Min/max seconds to wait between page requests to be polite.

    Returns
    -------
    A list of Review dataclass instances, ordered by Amazon's "most helpful"
    sort order.
    """
    asin = _extract_asin(url)
    logger.info("Extracted ASIN: %s", asin)

    session = _build_session()
    reviews: list[Review] = []
    page = 1

    while len(reviews) < max_reviews:
        session.headers["User-Agent"] = random.choice(_USER_AGENTS)
        page_url = _reviews_url(asin, page)
        logger.info("Fetching page %d: %s", page, page_url)

        try:
            response = session.get(page_url, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Request failed on page %d: %s", page, exc)
            break

        soup = BeautifulSoup(response.text, "lxml")
        page_reviews = _parse_reviews_from_page(soup)

        if not page_reviews:
            logger.info("No reviews found on page %d — stopping.", page)
            break

        reviews.extend(page_reviews)
        logger.info(
            "Collected %d reviews so far (page %d returned %d).",
            len(reviews),
            page,
            len(page_reviews),
        )

        # Check for a "next page" link before incrementing
        next_btn = soup.select_one("li.a-last a")
        if not next_btn:
            logger.info("No next-page link found — reached last page.")
            break

        page += 1
        time.sleep(random.uniform(*delay_range))

    trimmed = reviews[:max_reviews]
    logger.info("Returning %d reviews total.", len(trimmed))
    return trimmed
