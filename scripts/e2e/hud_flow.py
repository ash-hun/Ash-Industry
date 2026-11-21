"""Playwright 로 Web HUD 를 조작해 성찰 🔔 와 피드백, 승인 기억, 절차 학습/승인 흐름을 검증한다."""

import sys
import json
import tempfile
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(tempfile.gettempdir())
WORK = Path((ROOT / "ash-e2e-workdir").read_text().strip())
BASE = "http://127.0.0.1:7799"
SHOTS = ROOT / "shots"
SHOTS.mkdir(exist_ok=True)
checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def messages_text(page) -> str:
    return page.evaluate("() => document.getElementById('messages').innerText")


def send(page, text: str) -> None:
    page.wait_for_function("() => !document.getElementById('chat-input').disabled", timeout=20000)
    page.fill("#chat-input", text)
    page.press("#chat-input", "Enter")
    # 슬래시 피커가 열려 있으면 첫 Enter 는 항목 선택이다. 입력이 남아 있으면 한 번 더 보낸다
    page.wait_for_timeout(200)
    if page.input_value("#chat-input").strip():
        page.press("#chat-input", "Enter")


def wait_text(page, needle: str, timeout: int = 20000) -> None:
    page.wait_for_function(
        "n => document.getElementById('messages').innerText.includes(n)", arg=needle, timeout=timeout
    )


def overlay_visible(page) -> bool:
    return page.evaluate("() => !document.getElementById('approval-overlay').classList.contains('hidden')")


def activity_text(page) -> str:
    return page.evaluate("() => document.getElementById('activity-log').innerText")


def thought_count(page) -> int:
    return page.evaluate("() => document.querySelectorAll('#messages .msg.thought').length")


def wait_activity(page, needle: str, timeout: int = 30000) -> None:
    page.wait_for_function(
        "n => document.getElementById('activity-log').innerText.includes(n)", arg=needle, timeout=timeout
    )


def session_files_contain(needle: str) -> bool:
    return any(needle in p.read_text() for p in (WORK / "sessions").glob("*.jsonl"))


