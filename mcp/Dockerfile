# MCP 도구 전용 컨테이너. 서버마다 자식 프로세스 하나를 포트 하나에 띄운다(mcp_launcher.py, servers.yaml).
# Python 서버는 uv tool 로 버전을 박아 설치하고, Node 서버는 npx 로 띄울 수 있게 node 를 둔다.
FROM python:3.12-slim

# libreoffice 와 poppler 는 docs 서버의 PDF, PNG 렌더용이고 fonts-nanum 은 한글 글꼴이 없어 네모로 나오는 것을 막는다
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates nodejs npm \
      libreoffice-writer libreoffice-calc poppler-utils fonts-nanum \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv pyyaml

# Google Workspace(Gmail, Calendar, Drive ...) MCP 서버. 버전은 servers.yaml 의 설명과 함께 올린다
RUN uv tool install workspace-mcp==2.5.0
ENV PATH="/root/.local/bin:$PATH"

# 인증 토큰과 캐시가 볼륨에 남게 작업 디렉토리와 HOME 을 /data 로 둔다
WORKDIR /data
ENV HOME=/data
ENV PYTHONUNBUFFERED=1

# docs 서버(packages/docs_mcp)와 파서(packages/docparse)만 workspace 에서 설치한다. ash_industry 본체는 깔지 않는다
COPY pyproject.toml uv.lock /opt/docs/
COPY packages/ /opt/docs/packages/
RUN mkdir -p /opt/docs/src/ash_industry && touch /opt/docs/src/ash_industry/__init__.py \
 && cd /opt/docs && UV_PROJECT_ENVIRONMENT=/opt/docs/.venv uv sync --frozen --no-dev --package docs-mcp

COPY mcp/mcp_launcher.py /opt/mcp/mcp_launcher.py
COPY mcp/servers.yaml /opt/mcp/servers.yaml

CMD ["python", "/opt/mcp/mcp_launcher.py", "/opt/mcp/servers.yaml"]
