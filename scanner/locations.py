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
    # Countries and territories. Deliberately near-exhaustive: a partial list
    # is what let Pakistan, Moldova, Honduras and Suriname through as
    # "ambiguous" and into US-only results.
    "afghanistan", "albania", "algeria", "andorra", "angola", "antigua",
    "argentina", "armenia", "aruba", "australia", "austria", "azerbaijan",
    "bahamas", "bahrain", "bangladesh", "barbados", "belarus", "belgium",
    "belize", "benin", "bermuda", "bhutan", "bolivia", "bosnia",
    "bosnia and herzegovina", "botswana", "brazil", "brunei", "bulgaria",
    "burkina faso", "burundi", "cambodia", "cameroon", "canada",
    "cape verde", "cayman islands", "chad", "chile", "china", "colombia",
    "comoros", "congo", "costa rica", "croatia", "cuba", "curacao",
    "cyprus", "czech republic", "czechia", "czech", "denmark", "djibouti",
    "dominica", "dominican republic", "ecuador", "egypt", "el salvador",
    "estonia", "eswatini", "ethiopia", "fiji", "finland", "france",
    "gabon", "gambia", "germany", "ghana", "gibraltar", "greece",
    "greenland", "grenada", "guatemala", "guernsey", "guinea", "guyana",
    "haiti", "honduras", "hong kong", "hungary", "iceland", "india",
    "indonesia", "iran", "iraq", "ireland", "isle of man", "israel",
    "italy", "ivory coast", "jamaica", "japan", "jersey", "jordan",
    "kazakhstan", "kenya", "kosovo", "kuwait", "kyrgyzstan", "laos",
    "latvia", "lesotho", "liberia", "libya", "liechtenstein", "lithuania",
    "luxembourg", "macau", "madagascar", "malawi", "malaysia", "maldives",
    "mali", "malta", "mauritania", "mauritius", "moldova", "monaco",
    "mongolia", "montenegro", "morocco", "mozambique", "myanmar",
    "namibia", "nepal", "netherlands", "new zealand", "nicaragua",
    "niger", "nigeria", "north macedonia", "macedonia", "norway", "oman",
    "pakistan", "palestine", "panama", "papua new guinea", "paraguay",
    "peru", "philippines", "poland", "portugal", "qatar", "romania",
    "russia", "rwanda", "san marino", "saudi arabia", "saudi", "senegal",
    "serbia", "seychelles", "sierra leone", "singapore", "slovakia",
    "slovenia", "somalia", "south africa", "south korea", "korea",
    "north korea", "south sudan", "spain", "sri lanka", "sudan",
    "suriname", "sweden", "switzerland", "syria", "taiwan", "tajikistan",
    "tanzania", "thailand", "togo", "trinidad", "tunisia", "turkey",
    "türkiye", "turkmenistan", "uganda", "ukraine", "united kingdom",
    "uk", "u.k.", "great britain", "england", "scotland", "wales",
    "northern ireland", "united arab emirates", "uae", "uruguay",
    "uzbekistan", "venezuela", "vietnam", "yemen", "zambia", "zimbabwe",
    # Major non-US metros that appear without a country.
    "toronto", "vancouver", "montreal", "ottawa", "calgary", "edmonton",
    "winnipeg", "london", "manchester", "birmingham uk", "edinburgh",
    "glasgow", "bristol", "leeds", "dublin", "belfast", "berlin",
    "munich", "hamburg", "frankfurt", "cologne", "stuttgart", "paris",
    "lyon", "marseille", "toulouse", "madrid", "barcelona", "valencia",
    "seville", "lisbon", "porto", "amsterdam", "rotterdam", "utrecht",
    "brussels", "antwerp", "zurich", "geneva", "basel", "bern", "vienna",
    "stockholm", "gothenburg", "oslo", "copenhagen", "helsinki",
    "reykjavik", "warsaw", "krakow", "wroclaw", "gdansk", "poznan",
    "prague", "brno", "bratislava", "budapest", "bucharest", "cluj",
    "sofia", "belgrade", "zagreb", "ljubljana", "sarajevo", "skopje",
    "tirana", "athens", "thessaloniki", "rome", "milan", "turin",
    "naples", "florence", "bologna", "kyiv", "kiev", "lviv", "odesa",
    "minsk", "moscow", "st petersburg", "istanbul", "ankara", "izmir",
    "tel aviv", "jerusalem", "haifa", "dubai", "abu dhabi", "sharjah",
    "doha", "riyadh", "jeddah", "kuwait city", "manama", "muscat",
    "amman", "beirut", "cairo", "alexandria", "casablanca", "rabat",
    "tunis", "algiers", "lagos", "abuja", "accra", "nairobi",
    "kampala", "dar es salaam", "addis ababa", "johannesburg",
    "cape town", "durban", "pretoria", "bangalore", "bengaluru",
    "hyderabad", "mumbai", "new delhi", "delhi", "gurgaon", "gurugram",
    "pune", "chennai", "kolkata", "noida", "ahmedabad", "jaipur",
    "kochi", "coimbatore", "indore", "karachi", "lahore", "islamabad",
    "dhaka", "colombo", "kathmandu", "beijing", "shanghai", "shenzhen",
    "guangzhou", "hangzhou", "chengdu", "taipei", "tokyo", "osaka",
    "kyoto", "yokohama", "seoul", "busan", "kuala lumpur", "jakarta",
    "bandung", "bangkok", "chiang mai", "hanoi", "ho chi minh",
    "saigon", "da nang", "manila", "cebu", "makati", "sydney",
    "melbourne", "brisbane", "perth", "adelaide", "canberra",
    "auckland", "wellington", "christchurch", "sao paulo", "são paulo",
    "rio de janeiro", "brasilia", "belo horizonte", "porto alegre",
    "curitiba", "recife", "mexico city", "guadalajara", "monterrey",
    "buenos aires", "cordoba", "santiago", "bogota", "bogotá",
    "medellin", "medellín", "lima", "quito", "guayaquil", "caracas",
    "montevideo", "asuncion", "la paz", "san jose costa rica",
    "panama city", "tegucigalpa", "managua", "san salvador",
    "guatemala city", "santo domingo", "havana", "kingston",
    # Regions.
    "emea", "apac", "latam", "anz", "mena", "benelux", "nordics",
    "europe", "european union", "eurozone", "asia", "asia pacific",
    "southeast asia", "south asia", "east asia", "middle east",
    "africa", "south america", "latin america", "central america",
    "caribbean", "oceania",
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

    # Order is the whole design here. Strong US signals are checked before
    # country names so that US places sharing a country's name still read as
    # US — Georgia the state, New Mexico, Panama City FL. Weaker US signals
    # (a bare two-letter code, a city name) are checked *after* the country
    # list, so "Toronto, CA" is Canada rather than California.

    # 1. An explicit country reference. Also settles multi-region postings
    #    like "Remote (US or Canada)" in favour of the US.
    if any(marker in text for marker in US_MARKERS) or _US_TOKEN.search(text):
        return "US"

    # 2. A spelled-out state name.
    for state in US_STATES:
        if re.search(rf"(?<!\w){re.escape(state)}(?!\w)", text):
            return "US"

    # 3. A ZIP code.
    if _ZIP.search(text):
        return "US"

    # 4. A two-letter state code. This has to beat the country list, because
    #    a great many US cities share a foreign city's name — Naples FL,
    #    Athens GA, Vienna VA, Rome NY, Manchester NH, Panama City FL — and
    #    those postings are nearly always written "City, XX". Reading them as
    #    foreign would silently discard real US jobs, which is the one
    #    failure this screen must not make.
    #
    #    The cost is "Toronto, CA" reading as California. Canadian postings
    #    almost always carry a province code or the word Canada, both of
    #    which are caught below, so the exchange is worth it.
    if _STATE_ABBR.search(str(location or "")):
        return "US"

    # 5. A country or region we can place outside the US.
    if any(
        re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", text)
        for marker in NON_US_MARKERS
    ):
        return "NON_US"

    # 6. A US metro we recognise by name alone.
    for city in US_CITIES:
        if re.search(rf"(?<!\w){re.escape(city)}(?!\w)", text):
            return "US"

    # Bare "Remote", "Worldwide", or a city we cannot place. These genuinely
    # may include the US, so they go to the model rather than being guessed.
    return "AMBIGUOUS"


def is_us_location(location: str | None) -> bool:
    return screen_location(location) == "US"


def needs_llm_screening(location: str | None) -> bool:
    return screen_location(location) == "AMBIGUOUS"


def job_has_confirmed_us_location(job: dict) -> bool:
    """
    Return True only when structured data or completed analysis confirms US.

    An unresolved ambiguous location must not leak into a US-only result set
    just because the full-analysis budget was exhausted.
    """

    verdict = str(job.get("location_verdict") or "").upper()

    if not verdict:
        verdict = screen_location(job.get("location"))

    if verdict == "US":
        return True

    if verdict == "NON_US":
        return False

    analysis = job.get("analysis") or {}

    return str(analysis.get("us_location_eligible") or "").upper() == "YES"
