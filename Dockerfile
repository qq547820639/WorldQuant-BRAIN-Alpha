# ──────────────────────────────────────────────────────────────────────────────
# Stage 1: React frontend builder
#   Builds the production SPA bundle (dist/) that is later copied into the
#   runtime image. node_modules and source are NOT carried forward.
# ──────────────────────────────────────────────────────────────────────────────
FROM node:22-bookworm AS webbuild
WORKDIR /app/brain_alpha_ops/web/react_app
# Copy lockfile first for npm ci layer caching — when only source changes
# (not dependencies), the expensive `npm ci` layer is reused.
COPY brain_alpha_ops/web/react_app/package*.json ./
RUN npm ci
# Copy source and build the production SPA bundle (dist/).
COPY brain_alpha_ops/web/react_app/ ./
RUN npm run build

# ──────────────────────────────────────────────────────────────────────────────
# Stage 2: Python builder
#   1. Builds wheels for the PRODUCTION dependency set only (browser + core,
#      excludes test/dev) so the runtime stage can install them offline.
#      Only build tools (pip/setuptools/wheel) are installed here — the full
#      dev/test toolchain is NOT needed to build wheels and is omitted to keep
#      this builder layer lean.
#   2. Prepares a cleaned source tree for the runtime image: the entire
#      react_app/ is dropped (only its dist/ is re-added from webbuild) and
#      Python bytecode caches are removed.
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS pybuilder
WORKDIR /app
COPY pyproject.toml README.md ./
COPY brain_alpha_ops/ ./brain_alpha_ops/
# Build wheels for production deps only (browser + core; NO test/dev).
# Drop the project wheel itself — the runtime imports from source in /app.
RUN pip install --upgrade pip setuptools wheel --no-cache-dir \
    && pip wheel ".[browser]" --no-cache-dir -w /wheels \
    && rm -f /wheels/brain_alpha_ops-*.whl
# Prepare cleaned source tree for runtime: remove the entire react_app/
# (only dist/ is re-added from webbuild) and any bytecode caches.
RUN rm -rf /app/brain_alpha_ops/web/react_app \
    && find /app/brain_alpha_ops -name __pycache__ -type d -prune -exec rm -rf {} + \
    && find /app/brain_alpha_ops -type f -name "*.pyc" -delete

# ──────────────────────────────────────────────────────────────────────────────
# Stage 3: Runtime (production only)
#   - Slim base image
#   - Only production Python deps (no test/dev), installed from builder wheels
#   - Cleaned Python source (no frontend source/node_modules)
#   - Frontend dist/ only (copied from webbuild)
#   - data/ and config/ exposed as VOLUMEs for persistent runtime state
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

# System libraries required by Playwright/Chromium (browser execution mode).
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget ca-certificates fonts-liberation libasound2 \
    libatk-bridge2.0-0 libatk1.0-0 libcups2 libdrm2 \
    libgbm1 libgtk-3-0 libnspr4 libnss3 libu2f-udev \
    libxcomposite1 libxdamage1 libxfixes3 libxkbcommon0 \
    libxrandr2 xdg-utils \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BRAIN_ALPHA_OPS_EXECUTION_MODE=browser \
    BRAIN_ALPHA_OPS_WEB_FRONTEND=react \
    WEB_HOST=0.0.0.0

WORKDIR /app

# Install ONLY production Python dependencies from builder wheels.
# (no test/dev, no network — fully reproducible from the wheel cache)
# NOTE: do NOT delete ~/.cache — Playwright stores its Chromium browser there.
COPY --from=pybuilder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl \
    && python -m playwright install chromium --with-deps \
    && rm -rf /wheels /var/lib/apt/lists/*

# Runtime Python source (cleaned in pybuilder — no frontend source/deps).
# PROJECT_ROOT resolves to /app, so data/ and config/ are read from
# /app/data and /app/config.
COPY --from=pybuilder /app/brain_alpha_ops/ ./brain_alpha_ops/
COPY launch_web.py ./

# Copy built frontend from Stage 1 — dist/ ONLY (no node_modules, no source).
COPY --from=webbuild /app/brain_alpha_ops/web/react_app/dist ./brain_alpha_ops/web/react_app/dist

# Bundled static reference data + default config (overridable via volumes).
COPY data/ ./data/
COPY config/ ./config/

# Runtime-writable directories.
RUN mkdir -p /app/data /app/config /app/artifacts/evidence \
    && chmod 777 /app/artifacts/evidence

# Declare data/ and config/ as volumes so host or named volumes can supply
# persistent state; on first run the image contents seed the volume.
VOLUME ["/app/data", "/app/config"]

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health')" || exit 1

CMD ["python", "launch_web.py"]
