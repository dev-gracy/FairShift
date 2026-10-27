# ─────────────────────────────────────────────────────────────────────────────
# FairShift — Dockerfile
# Multi-stage build for a lean production image (~180 MB vs ~900 MB naive)
#
# Stage 1 (builder): Install Python deps into a venv
# Stage 2 (runtime): Copy venv + source into slim base — no build tools in prod
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: dependency builder ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies for bcrypt (needs gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
 && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /build/venv
ENV PATH="/build/venv/bin:$PATH"

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: run as non-root user
RUN addgroup --system fairshift && adduser --system --ingroup fairshift fairshift

WORKDIR /app

# Copy virtual environment from builder (no gcc/build tools in runtime)
COPY --from=builder /build/venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Copy application source
COPY backend/app ./app
COPY backend/seed.py ./seed.py
COPY backend/pytest.ini ./pytest.ini
COPY config ./config
COPY frontend ./frontend

# Create a writable directory for the SQLite database
RUN mkdir -p /data && chown fairshift:fairshift /data
ENV DATABASE_URL=sqlite:////data/fairshift.db

# Switch to non-root user
USER fairshift

# Cloud Run injects PORT; default to 8080
ENV PORT=8080
EXPOSE 8080

# Healthcheck for Cloud Run
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')"

# Seed DB then start server
CMD ["sh", "-c", "python seed.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --log-level info"]
