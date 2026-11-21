FROM python:3.11-slim AS base

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
COPY src/ src/

RUN uv sync --frozen --no-dev

# ── test stage ────────────────────────────────────────────────────────────────
FROM base AS test

# web·scheduler extra까지 설치해야 Web HUD(fastapi)·스케줄러(croniter) 테스트가
# skip·수집 오류 없이 실제로 돈다.
RUN uv sync --frozen --extra web --extra scheduler

COPY tests/ tests/

ENV PYTHONPATH=/app/src
ENV ASH_DEBUG=true
ENV ASH_LLM__PROVIDER=faux
ENV ASH_LLM__MODEL=faux-model
ENV ASH_MEMORY__BACKEND=in_memory
ENV ASH_SESSION__PERSISTENCE_BACKEND=jsonl
ENV ASH_SESSION__SESSIONS_DIR=/tmp/ash/sessions
ENV ASH_MEMORY__SQLITE_PATH=/tmp/ash/memory.db
ENV ASH_SECURITY__REQUIRE_AUTH=false

CMD ["uv", "run", "pytest", "-v", "--no-header", "--tb=short"]

# ── runtime-web stage (Web HUD backend) ───────────────────────────────────────
FROM base AS runtime-web

# scheduler extra(croniter)가 없으면 스케줄러가 조용히 꺼지고 HUD Agenda 의 다음 실행 시각도 비는다.
# piper extra 는 영어 문장을 서버에서 읽는 음성(ASH_VOICE__ENGLISH_TTS_PROVIDER=piper)용이다.
# wake extra 는 웨이크워드(ASH_VOICE__WAKE_MODEL_DIR)용이다.
# discord extra 는 봇이 음성 채널에서 알림을 읽는 데 쓰고(ASH_NOTIFY__DISCORD_BOT_TOKEN), 재생에 ffmpeg 가 필요하다.
# voice extra 는 서버 STT(ASH_VOICE__STT_PROVIDER=whisper)와 서버 TTS(supertonic)용이다. 앱(iOS)이 녹음을 서버로 보낸다.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
# mcp extra 는 MCP 컨테이너(ash-mcp)의 도구를 에이전트 도구로 붙이는 클라이언트다.
RUN uv sync --frozen --extra web --extra scheduler --extra piper --extra wake --extra discord --extra voice --extra mcp --no-dev
# 음성 모델(supertonic, faster-whisper)을 볼륨(/root/.ash)에 받아 컨테이너를 다시 만들어도 다시 받지 않는다
ENV HF_HOME=/root/.ash/cache/huggingface
# supertonic 은 HF_HOME 을 보지 않고 ~/.cache/supertonic3 에 받는다. 같은 볼륨으로 돌린다
ENV SUPERTONIC_CACHE_DIR=/root/.ash/cache/supertonic3

COPY . .

ENV PYTHONPATH=/app/src
ENV PATH="/app/.venv/bin:$PATH"

# uv run 은 시작할 때마다 dev 그룹까지 맞추려고 mypy, ruff 등을 받는다. 빌드 때 맞춘 .venv 를 그대로 쓴다
CMD ["ash-industry", "--host", "0.0.0.0", "--port", "7777"]
