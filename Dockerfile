FROM python:3.10-slim

WORKDIR /app

# Install system dependencies if needed (e.g. for dbt or duckdb extensions)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Set environment variables
ENV DAGSTER_HOME=/app/dagster_home
ENV PYTHONPATH=/app

# Create directory for Dagster home and data
RUN mkdir -p $DAGSTER_HOME /data

# Copy dagster.yaml if we had one, otherwise default sqlite is used.

EXPOSE 3000 8001
