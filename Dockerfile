FROM python:3.11-slim

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    XHS_BRIDGE_HOST=0.0.0.0 \
    XHS_BRIDGE_PORT=9333

WORKDIR /app

RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" uv

COPY pyproject.toml uv.lock README.md /app/
COPY bridge /app/bridge

RUN uv sync --frozen --no-dev --no-install-project --default-index "${UV_DEFAULT_INDEX}"

EXPOSE 9333

CMD ["uv", "run", "python", "-m", "bridge.server"]
