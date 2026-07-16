# Weekmenu application image (Python 3.13 + uv).
FROM python:3.13-slim-bookworm

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 8000

CMD ["uv", "run", "litestar", "--app", "src.app:app", "run", "--host", "0.0.0.0", "--port", "8000"]
