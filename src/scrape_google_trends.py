from pytrends.request import TrendReq
from pytrends.exceptions import TooManyRequestsError
import sys
import time

from config import get_settings, output_path


def fetch_interest_over_time(keywords, timeframe="today 3-m", retries=None, backoff=None):
    if not keywords or any(not keyword.strip() for keyword in keywords):
        raise ValueError("provide at least one non-empty keyword")
    settings = get_settings(require_youtube_key=False)
    retries = settings.google_retries if retries is None else retries
    backoff = settings.google_backoff_seconds if backoff is None else backoff
    pytrends = TrendReq(hl="en-US", tz=360, requests_args={"timeout": settings.http_timeout_seconds})
    for attempt in range(retries):
        try:
            pytrends.build_payload(keywords, cat=0, timeframe=timeframe)
            df = pytrends.interest_over_time()
            if "isPartial" in df.columns:
                df = df.drop(columns=["isPartial"])
            return df
        except TooManyRequestsError:
            if attempt == retries - 1:
                raise
            wait = backoff * (attempt + 1)
            print(f"Rate limited by Google Trends, retrying in {wait}s...", file=sys.stderr)
            time.sleep(wait)


def demand_velocity(keywords, timeframe="today 3-m"):
    """Mean Google Trends interest (0-100) over the timeframe, across keywords."""
    df = fetch_interest_over_time(keywords, timeframe)
    if df.empty:
        return 0.0
    return float(df.mean(numeric_only=True).mean())


if __name__ == "__main__":
    keywords = sys.argv[1:] if len(sys.argv) > 1 else ["React", "Svelte", "HTMX"]
    df = fetch_interest_over_time(keywords)
    md_table = df.to_markdown()
    md_content = f"---\ntags: [trends, data]\n---\n# Trend Data: {', '.join(keywords)}\n\n{md_table}"

    out_path = output_path("tech_trends.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as file:
        file.write(md_content)
    print(f"Trends written to {out_path}")
