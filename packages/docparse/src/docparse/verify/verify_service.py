"""[service] 편집 결과 검증. 다시 읽은 구조를 계획과 대조한다. 순수 함수."""

from pydantic import BaseModel, ConfigDict

from docparse.document_model import Document
from docparse.edit_plan import EditPlan

PLACEHOLDER = "{{"


class VerifyResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: bool
    issues: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()


def _related(a: str, b: str) -> bool:
    """셀과 그 안의 문단(t0r1c1 과 t0r1c1p0)은 한쪽이 바뀌면 다른 쪽도 바뀐다."""
    return a == b or a.startswith(b + "p") or b.startswith(a + "p")


def verify_edit(before: Document, after: Document, plan: EditPlan) -> VerifyResult:
    """검사: 대상마다 계획한 글이 들어갔는가, 계획 밖이 바뀌지 않았는가, 구조(id)가 남았는가, {{ 가 남지 않았는가."""
    old = before.texts()
    new = after.texts()
    issues: list[str] = []
    targets = [r.target for r in plan.replacements]
    for item in plan.replacements:
        if item.target not in new:
            issues.append(f"결과에 없는 대상: {item.target}")
        elif new[item.target] != item.text:
            issues.append(f"계획과 다른 글: {item.target}")
    missing = sorted(set(old) - set(new))
    if missing:
        issues.append(f"사라진 항목 {len(missing)}개: {', '.join(missing[:5])}")
    changed = sorted(i for i in old if i in new and old[i] != new[i])
    outside = [i for i in changed if not any(_related(i, t) for t in targets)]
    if outside:
        issues.append(f"계획 밖이 바뀜: {', '.join(outside[:5])}")
    leftover = sorted(i for i, t in new.items() if PLACEHOLDER in t)
    if leftover:
        issues.append(f"자리표시자가 남음: {', '.join(leftover[:5])}")
    return VerifyResult(ok=not issues, issues=tuple(issues), changed=tuple(changed))
