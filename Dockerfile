FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY api ./api
COPY gate ./gate
COPY simple_word ./simple_word
RUN pip install --no-cache-dir .
COPY web ./web
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
