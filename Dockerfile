# ── Stage 1: Build React frontend ──
FROM node:22-bookworm AS webbuild
WORKDIR /app
COPY brain_alpha_ops/web/react_app/package.json \
     brain_alpha_ops/web/react_app/package-lock.json* \
     ./brain_alpha_ops/web/react_app/
WORKDIR /app/brain_alpha_ops/web/react_app
RUN npm ci && npm run build

# ── Stage 2: Python backend + bundled frontend ──
FROM python:3.13-slim

# System deps for Playwright (optional — install only for browser mode)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget ca-certificates fonts-liberation libasound2 \
    libatk-bridge2.0-0 libatk1.0-0 libcups2 libdrm2 \
    libgbm1 libgtk-3-0 libnspr4 libnss3 libu2f-udev \
    libxcomposite1 libxdamage1 libxfixes3 libxkbcommon0 \
    libxrandr2 xdg-utils \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BRAIN_ALPHA_EXECUTION_BACKEND=browser \
    BRAIN_ALPHA_OPS_WEB_FRONTEND=react

WORKDIR /app

# Install Python deps
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip setuptools wheel \
    && pip install -e ".[browser,test,dev]" --no-cache-dir \
    && python -m playwright install chromium --with-deps

# Copy source
COPY brain_alpha_ops/ ./brain_alpha_ops/
COPY config/ ./config/
COPY data/ ./data/
COPY launch_web.py ./

# Copy built frontend from Stage 1
COPY --from=webbuild /app/brain_alpha_ops/web/react_app/dist ./brain_alpha_ops/web/react_app/dist

# Artifacts directory for browser evidence
RUN mkdir -p /app/artifacts/evidence && chmod 777 /app/artifacts/evidence

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health')" || exit 1

CMD ["python", "launch_web.py"]
