"""Web HUD 를 스크립트 프로바이더(실 LLM 없음)와 격리된 임시 디렉토리로 띄운다. e2e 검증용."""

# uv run python scripts/e2e/launch_hud.py &          # 7799 포트
# uv run --with playwright python scripts/e2e/hud_flow.py

import os
import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(tempfile.gettempdir())
WORK = Path(tempfile.mkdtemp(prefix="ash-e2e-"))
(ROOT / "ash-e2e-workdir").write_text(str(WORK))

os.environ.update(
    {
        "ASH_LLM__PROVIDER": "scripted",
        "ASH_LLM__MODEL": "scripted-1",
        "ASH_MEMORY__BACKEND": "in_memory",
        "ASH_SESSION__PERSISTENCE_BACKEND": "jsonl",
        "ASH_SESSION__SESSIONS_DIR": str(WORK / "sessions"),
        "ASH_PROCEDURES__DIR": str(WORK / "procedures"),
        "ASH_SECURITY__APPROVALS_PATH": str(WORK / "approvals.yaml"),
        # 에이전트별 규칙 파일(#88). 비우면 ALWAYS 가 홈의 ~/.ash/approvals/main.yaml 에 남는다
        "ASH_SECURITY__AGENT_APPROVALS_DIR": str(WORK / "approvals"),
        "ASH_SECURITY__API_KEYS": "{}",
        # 성찰 → 🔔 → 피드백 시나리오. 사고와 데몬을 켜고 2초마다 성찰한다. 템플릿은 홈의 사용자 파일이 아닌 기본값
        "ASH_THOUGHT__ENABLED": "true",
        "ASH_THOUGHT__PROVIDER": "scripted",  # .env 의 사고 모델(openai)이 끼어들지 않게
        "ASH_THOUGHT__MODEL": "scripted-1",
        "ASH_THOUGHT__BASE_URL": "",
        "ASH_THOUGHT__PROMPT_PATH": str(WORK / "inner_thought.md"),
        "ASH_THOUGHT__REFLECTION_PROMPT_PATH": str(WORK / "inner_thought_reflection.md"),
        "ASH_PROACTIVE__ENABLED": "true",
        "ASH_PROACTIVE__DAEMON_ENABLED": "true",
        "ASH_PROACTIVE__DAEMON_INTERVAL_SEC": "2",
        "ASH_PROACTIVE__DECISION_MODEL": "",
        "ASH_SCHEDULER__ENABLED": "false",
        "ASH_AGENTS__ENABLED": "false",
        "ASH_EXTERNAL__ENABLED": "false",
        "ASH_PLUGIN__TOOLS_DIR": str(WORK / "tools"),
        "ASH_PLUGIN__SKILLS_DIR": str(WORK / "skills"),
        "ASH_PLUGIN__PLUGINS_DIR": str(WORK / "plugins"),
        "ASH_OPENLOOP__BACKEND": "in_memory",
        "ASH_USER_MODEL__BACKEND": "in_memory",
        "ASH_SETTINGS_FILE": str(WORK / "settings.yaml"),
    }
)

from ash_industry.model_layer.model_types import StopEvent, TextDeltaEvent, ToolCallDeltaEvent, Usage  # noqa: E402
from ash_industry.model_layer.model_registry import get_default_registry  # noqa: E402

# 성찰 시나리오의 약속. AGENDA 판단이 열고, 기한이 DUE_SOON 안이라 성찰이 먼저 말을 건다
PROMISE = "20분 뒤에 팀에 배포 결과를 공유하기로 했어. 기억해줘"
PROMISE_LOOP = "팀에 배포 결과 공유하기"
PROMISE_EVIDENCE = "20분 뒤에 팀에 배포 결과를 공유하기로 했어"
PROACTIVE_UTTERANCE = "배포 결과 공유 시간이 다가옵니다. 준비는 됐나요?"

