FROM python:3.11-slim

WORKDIR /app

# Install build dependencies if needed (none really required for sqlite)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source folders, scripts, and initial Excel templates
COPY app/ /app/app/
COPY scripts/ /app/scripts/
COPY data/ /app/data/
COPY *.xlsx /app/

# Create volume mount point for database persistence
RUN mkdir -p /app/data

EXPOSE 8000

# Start server using Gunicorn in production mode
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app.server:app"]