PROMISE = "20분 뒤에 팀에 배포 결과를 공유하기로 했어. 기억해줘"
PROACTIVE_UTTERANCE = "배포 결과 공유 시간이 다가옵니다. 준비는 됐나요?"


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 860})
    page.goto(BASE + "/")
    page.wait_for_function("() => !document.getElementById('chat-input').disabled", timeout=20000)
    page.screenshot(path=str(SHOTS / "00_ready.png"))

    # ── 0. 약속 → AGENDA 에 열림 → 성찰이 🔔 로 먼저 말함 → 다음 말이 무시 피드백으로 학습됨 ──
    send(page, PROMISE)
    wait_text(page, "네, 기억해 둘게요.")
    page.wait_for_function(
        "() => document.getElementById('openloop-list').innerText.includes('배포 결과 공유')", timeout=20000
    )
    check("promise appears in OPEN LOOPS", True)
    wait_activity(page, "🔔 " + PROACTIVE_UTTERANCE)
    check("reflection spoke first with a 🔔", PROACTIVE_UTTERANCE in messages_text(page))
    check("reflection frame shown as 💭", thought_count(page) >= 1)
    page.screenshot(path=str(SHOTS / "00a_proactive.png"))

    thoughts_before = thought_count(page)
    send(page, "아니오")
    wait_text(page, "echo: 아니오")
    for _ in range(50):
        if session_files_contain('"proactive_ack"'):
            break
        page.wait_for_timeout(200)
    check("dismissal is recorded as feedback for the 🔔", session_files_contain('"proactive_ack"'))
    # 다음 성찰은 같은 말을 다시 고르지만 반복 게이트와 쿨다운이 막아 💭 만 늘고 🔔 는 하나로 남는다
    page.wait_for_function(
        "n => document.querySelectorAll('#messages .msg.thought').length > n", arg=thoughts_before, timeout=20000
    )
    check("later reflection stays silent", activity_text(page).count("🔔 " + PROACTIVE_UTTERANCE) == 1)
    page.screenshot(path=str(SHOTS / "00b_feedback.png"))

    # ── 1. bash 호출 → 승인 오버레이 + ALWAYS 버튼(패턴 표시) ─────────────────
    send(page, "run-echo")
    page.wait_for_function(
        "() => !document.getElementById('approval-overlay').classList.contains('hidden')", timeout=20000
    )
    always_text = page.inner_text("#btn-always")
    command_text = page.inner_text("#approval-command")
    check("approval overlay shows command", command_text.strip() == "echo hello", command_text)
    check("ALWAYS button shows suggested pattern", "echo hello" in always_text, always_text)
    page.screenshot(path=str(SHOTS / "01_approval_overlay.png"))

    page.click("#btn-always")
    page.wait_for_function(
        "() => document.getElementById('approval-overlay').classList.contains('hidden')", timeout=5000
    )
    wait_text(page, "done: hello")
    # ALWAYS 는 공용 파일이 아니라 에이전트 규칙 파일(approvals/<agent>.yaml)에 남는다
    rules_file = WORK / "approvals" / "main.yaml"
    rules = rules_file.read_text() if rules_file.exists() else ""
    check(
        "approvals/main.yaml has bash/echo hello rule",
        "tool: bash" in rules and "pattern: echo hello" in rules,
        rules.strip(),
    )
    page.screenshot(path=str(SHOTS / "02_after_always.png"))

    # ── 2. 같은 명령 재호출 → 묻지 않고 실행 ─────────────────────────────────
    before = messages_text(page).count("done: hello")
    send(page, "run-echo")
    asked = False
    for _ in range(30):
        page.wait_for_timeout(100)
        if overlay_visible(page):
            asked = True
            break
    page.wait_for_function(
        "n => document.getElementById('messages').innerText.split('done: hello').length - 1 > n",
        arg=before,
        timeout=20000,
    )
    check("second run did not ask for approval", not asked)
    page.screenshot(path=str(SHOTS / "03_no_prompt_second_run.png"))

    # ── 3. /procedures 비어 있음 ──────────────────────────────────────────────
    send(page, "/procedures")
    wait_text(page, "학습된 절차가 없습니다")
    check("/procedures lists nothing initially", True)

    # ── 4. 다단계 작업(도구 3회) → 다른 패턴은 다시 묻는다 → 이번 한 번 허용 ─
    send(page, "multi")
    page.wait_for_function(
        "() => !document.getElementById('approval-overlay').classList.contains('hidden')", timeout=20000
    )
    cmd2 = page.inner_text("#approval-command")
    check("different pattern asks again", cmd2.strip() == "echo multi", cmd2)
    page.click("#btn-allow")
    wait_text(page, "세 단계 작업 완료")
    rules_after = rules_file.read_text()
    check("ALLOW once does not add a rule", "echo multi" not in rules_after)

    # ── 5. /procedures learn → 초안, approve → 도구 등록, learn 재실행 → 없음 ─
    send(page, "/procedures learn")
    wait_text(page, "초안 저장")
    text = messages_text(page)
    name = "scan-and-echo"
    check("learn saved draft", f"초안 저장: {name}" in text)
    draft_file = WORK / "procedures" / f"{name}.md"
    check("draft file exists with source", draft_file.exists() and "source: default#" in draft_file.read_text())
    page.screenshot(path=str(SHOTS / "04_learned.png"))

    send(page, "/procedures learn")
    wait_text(page, "새로 배울 구간이 없습니다")
    check("learn twice writes nothing new", len(list((WORK / "procedures").glob("*.md"))) == 1)

    send(page, f"/procedures approve {name}")
    wait_text(page, f"procedure_{name}")
    tools = json.load(urllib.request.urlopen(BASE + "/api/tools"))
    tool_names = [t.get("name") for t in tools.get("tools", [])]
    check("approved procedure is exposed as a tool", f"procedure_{name}" in tool_names, ",".join(tool_names))
    check("file status flipped to approved", "status: approved" in draft_file.read_text())

    send(page, "/procedures")
    wait_text(page, f"✓ {name} [approved]")
    check("/procedures shows approved mark", True)
    page.screenshot(path=str(SHOTS / "05_approved.png"))

    # ── 6. 승인된 절차를 스킬로 호출 → 본문이 LLM 프롬프트로 확장된다 ────────
    send(page, f"/{name} docs")
    wait_text(page, "echo:")
    check("approved procedure is callable as a slash skill", "echo: 아래 절차를" in messages_text(page))
    page.screenshot(path=str(SHOTS / "06_skill_call.png"))

    browser.close()

failed = [c for c in checks if not c[1]]
print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
sys.exit(1 if failed else 0)
