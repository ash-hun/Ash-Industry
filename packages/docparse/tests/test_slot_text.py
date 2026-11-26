"""[test] 빈 괄호 자리와 체크 칸 위치 찾기."""

from docparse.template.slot_text import slot_span, box_options, slot_labels, box_positions


def test_slot_span_is_inside_parens_only() -> None:
    text = "성명(      ) 연락처（＿＿＿）"
    start, end = slot_span(text, "성명") or (0, 0)
    assert text[start - 1] == "(" and text[end] == ")"
    assert slot_span(text, "연락처") is not None
    assert slot_span("성명(홍길동)", "성명") is None
    assert slot_span(text, "주소") is None


def test_slot_labels_skip_filled_numbers_and_repeats() -> None:
    assert slot_labels("성명(   ) 서명(인) 2026(   ) 성명(   ) 기간 (  )") == ["성명", "기간"]


def test_box_options_drop_slot_tail_and_duplicates() -> None:
    assert box_options("해당 여부: □ 예 □ 아니오") == ["예", "아니오"]
    assert box_options("☐ 기타(        ) □ 기타") == ["기타"]
    assert box_options("체크 칸이 없다") == []


def test_box_positions_need_all_options_in_order() -> None:
    text = "□ 예 ■ 아니오"
    assert box_positions(text, ("예", "아니오")) == {"예": 0, "아니오": 4}
    assert box_positions(text, ("아니오", "예")) is None
    assert box_positions(text, ("모름",)) is None
