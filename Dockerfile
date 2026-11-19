FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY api ./api
COPY gate ./gate
COPY simple_word ./simple_word
RUN pip install --no-cache-dir .
COPY web ./web
RUN useradd --system --uid 10001 app && mkdir -p /app/logs && chown app:app /app/logs
USER app
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
