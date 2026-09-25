FROM python:3.11-slim

LABEL maintainer="ml-platform@biogenai.corp"
LABEL description="BioGenAI BioTools MCP Server"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY biotools/ biotools/
COPY server.py .

ENV BIOTOOLS_LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "server.py"]
