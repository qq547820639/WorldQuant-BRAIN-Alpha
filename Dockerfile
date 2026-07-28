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
#   1. Builds wheels for the PRODUCTION dependency set only (core, excludes
#      browser/test/dev) so the runtime stage can install them offline.
#      Only build tools (pip/setuptools/wheel) are installed here — the full
#      dev/test toolchain is NOT needed to build wheels and is omitted to keep
#      this builder layer lean.
#   2. Prepares a cleaned source tree for the runtime image: the entire
#      react_app/ is dropped (only its dist/ is re-added from webbuild) and
#      Python bytecode caches are removed.
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS pybuilder
WORKDIR /app
COPY pyproject.toml README.md ./
COPY brain_alpha_ops/ ./brain_alpha_ops/
# Build wheels for production core deps only (NO browser/test/dev).
# Drop the project wheel itself — the runtime imports from source in /app.
RUN pip install --upgrade pip setuptools wheel --no-cache-dir \
    && pip wheel . --no-cache-dir -w /wheels \
    && rm -f /wheels/brain_alpha_ops-*.whl
# Prepare cleaned source tree for runtime: remove the entire react_app/
# (only dist/ is re-added from webbuild) and any bytecode caches.
RUN rm -rf /app/brain_alpha_ops/web/react_app \
    && find /app/brain_alpha_ops -name __pycache__ -type d -prune -exec rm -rf {} + \
    && find /app/brain_alpha_ops -type f -name "*.pyc" -delete

# ──────────────────────────────────────────────────────────────────────────────
# Stage 3: Runtime — lean (default target)
#   - Slim base image, Python 3.12
#   - Only production Python core deps (no browser/test/dev), from builder wheels
#   - Cleaned Python source (no frontend source/node_modules)
#   - Frontend dist/ only (copied from webbuild)
#   - data/ and config/ exposed as VOLUMEs for persistent runtime state
#   - Default execution mode: headless (no Playwright/Chromium)
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Minimal system libraries for runtime (wget for healthcheck, certs for HTTPS).
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BRAIN_ALPHA_OPS_EXECUTION_MODE=headless \
    BRAIN_ALPHA_OPS_WEB_FRONTEND=react \
    WEB_HOST=0.0.0.0

WORKDIR /app

# Install ONLY production Python core dependencies from builder wheels.
# (no browser/test/dev, no network — fully reproducible from the wheel cache)
COPY --from=pybuilder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl \
    && rm -rf /wheels

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

# Runtime-writable directories (755 — least-privilege).
RUN mkdir -p /app/data /app/config /app/artifacts/evidence \
    && chmod 755 /app/artifacts/evidence

# F-006: create a non-root user and hand it ownership of /app so the web
# process can still write data/config/artifacts. The container must not run
# as root — otherwise a container escape yields host root. evidence/ stays
# 755 (world-readable, owner-writable) so the appuser can write screenshots.
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

# Declare data/ and config/ as volumes so host or named volumes can supply
# persistent state; on first run the image contents seed the volume.
VOLUME ["/app/data", "/app/config"]

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health')" || exit 1

# F-006: drop root for the default runtime target.
USER appuser

CMD ["python", "launch_web.py"]

# ──────────────────────────────────────────────────────────────────────────────
# Stage 4: Runtime Full — extends runtime with Playwright + Chromium
#   Use this stage when browser-based alpha execution is required.
#   Build with: docker build --target runtime-full .
# ──────────────────────────────────────────────────────────────────────────────
FROM runtime AS runtime-full

# F-006: runtime dropped to appuser; browser dependency install needs root.
USER root

# System libraries required by Playwright/Chromium (browser execution mode).
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation libasound2 \
    libatk-bridge2.0-0 libatk1.0-0 libcups2 libdrm2 \
    libgbm1 libgtk-3-0 libnspr4 libnss3 libu2f-udev \
    libxcomposite1 libxdamage1 libxfixes3 libxkbcommon0 \
    libxrandr2 xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright and Chromium browser. F-006: install browsers to a shared
# path owned by appuser so the non-root runtime user can launch Chromium.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
RUN pip install --no-cache-dir playwright \
    && python -m playwright install chromium --with-deps \
    && chown -R appuser:appuser /opt/ms-playwright

# F-006: drop back to the non-root user for browser execution too.
USER appuser

# Override execution mode to browser when using the full image.
ENV BRAIN_ALPHA_OPS_EXECUTION_MODE=browser
