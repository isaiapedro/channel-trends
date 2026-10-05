import json
import re
import sys
from itertools import combinations

import httpx
import numpy as np
from googleapiclient.discovery import build

from config import ConfigurationError, get_settings, output_path
from scrape_google_trends import demand_velocity

CHANNEL_ID_PATTERN = re.compile(r"^UC[\w-]{22}$")

ANGLE_PROMPT = """Rate the following YouTube video title and description on three cognitive triggers, each on a 1-5 scale (1=absent, 5=very strong).

Title: {title}
Description: {description}

Respond with ONLY a JSON object, no other text:
{{"curiosity_gap": <1-5>, "relatability": <1-5>, "stakes_tension": <1-5>}}
"""


def get_first_10_videos(youtube, channel_id):
    channel = youtube.channels().list(part="contentDetails,statistics", id=channel_id).execute()
    if not channel.get("items"):
        raise ValueError("channel was not found or its metadata is unavailable")
    item = channel["items"][0]
    uploads_playlist = item["contentDetails"]["relatedPlaylists"]["uploads"]
    subscriber_count = int(item["statistics"]["subscriberCount"])

    video_ids = []
    page_token = None
    while len(video_ids) < 200:
        resp = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        video_ids.extend(
            (i["contentDetails"]["videoId"], i["contentDetails"].get("videoPublishedAt", ""))
            for i in resp["items"]
        )
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    video_ids.sort(key=lambda v: v[1])
    first_10_ids = [v[0] for v in video_ids[:10]]

    if not first_10_ids:
        raise ValueError("channel has no public videos")

    videos = youtube.videos().list(
        part="snippet,statistics", id=",".join(first_10_ids)
    ).execute()

    videos_sorted = sorted(
        videos["items"], key=lambda v: v["snippet"]["publishedAt"]
    )
    return videos_sorted, subscriber_count


def embed(text, settings):
    resp = httpx.post(
        f"{settings.ollama_host}/api/embed",
        json={"model": "nomic-embed-text", "input": text},
        timeout=settings.http_timeout_seconds,
    )
    resp.raise_for_status()
    return np.array(resp.json()["embeddings"][0])


def cosine_similarity(a, b):
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    if denominator == 0:
        raise ValueError("Ollama returned a zero-norm embedding")
    return float(np.dot(a, b) / denominator)


def mean_pairwise_cosine_similarity(embeddings):
    if len(embeddings) < 2:
        raise ValueError("at least two public videos are required for momentum analysis")
    pairs = list(combinations(range(len(embeddings)), 2))
    sims = [cosine_similarity(embeddings[i], embeddings[j]) for i, j in pairs]
    return float(np.mean(sims))


ANGLE_SCHEMA = {
    "type": "object",
    "properties": {
        "curiosity_gap": {"type": "integer"},
        "relatability": {"type": "integer"},
        "stakes_tension": {"type": "integer"},
    },
    "required": ["curiosity_gap", "relatability", "stakes_tension"],
}


def angle_leverage_score(title, description, settings):
    resp = httpx.post(
        f"{settings.ollama_host}/api/generate",
        json={
            "model": "llama3.2",
            "prompt": ANGLE_PROMPT.format(title=title, description=description[:500]),
            "stream": False,
            "format": ANGLE_SCHEMA,
        },
        timeout=settings.http_timeout_seconds,
    )
    resp.raise_for_status()
    scores = json.loads(resp.json()["response"])
    if set(scores) != set(ANGLE_SCHEMA["required"]) or any(
        not isinstance(value, int) or not 1 <= value <= 5 for value in scores.values()
    ):
        raise ValueError("Ollama returned invalid angle-leverage scores")
    return scores, np.mean([scores["curiosity_gap"], scores["relatability"], scores["stakes_tension"]])


def analyze_channel(channel_id, niche_keywords):
    if not CHANNEL_ID_PATTERN.fullmatch(channel_id):
        raise ValueError("channel_id must be a canonical YouTube channel ID beginning with UC")
    settings = get_settings()
    youtube = build("youtube", "v3", developerKey=settings.youtube_api_key)
    videos, subscriber_count = get_first_10_videos(youtube, channel_id)
    if len(videos) < 10:
        print(f"Warning: only {len(videos)} videos found for channel {channel_id}", file=sys.stderr)

    texts = [f'{v["snippet"]["title"]} {v["snippet"]["description"]}' for v in videos]
    embeddings = [embed(t, settings) for t in texts]
    mean_cosine_similarity = mean_pairwise_cosine_similarity(embeddings)

    view_counts = [int(v["statistics"].get("viewCount", 0)) for v in videos]
    avg_view_count = float(np.mean(view_counts))
    supply_deficit_ratio = avg_view_count / subscriber_count if subscriber_count else 0.0

    angle_results = [
        angle_leverage_score(v["snippet"]["title"], v["snippet"]["description"], settings)
        for v in videos
    ]
    angle_leverage = float(np.mean([r[1] for r in angle_results]))

    velocity = demand_velocity(niche_keywords)

    blueprint_viability_index = mean_cosine_similarity * supply_deficit_ratio * velocity

    return {
        "channel_id": channel_id,
        "videos": [
            {"id": v["id"], "title": v["snippet"]["title"], "publishedAt": v["snippet"]["publishedAt"]}
            for v in videos
        ],
        "mean_cosine_similarity": mean_cosine_similarity,
        "avg_view_count": avg_view_count,
        "subscriber_count": subscriber_count,
        "supply_deficit_ratio": supply_deficit_ratio,
        "demand_velocity": velocity,
        "angle_leverage": angle_leverage,
        "blueprint_viability_index": blueprint_viability_index,
    }


def write_report(result):
    path = output_path(f'channel_momentum_{result["channel_id"]}.md')
    lines = [
        "---",
        "tags: [trends, channel-momentum]",
        "---",
        f'# Channel Momentum Score: {result["channel_id"]}',
        "",
        f'- **Niche Consistency (mean cosine similarity):** {result["mean_cosine_similarity"]:.3f}',
        f'- **Supply Deficit Ratio:** {result["supply_deficit_ratio"]:.4f} '
        f'(avg views {result["avg_view_count"]:.0f} / subscribers {result["subscriber_count"]})',
        f'- **Demand Velocity:** {result["demand_velocity"]:.2f}',
        f'- **Blueprint Viability Index:** {result["blueprint_viability_index"]:.4f}',
        f'- **Angle Leverage (diagnostic, not in index):** {result["angle_leverage"]:.2f} / 5',
        "",
        "## Source videos (first 10 published)",
    ]
    for v in result["videos"]:
        lines.append(f'- `{v["id"]}` — {v["title"]} ({v["publishedAt"]})')

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Report written to {path}")


if __name__ == "__main__":
    if sys.argv[1:] == ["--validate-config"]:
        try:
            get_settings()
        except ConfigurationError as exc:
            print(f"Configuration invalid: {exc}", file=sys.stderr)
            sys.exit(2)
        print("Configuration is valid (credentials and models were not contacted).")
        sys.exit(0)
    if len(sys.argv) < 2:
        print("Usage: python channel_momentum.py <channel_id> [niche_keyword ...]")
        sys.exit(1)

    channel_id = sys.argv[1]
    niche_keywords = sys.argv[2:] if len(sys.argv) > 2 else ["devlog"]

    result = analyze_channel(channel_id, niche_keywords)
    write_report(result)
