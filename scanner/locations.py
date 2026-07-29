"""
US-location screening from structured location text.

Fast pattern matching decides the clear cases. Only genuinely ambiguous
city-only strings are handed to the LLM, because inference is thousands of
times more expensive than a regex and most locations are unambiguous.
"""

from __future__ import annotations

import re

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT",
    "delaware": "DE", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI",
    "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND",
    "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC", "puerto rico": "PR",
}

STATE_ABBREVIATIONS = set(US_STATES.values())

US_MARKERS = [
    "united states", "usa", "u.s.a", "u.s.", "us-remote", "remote us",
    "remote - us", "remote (us)", "us remote", "nationwide",
]

# Unambiguous US metros. A bare "Springfield" is not here on purpose.
US_CITIES = {
    "new york", "nyc", "brooklyn", "manhattan", "san francisco", "sf",
    "bay area", "silicon valley", "palo alto", "mountain view", "sunnyvale",
    "santa clara", "san jose", "oakland", "berkeley", "los angeles", "la",
    "san diego", "seattle", "bellevue", "redmond", "portland", "denver",
    "boulder", "austin", "dallas", "houston", "san antonio", "chicago",
    "boston", "cambridge", "atlanta", "miami", "orlando", "tampa",
    "philadelphia", "pittsburgh", "detroit", "minneapolis", "st. louis",
    "kansas city", "nashville", "charlotte", "raleigh", "durham",
    "washington dc", "arlington", "baltimore", "phoenix", "scottsdale",
    "tempe", "las vegas", "salt lake city", "columbus", "cleveland",
    "cincinnati", "indianapolis", "milwaukee", "sacramento", "irvine",
    "san mateo", "menlo park", "cupertino", "boca raton", "fort worth",
}

NON_US_MARKERS = [
    "canada", "toronto", "vancouver", "montreal", "ottawa", "calgary",
    "united kingdom", "uk", "london", "manchester", "edinburgh", "dublin",
    "ireland", "germany", "berlin", "munich", "hamburg", "france", "paris",
    "spain", "madrid", "barcelona", "portugal", "lisbon", "porto",
    "netherlands", "amsterdam", "belgium", "brussels", "switzerland",
    "zurich", "geneva", "austria", "vienna", "sweden", "stockholm",
    "norway", "oslo", "denmark", "copenhagen", "finland", "helsinki",
    "poland", "warsaw", "krakow", "czech", "prague", "romania",
    "bucharest", "hungary", "budapest", "greece", "athens", "italy",
    "rome", "milan", "india", "bangalore", "bengaluru", "hyderabad",
    "mumbai", "delhi", "gurgaon", "gurugram", "pune", "chennai", "noida",
    "china", "beijing", "shanghai", "shenzhen", "hong kong", "taiwan",
    "taipei", "japan", "tokyo", "osaka", "korea", "seoul", "singapore",
    "malaysia", "kuala lumpur", "indonesia", "jakarta", "thailand",
    "bangkok", "vietnam", "hanoi", "philippines", "manila", "australia",
    "sydney", "melbourne", "brisbane", "new zealand", "auckland",
    "brazil", "sao paulo", "mexico", "mexico city", "guadalajara",
    "argentina", "buenos aires", "chile", "santiago", "colombia",
    "bogota", "israel", "tel aviv", "uae", "dubai", "abu dhabi",
    "saudi", "riyadh", "egypt", "cairo", "south africa", "cape town",
    "nigeria", "lagos", "kenya", "nairobi", "turkey", "istanbul",
    "ukraine", "kyiv", "emea", "apac", "latam",
]

_ZIP = re.compile(r"\b\d{5}(?:-\d{4})?\b")
_STATE_ABBR = re.compile(
    r"(?<![A-Za-z])(" + "|".join(sorted(STATE_ABBREVIATIONS)) + r")(?![A-Za-z])"
)

# A bare "US" / "U.S." token, which the phrase markers miss in strings like
# "Remote (US or Canada)".
_US_TOKEN = re.compile(r"(?<!\w)u\.?s\.?a?(?!\w)", re.IGNORECASE)


def _normalize(location: str | None) -> str:
    return re.sub(r"\s+", " ", str(location or "").strip().lower())


def screen_location(location: str | None) -> str:
    """
    Return "US", "NON_US", or "AMBIGUOUS".

    AMBIGUOUS is the only answer that should ever reach the LLM.
    """

    text = _normalize(location)

    if not text:
        return "AMBIGUOUS"

    has_non_us = any(
        re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", text)
        for marker in NON_US_MARKERS
    )

    has_us = any(marker in text for marker in US_MARKERS) or bool(
        _US_TOKEN.search(text)
    )

    if has_us and not has_non_us:
        return "US"

    # A full state name, a two-letter state code, or a ZIP settles it.
    if not has_non_us:
        for state in US_STATES:
            if re.search(rf"(?<!\w){re.escape(state)}(?!\w)", text):
                return "US"

        if _STATE_ABBR.search(str(location or "")):
            return "US"

        if _ZIP.search(text):
            return "US"

        for city in US_CITIES:
            if re.search(rf"(?<!\w){re.escape(city)}(?!\w)", text):
                return "US"

    if has_non_us and has_us:
        # Multi-region posting that includes the US. Good enough.
        return "US"

    if has_non_us:
        return "NON_US"

    # Bare "Remote" with nothing else, or a city we cannot place.
    return "AMBIGUOUS"


def is_us_location(location: str | None) -> bool:
    return screen_location(location) == "US"


def needs_llm_screening(location: str | None) -> bool:
    return screen_location(location) == "AMBIGUOUS"