SCRIPTS = {
    PROMISE: ([], "네, 기억해 둘게요."),
    "run-echo": ([("bash", {"command": "echo hello"})], "done: hello"),
    "multi": (
        [
            ("glob", {"pattern": "*.md"}),
            ("read_file", {"path": "README.md", "limit": 3}),
            ("bash", {"command": "echo multi"}),
        ],
        "세 단계 작업 완료.",
    ),
}
DISTILL = json.dumps(
    {
        "name": "scan-and-echo",
        "description": "마크다운을 훑고 README 를 읽은 뒤 셸로 확인한다",
        "parameters": "확인할 디렉토리",
        "steps": ["glob 으로 *.md 나열", "read_file 로 README 앞부분 확인", "bash 로 echo 실행"],
    },
    ensure_ascii=False,
)
SILENT_FRAME = json.dumps({"decision": "silent", "confidence": 0.1})
# 성찰은 늘 같은 말을 고른다. 첫 번은 🔔 로 나가고, 그 뒤는 "최근에 건넨 말" 반복 게이트와 쿨다운이 막는다
ACT_FRAME = json.dumps(
    {
        "observation": "배포 결과 공유 약속이 곧이다",
        "interpretation": "사용자가 곧 팀에 배포 결과를 공유해야 한다",
        "decision": "act",
        "confidence": 0.95,
        "rationale": "기한이 가까운 약속",
        "utterance": PROACTIVE_UTTERANCE,
    },
    ensure_ascii=False,
)
EMPTY_VERDICT = json.dumps({"open_loops": [], "closed_loops": []})


def _judge_verdict(prompt: str) -> str:
    """AGENDA 판단. 약속 문장이 [사용자 입력] 줄에 있으면 20분 뒤 기한으로 연다."""
    # 지시문 아래에도 "[사용자 입력]" 이 여러 번 나오므로 값이 든 줄만 본다
    user_input = next((line for line in prompt.splitlines() if line.startswith("[사용자 입력] ")), "")
    if PROMISE_EVIDENCE not in user_input:
        return EMPTY_VERDICT
    due = (datetime.now() + timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M")
    return json.dumps(
        {"open_loops": [f"{PROMISE_LOOP} @{due} (근거: {PROMISE_EVIDENCE})"], "closed_loops": []}, ensure_ascii=False
    )


def _feedback_verdict(prompt: str) -> str:
    answer = prompt.rsplit("[사용자의 답]", 1)[-1]
    verdict = "dismiss" if any(w in answer for w in ("아니", "됐어", "필요 없")) else "other"
    return json.dumps({"verdict": verdict})


def _text(m):
    c = getattr(m, "content", "")
    if isinstance(c, str):
        return c
    return " ".join(getattr(b, "text", "") for b in c if getattr(b, "text", ""))


class ScriptedProvider:
    provider_name = "scripted"

    def supports_thinking(self):
        return False

    def supports_images(self):
        return False

    async def stream(self, model, context, options=None):
        msgs = context.messages
        if context.tools is None:
            prompt = _text(msgs[-1]) if msgs else ""
            if "[도구 호출 순서]" in prompt:
                yield TextDeltaEvent(delta=DISTILL)
            elif "AGENDA 판단 모듈" in prompt:
                yield TextDeltaEvent(delta=_judge_verdict(prompt))
            elif "[비서의 제안]" in prompt:
                yield TextDeltaEvent(delta=_feedback_verdict(prompt))
            elif "자율 성찰 시점" in prompt:
                yield TextDeltaEvent(delta=ACT_FRAME)
            elif "JSON" in prompt and "decision" in prompt:
                yield TextDeltaEvent(delta=SILENT_FRAME)
            else:
                yield TextDeltaEvent(delta="요약: 테스트 세션")
            yield StopEvent(reason="stop", usage=Usage(input=5, output=5))
            return

        # 메모리 블록([핵심 사실] 등)도 user 역할이라 "[" 로 시작하지 않는 마지막 사용자 메시지를 찾는다
        users = [i for i, m in enumerate(msgs) if m.role == "user" and isinstance(m.content, str)]
        idx = max((i for i in users if not msgs[i].content.startswith("[")), default=-1)
        text = msgs[idx].content.strip() if idx >= 0 else ""
        steps, final = SCRIPTS.get(text, ([], f"echo: {text}"))
        done = sum(1 for m in msgs[idx + 1 :] if m.role == "tool_result")
        if done < len(steps):
            name, args = steps[done]
            yield ToolCallDeltaEvent(id=f"call_{done}", name=name, arguments_delta=json.dumps(args))
            yield StopEvent(reason="tool_use", usage=Usage(input=10, output=5))
        else:
            yield TextDeltaEvent(delta=final)
            yield StopEvent(reason="stop", usage=Usage(input=10, output=5))


get_default_registry().register(ScriptedProvider())

from ash_industry.ui.cli.cli_startup import main  # noqa: E402

sys.argv = ["ash-industry", "--web", "--port", "7799"]
main()
