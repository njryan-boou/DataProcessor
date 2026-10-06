# Build the browser application using the checked-in npm lockfile.
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=network_ca \
    if [ -f /run/secrets/network_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/network_ca; fi; \
    npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Install Python dependencies separately so source changes reuse this layer.
FROM python:3.12-slim-bookworm AS backend-build
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /usr/local/bin/uv
WORKDIR /app/backend
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=secret,id=network_ca \
    if [ -f /run/secrets/network_ca ]; then export SSL_CERT_FILE=/run/secrets/network_ca UV_SYSTEM_CERTS=1; fi; \
    uv sync --locked --no-dev --no-install-project
COPY backend/app ./app
COPY backend/sample.csv ./sample.csv

# One non-root web service serves the compiled frontend and its API.
FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATAFLOW_FRONTEND_DIST=/app/frontend/dist \
    PORT=8000
RUN groupadd --system --gid 10001 dataflow \
    && useradd --uid 10001 --gid dataflow --home-dir /app --no-create-home dataflow
WORKDIR /app/backend
COPY --from=backend-build --chown=10001:10001 /app/backend /app/backend
COPY --from=frontend-build --chown=10001:10001 /build/frontend/dist /app/frontend/dist
COPY --chown=10001:10001 --chmod=755 deploy/start.sh /app/start.sh
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD /app/backend/.venv/bin/python -c "import json,os,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/health',timeout=3); assert json.load(r)['status']=='ok'"
ENTRYPOINT ["/app/start.sh"]
