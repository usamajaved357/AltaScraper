FROM python:3.11-slim

WORKDIR /app

# System deps needed by Playwright's Chromium (used by crawl4ai's scraper fallback)
# and by Pillow/lxml-style wheels that occasionally need build tools.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY . .

RUN chmod +x docker-entrypoint.sh

EXPOSE 10000

ENTRYPOINT ["./docker-entrypoint.sh"]
