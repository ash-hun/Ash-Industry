# MCP 도구 전용 컨테이너. 서버마다 자식 프로세스 하나를 포트 하나에 띄운다(mcp_launcher.py, servers.yaml).
# Python 서버는 uv tool 로 버전을 박아 설치하고, Node 서버는 npx 로 띄울 수 있게 node 를 둔다.
FROM python:3.12-slim

# libreoffice(writer, calc, impress) 와 poppler 는 docs 서버의 DOCX, XLSX, PPTX 를 PDF, PNG 로 그리는 데 쓰고 fonts-nanum 은 한글 글꼴이 없어 네모로 나오는 것을 막는다
# librsvg2-bin(rsvg-convert)은 rhwp 가 만든 HWP, HWPX 의 SVG 를 fontconfig 글꼴로 PDF, PNG 로 그린다
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates nodejs npm \
      libreoffice-writer libreoffice-calc libreoffice-impress poppler-utils fonts-nanum librsvg2-bin libfreetype6 \
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
# rhwp 휠에 든 libfreetype 는 FT_Palette_Select 가 없어 import 가 실패한다(2026-11-24 실측). 시스템 것으로 교체한다.
# ln -sf 라 다시 빌드해도 결과가 같다
RUN for lib in /opt/docs/.venv/lib/python3.12/site-packages/rhwp_python.libs/libfreetype-*.so.6; do \
      ln -sf "/usr/lib/$(uname -m)-linux-gnu/libfreetype.so.6" "$lib"; \
    done \
 && /opt/docs/.venv/bin/python -c "import rhwp"

COPY mcp/mcp_launcher.py /opt/mcp/mcp_launcher.py
COPY mcp/servers.yaml /opt/mcp/servers.yaml

CMD ["python", "/opt/mcp/mcp_launcher.py", "/opt/mcp/servers.yaml"]
