"""[schema] 문단 글 안의 빈 괄호 자리와 체크 칸(□) 위치를 찾는다. 탐지, 검사, 채우기가 같이 쓰는 순수 함수."""

import re

BOX_EMPTY = "□"
BOX_CHECKED = "■"
# 채운 뒤 다시 채워도 같은 자리를 찾도록 칠한 칸과 비슷한 기호도 칸으로 본다
BOXES = "□☐■☑"
SLOT_BLANK = r"[\s_＿]"
# 라벨 바로 뒤의 빈 괄호. 라벨은 괄호, 콜론, 쉼표, 칸 기호가 없는 낱말 하나
LABEL = r"(?P<label>[^\s()（）\[\]:：,，" + BOXES + r"]{1,20})"
SLOT = re.compile(LABEL + r"\s*[(（](?P<blank>" + SLOT_BLANK + r"{2,})[)）]")
OPTION = re.compile(r"[" + BOXES + r"]\s*(?P<option>[^" + BOXES + r"]*)")
# 선택지 끝의 괄호 자리(`기타(   )`)는 선택지 이름이 아니다. 괄호를 채워도 선택지를 찾을 수 있게 뗀다
OPTION_TAIL = re.compile(r"\s*[(（][^)）]*[)）]?\s*$")
OPTION_MAX = 20


def slot_span(text: str, label: str) -> tuple[int, int] | None:
    """label 바로 뒤 첫 빈 괄호의 안쪽 [start, end). 괄호 기호와 뒤 글은 범위 밖이다. 없으면 None."""
    pattern = re.escape(label) + r"\s*[(（](" + SLOT_BLANK + r"+)[)）]"
    m = re.search(pattern, text)
    return m.span(1) if m else None


def slot_labels(text: str) -> list[str]:
    """빈 괄호마다 바로 앞 라벨을 나온 순서로 한 번씩. 같은 라벨의 두 번째 괄호는 slot_span 이 못 가리켜 뺀다."""
    out: list[str] = []
    for m in SLOT.finditer(text):
        label = m.group("label")
        if label not in out and any(ch.isalpha() for ch in label):
            out.append(label)
    return out


def box_options(text: str) -> list[str]:
    """칸 기호마다 뒤에 붙은 선택지 이름. 끝의 괄호 자리는 떼고, 비었거나 너무 긴 것은 빼며 겹치면 한 번만."""
    out: list[str] = []
    for m in OPTION.finditer(text):
        option = OPTION_TAIL.sub("", m.group("option")).strip()
        if option and len(option) <= OPTION_MAX and option not in out:
            out.append(option)
    return out


def box_positions(text: str, options: tuple[str, ...]) -> dict[str, int] | None:
    """선택지마다 앞 칸 기호의 위치. 선택지가 글에 나온 순서대로 다 있어야 하고, 하나라도 없으면 None."""
    out: dict[str, int] = {}
    at = 0
    for option in options:
        m = re.compile(r"[" + BOXES + r"]\s*" + re.escape(option)).search(text, at)
        if m is None:
            return None
        out[option] = m.start()
        at = m.end()
    return out
