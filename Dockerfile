FROM python:3.11-slim

WORKDIR /app

# System deps occasionally needed by numpy/pandas wheels
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the multi-pair paper portfolio. Override `command` for live.
CMD ["python", "run_aries.py", "--live", "--pairs", "ETHUSDT,SOLUSDT,LINKUSDT", "--tf", "15m", "--capital", "100"]
