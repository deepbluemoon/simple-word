FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY api ./api
COPY gate ./gate
COPY training ./training
COPY simple_word ./simple_word
RUN pip install --no-cache-dir .
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
RUN useradd --system --uid 10001 app && mkdir -p /app/logs && chown app:app /app/logs
USER app
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
