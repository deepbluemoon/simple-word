FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.11-slim AS python-deps
WORKDIR /app
COPY pyproject.toml .
COPY api ./api
COPY gate ./gate
COPY training ./training
COPY simple_word ./simple_word
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --no-compile . \
 && /opt/venv/bin/pip uninstall -y simple-word pip setuptools wheel \
 && find /opt/venv/lib/python3.11/site-packages -type d \( -name test -o -name tests -o -name __pycache__ \) -prune -exec rm -rf '{}' + \
 && find /opt/venv/lib/python3.11/site-packages -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete \
 && find /opt/venv/lib/python3.11/site-packages -type d -name '*.dist-info' -exec sh -c 'find "$1" -type f \( -name RECORD -o -name INSTALLER -o -name WHEEL -o -name direct_url.json \) -delete' _ '{}' \; \
 && find /opt/venv -type d -empty -delete

FROM python:3.11-slim AS runtime
WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1
COPY --from=python-deps /opt/venv /opt/venv
COPY api ./api
COPY simple_word ./simple_word
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
RUN useradd --system --uid 10001 app && mkdir -p /app/logs && chown app:app /app/logs
USER app
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
