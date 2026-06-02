FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PANDA_TRACE_API_HOST=0.0.0.0
ENV PANDA_TRACE_API_PORT=8000

WORKDIR /app

COPY pyproject.toml README.md ./
COPY panda_trace ./panda_trace
COPY docs ./docs

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn panda_trace.main:app --host \"$PANDA_TRACE_API_HOST\" --port \"$PANDA_TRACE_API_PORT\""]
