# PIOS Trends Service

Local CLI analysis of public Google Trends and YouTube metadata. It is not a
web service and it never consumes Personal-domain data.

## Setup

```bash
cd services/trends
python -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
# set YOUTUBE_API_KEY to an authorized YouTube Data API v3 key
venv/bin/python src/channel_momentum.py --validate-config
```

The default Ollama URL is loopback-only. Start the required local models before
running channel analysis: `nomic-embed-text` and `llama3.2`.

## Run

```bash
venv/bin/python src/scrape_google_trends.py "python"
venv/bin/python src/channel_momentum.py UCxxxxxxxxxxxxxxxxxxxxxx "python"
```

Reports are local operational output under `output/`; they are not PIOS
Knowledge records and are intentionally excluded from the root repository.

Read [SYSTEM.md](SYSTEM.md), [DEPENDENCIES.md](DEPENDENCIES.md), and
[BEHAVIOR.md](BEHAVIOR.md) before changing the service.
