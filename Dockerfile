FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Nodus VM: set NODUS_SOURCE_PATH at runtime (docker run -e or compose
# environment block) to point to a compiled nodus.runtime.embedding module.
# This image cannot bundle the Nodus VM — it must be volume-mounted or
# provided in a derived image. See docs/ops/RUNBOOK.md §6.
ENV NODUS_SOURCE_PATH=""

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY AINDY/requirements.txt /app/AINDY/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/AINDY/requirements.txt

COPY . /app

EXPOSE 8000

CMD ["uvicorn", "AINDY.main:app", "--host", "0.0.0.0", "--port", "8000"]
