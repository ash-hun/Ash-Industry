"""[schema] 편집 계획(대상 id 와 새 텍스트)과 적용 전 미리보기. 순수 함수만."""

from pydantic import BaseModel, ConfigDict, Field

from docparse.document_model import Document


class Replacement(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: str
    text: str


class EditPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    replacements: tuple[Replacement, ...] = ()

    def targets(self) -> list[str]:
        return [r.target for r in self.replacements]


class Change(BaseModel):
    """바뀔 곳 하나. before 는 지금 텍스트, after 는 계획의 텍스트."""

    model_config = ConfigDict(frozen=True)

    target: str
    before: str
    after: str


class Preview(BaseModel):
    model_config = ConfigDict(frozen=True)

    changes: tuple[Change, ...] = ()
    issues: tuple[str, ...] = Field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.issues


def preview(document: Document, plan: EditPlan) -> Preview:
    """계획을 문서에 대 본다. 읽기 전용 id, 모르는 id, 같은 id 두 번, 변화 없는 항목은 issues 로."""
    texts = document.texts()
    readonly = document.readonly_ids()
    changes: list[Change] = []
    issues: list[str] = []
    seen: set[str] = set()
    for item in plan.replacements:
        if item.target in seen:
            issues.append(f"같은 대상이 두 번: {item.target}")
            continue
        seen.add(item.target)
        if item.target in readonly:
            issues.append(f"고칠 수 없는 대상(읽기 전용): {item.target}")
            continue
        if item.target not in texts:
            issues.append(f"없는 대상: {item.target}")
            continue
        before = texts[item.target]
        if before == item.text:
            issues.append(f"바뀌는 것이 없음: {item.target}")
            continue
        changes.append(Change(target=item.target, before=before, after=item.text))
    if not plan.replacements:
        issues.append("치환 항목이 없음")
    return Preview(changes=tuple(changes), issues=tuple(issues))
