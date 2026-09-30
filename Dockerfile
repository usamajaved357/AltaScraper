FROM python:3.11-slim

WORKDIR /app

# System deps needed by Playwright's Chromium (used by crawl4ai's scraper fallback)
# and by Pillow/lxml-style wheels that occasionally need build tools.
# tini (30 Sep 2026 RAM investigation): a tiny init that runs as PID 1 and reaps
# zombie processes. Without it, the listing-run subprocesses and the Chromium
# children a scrape leaves behind are never reaped and hold their memory.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    tini \
    && rm -rf /var/lib/apt/lists/*

# 30 Sep 2026 RAM investigation: glibc gives every thread its own malloc arena
# (up to 8 x CPU cores), and a threaded Flask app fragments them so memory is
# never handed back. Two arenas keeps the footprint flat at no measurable cost.
ENV MALLOC_ARENA_MAX=2
# 30 Sep 2026 RAM investigation: each listing run is its own Python subprocess
# (domain/run_slots.py, code default 6). Three at once in production bounds the
# peak memory; a Railway variable of the same name still overrides this.
ENV ALTA_RUNS_TOTAL=3

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY . .

RUN chmod +x docker-entrypoint.sh

EXPOSE 10000

# tini is PID 1 (30 Sep 2026 RAM investigation): it forwards signals to the app
# and reaps orphaned children (Debian's tini package installs /usr/bin/tini).
ENTRYPOINT ["/usr/bin/tini", "--", "./docker-entrypoint.sh"]
