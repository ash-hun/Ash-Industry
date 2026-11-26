---
sidebar_position: 4.5
title: Document Tools
---

# Document Tools

문서 도구는 에이전트가 문서 폴더의 행정문서(DOCX, XLSX, HWPX, HWP, PPTX, PDF)를 읽고, 서식을 지킨 채 고치고, 새 DOCX, PPTX, XLSX 를 만들고, 자주 쓰는 양식을 템플릿으로 등록해 값만 받아 채우게 해 주는 MCP 서버(`docs`)다. 서버는 `ash-mcp` 컨테이너 안에서 다른 MCP 서버와 함께 돌고, 에이전트에게는 보통 MCP 도구처럼 보인다. 고친 결과는 언제나 새 파일로 저장하고 원본은 덮어쓰지 않는다. 이 페이지는 지원 형식, 고치는 흐름, 템플릿, 안전장치, 에이전트에게 도구를 주는 방법을 차례로 정리한다.

## 무엇을 할 수 있나

| 도구 | 하는 일 | 쓰기 |
|---|---|---|
| `list_documents` | 문서 폴더(또는 그 아래 `subdir`)의 DOCX, XLSX, HWPX, HWP, PPTX, PDF 목록. 상대 경로, 크기, 수정 시각 | |
| `inspect_document` | 문단과 표 셀에 id 를 붙여 보인다. 빈 문단은 기본으로 뺀다(`include_empty`) | |
| `plan_edit` | 바꿀 곳(`target` id 와 새 글)을 받아 바뀔 곳의 전과 후, 문제 목록, `plan_id` 를 돌려준다. 파일은 건드리지 않는다 | |
| `apply_edit` | `plan_id` 의 계획을 새 파일에 적용하고 결과를 다시 읽어 검증한다 | 승인 |
| `render_document` | HTML, PDF, PNG 로 그린다 | |
| `list_templates`, `get_template_schema` | 등록한 템플릿 목록과 필드(이름, 형식, 필수 여부, 글자 수 제한) | |
| `detect_fields` | 빈 양식에서 채울 자리 후보를 찾는다. 아무것도 저장하지 않는다 | |
| `register_template` | 문서를 템플릿으로 등록한다 | 승인 |
| `make_placeholder_copy` | 빈 양식 옆에 자리마다 `{{이름}}` 을 넣은 사본을 만든다 | 승인 |
| `fill_template` | 템플릿에 값을 넣어 새 파일로 저장하고 검증한다 | 승인 |
| `create_document` | 내용(문단, 슬라이드, 시트)을 받아 새 DOCX, PPTX, XLSX 를 만든다 | 승인 |

쓰기 도구 다섯은 MCP 정책의 기본값(쓰기는 ask)에 따라 실행 전에 승인 모달을 띄운다. auto mode 를 켠 에이전트는 묻지 않는다. 승인 흐름은 [Tool & Approve System](./tools-and-approval.md) 과 같다.

## 지원 형식

| 형식 | 읽기 | 고치기, 채우기 | 결과 파일 | 그리기 |
|---|---|---|---|---|
| DOCX | 본문 문단, 표 | 된다. 첫 run 의 글꼴과 굵기를 남긴다 | `.docx` | HTML, PDF, PNG |
| XLSX | 시트 하나가 표 하나, 셀에 주소(`B3`) | 된다. 숫자였던 칸은 숫자로 둔다 | `.xlsx` | HTML, PDF, PNG |
| HWPX | 본문 문단, 본문에 바로 든 표 | 된다. 글자 모양을 남기고 손대지 않은 부분은 바이트 그대로 둔다 | `.hwpx` | HTML. PDF, PNG 는 아래 한계 참고 |
| HWP | 된다(HWPX 모델로 바꿔 연다) | 된다 | `.hwpx` 로 저장 | HWPX 와 같다 |
| PPTX | 글 도형의 문단(`s<슬라이드>sh<도형>p<줄>`), 표. 노트와 차트 글은 읽기 전용 | 된다. 첫 run 의 서식을 남긴다 | `.pptx` | HTML, PDF, PNG |
| PDF | 쪽마다 글 줄, AcroForm 폼 필드 | 본문은 고치지 않는다. 폼 필드만 채운다 | `.pdf` | HTML, PDF(사본), PNG |

HWPX 와 HWP 는 python-hwpx 로 읽고 쓰며, PDF 와 PNG 는 rhwp 로 그린다. DOCX, XLSX, PPTX 의 PDF 는 LibreOffice, PNG 는 pdftoppm 이 만든다. PDF 원본은 LibreOffice 없이 pdftoppm 으로 바로 그린다. PDF 와 PNG 는 원본 옆 `.render/<이름>/` 아래에 저장하고 도구는 경로만 돌려준다.

:::warning

HWPX 와 HWP 의 PDF, PNG 렌더는 지금 Linux 컨테이너(`ash-mcp`)에서 되지 않을 수 있다. 컨테이너의 글꼴 라이브러리가 rhwp 가 요구하는 기능을 갖추지 못해서이고, 이때 `render_document` 는 렌더를 쓸 수 없다는 오류를 돌려준다. 읽기, 고치기, 채우기, HTML 미리보기는 영향을 받지 않는다.

:::

PDF 폼 필드를 채우면 보는 프로그램이 값의 외형을 다시 그리도록 표시해 둔다. 그래서 PDF 뷰어에서는 값이 보여도 PNG 렌더에는 빈칸으로 보일 수 있다. HWP 원본을 열 때 HWPX 로 옮기지 못한 내용이 있으면 `inspect_document` 결과에 그 수가 실리고, 그 내용은 결과 파일에서 빠질 수 있다.

## 고치는 흐름

고치기는 미리보기와 적용 두 단계다. 사용자가 바뀔 곳을 먼저 보고 맞다고 한 뒤에만 파일이 생긴다.

1. `inspect_document` 로 문서를 읽고 바꿀 대상의 id 를 고른다. id 는 본문 문단 `p3`, 표 셀 `t0r2c1`, 셀 안 문단 `t0r2c1p0` 꼴이고 같은 파일이면 언제나 같다
2. `plan_edit` 에 `[{target, text}]` 를 넘긴다. 결과의 바뀔 곳을 "대상 id: 전 → 후" 로 사용자에게 보인다. 없는 대상, 같은 대상 두 번, 바뀌지 않는 항목은 문제로 실린다
3. 사용자가 맞다고 하면 `apply_edit(plan_id)` 를 부른다. 승인 모달이 뜨고, 허용하면 새 파일을 만들고 다시 읽어 계획대로 바뀌었는지, 계획 밖이 바뀌지 않았는지 검증한 결과를 함께 돌려준다

결과 파일은 원본 옆 `<이름>.edited-<YYYYMMDD-HHMMSS>.<확장자>` 이고, HWP 원본이면 확장자가 `.hwpx` 다. 같은 `plan_id` 로 다시 부르면 파일을 더 만들지 않고 처음 결과를 그대로 돌려준다. 계획을 세운 뒤 원본이 바뀌었으면 적용하지 않고 오류를 돌려주므로 `plan_edit` 부터 다시 한다. 계획은 서버 메모리에만 있어서 `ash-mcp` 가 다시 뜬 뒤에도 `plan_edit` 부터 다시 한다.

### HUD 에서 직접 고치기

문서 창 머리의 `편집` 을 누르면 흰 종이 위에 문단과 표가 그려지고, 눌러서 그 자리에서 고친다(DOCX, HWPX, HWP, XLSX, PPTX). `저장`(Ctrl+S, ⌘S) 한 번이 `plan_edit` 과 `apply_edit` 을 이어 부르고, 새 파일을 같은 편집 화면으로 다시 연다. 문제가 있으면 저장하지 않고 고친 글을 그대로 둔 채 이유를 보인다. `Esc` 는 고치던 자리만 되돌린다. 버튼을 누른 것을 사람의 승인으로 보므로 승인 모달은 뜨지 않고, MCP 정책이 `deny` 한 도구는 막힌다(정책의 에이전트 이름은 `hud`).

## 새 문서 만들기

`create_document(path, ...)` 는 문서 폴더 안에 새 파일을 만든다. `path` 의 확장자가 형식을 정하고, 형식마다 내용을 넣는 칸이 다르다.

| 형식 | 칸 | 예 |
|---|---|---|
| DOCX | `title`(맨 위 제목), `blocks` | `[{"type": "heading", "text": "요약"}, {"type": "paragraph", "text": "..."}, {"type": "bullets", "items": ["...", "..."]}, {"type": "table", "rows": [["항목", "상태"], ["배포", "완료"]]}]` |
| PPTX | `slides` | `[{"title": "사업 계획", "subtitle": "2026"}, {"title": "목표", "bullets": ["..."], "notes": "발표자 노트"}, {"title": "일정", "table": [["단계", "기간"]]}]` |
| XLSX | `sheets` | `[{"name": "예산", "rows": [["항목", "금액"], ["출장", 150000]]}]` |

- 서식은 python-docx, python-pptx, openpyxl 의 기본 템플릿을 따른다. PPTX 는 4:3 이고, `bullets` 나 `table` 이 없는 슬라이드는 표지 레이아웃이다. 한 슬라이드에 `bullets` 와 `table` 을 함께 넣지 않는다
- 이미 있는 파일은 덮어쓰지 않고 오류를 돌려준다. 같은 경로에 같은 내용으로 다시 부르면 파일을 더 만들지 않고 처음 결과를 돌려준다(`ash-mcp` 가 다시 뜨기 전까지)
- 확장자와 칸이 맞지 않거나(DOCX 에 `slides`), 빈 슬라이드, 겹치는 시트 이름이 있으면 파일을 만들지 않고 문제를 돌려준다
- 결과는 `{path, format, paragraphs, tables, slides}` 다. Evi 는 만든 뒤 `render_document(png)` 로 그려 HUD 문서 창에 띄운다

## 템플릿

자주 쓰는 양식은 템플릿으로 등록해 두면, 그 뒤로는 값만 말해서 채운다. 템플릿은 두 종류다.

| 종류 | 쓰는 때 | 필드를 정하는 법 |
|---|---|---|
| `placeholder` | 문서에 `{{성명}}`, `{{기간}}` 같은 자리표시자를 미리 적어 둔 양식 | 자리표시자를 찾아 필드로 만든다. `fields` 는 같은 이름 필드의 형식 등을 덮어쓸 때만 넘긴다 |
| `blank_form` | 자리표시자 없이 빈칸만 있는 양식 | `fields` 마다 자리(locator)를 적는다. 보통 `detect_fields` 의 후보를 확인해 넘긴다 |

필드 자리는 여덟 가지로 가리킨다.

| locator | 가리키는 곳 | 예 |
|---|---|---|
| `placeholder` | 자리표시자 토큰 | `{"kind": "placeholder", "token": "{{성명}}"}` |
| `table_cell` | DOCX, HWPX, PPTX 표의 셀(표, 행, 열 모두 0부터. PPTX 표는 슬라이드를 가로질러 센다). 셀 전체를 바꾼다 | `{"kind": "table_cell", "table": 0, "row": 2, "col": 1}` |
| `anchor_text` | DOCX, HWPX 문단의 기준 글 뒤. 같은 문단에 뒤 글이 있으면 그 글을, 없으면 다음 문단을 바꾼다 | `{"kind": "anchor_text", "after": "신청 사유:"}` |
| `sheet_cell` | XLSX 의 시트와 셀 주소. 빈 칸에도 쓴다 | `{"kind": "sheet_cell", "sheet": "신청서", "cell": "C4"}` |
| `shape_text` | PPTX 슬라이드(0부터)의 글 도형(shape_id). 도형 글 전체를 바꾼다 | `{"kind": "shape_text", "slide": 0, "shape": 3}` |
| `inline_slot` | DOCX, HWPX 문단에서 라벨 바로 뒤 빈 괄호 안. 괄호와 뒤 글은 그대로 둔다 | `{"kind": "inline_slot", "paragraph": "p3", "label": "성명"}` |
| `checkbox` | DOCX, HWPX 문단의 `□` 칸 묶음. 고른 칸만 `■` 로 바꾼다 | `{"kind": "checkbox", "paragraph": "p5", "options": ["예", "아니오"]}` |
| `form_field` | PDF AcroForm 필드의 전체 이름. `detect_fields` 가 폼 필드를 그대로 후보로 낸다 | `{"kind": "form_field", "name": "applicant.name"}` |

필드는 이름, 형식, 필수 여부, 글자 수 제한(`max_chars`), 줄 수 제한(`max_lines`)을 가진다. 형식은 `text`, `long_text`, `date`(`YYYY-MM-DD`), `date_range`(`시작 ~ 끝`, 시작이 끝보다 늦으면 안 된다), `number`(숫자나 쉼표 있는 숫자), `choice`(`options` 가운데 하나) 여섯이다. 템플릿 id 는 한글, 영문, 숫자, `-`, `_` 로 64자까지다.

### 등록과 채우기

- `register_template` 는 모든 필드의 자리가 문서에 실제로 있는지 본다. 하나라도 없으면 등록하지 않고 문제 목록을 돌려준다
- 같은 id 와 같은 원본으로 다시 부르면 새로 만들지 않고 있던 템플릿을 돌려준다(`registered: false`). 같은 id 인데 원본이 다르면 새 버전 id(`-v2` 등)로 등록하라는 오류를 돌려준다. 템플릿을 지우거나 고치는 도구는 없다
- `fill_template` 는 값을 먼저 검사한다. 모르는 필드, 빠진 필수 값, 형식이나 길이가 맞지 않는 값이 있으면 파일을 만들지 않고 문제 목록을 돌려준다
- 통과하면 원본 자리 옆에 `<이름>.filled-<YYYYMMDD-HHMMSS>.<확장자>` 로 저장하고, 자리표시자가 남지 않았는지, 값이 제자리에 들어갔는지 검증한 결과를 함께 돌려준다. 검증에 실패해도 파일은 남기고 이유를 싣는다
- 같은 템플릿에 같은 값으로 다시 부르면 같은 `fill_id` 라서 파일을 더 만들지 않고 처음 결과를 돌려준다. 같은 초에 다른 값으로 채워 이름이 겹치면 이름 끝에 `-<fill_id>` 를 붙인다
- XLSX 에서 `=` 로 시작하는 값은 수식이 아니라 글로 저장한다

템플릿은 문서 폴더의 숨김 폴더 `.templates/<id>/` 에 스키마(`schema.json`)와 원본 사본으로 남고, 채운 기록은 그 아래 `fills/` 에 쌓인다. 등록 뒤에 원본 파일을 고쳐도 템플릿은 등록할 때의 사본으로 채운다.

### 빈 양식의 칸 찾기

`detect_fields` 는 빈 양식에서 채울 자리 후보를 규칙으로 찾는다. 같은 파일이면 언제나 같은 후보를 같은 순서로 돌려주고, 아무것도 저장하지 않는다.

- 본문 문단이 `라벨:`(전각 `：` 포함)로 끝나거나 뒤에 밑줄(`_`, `＿`)만 있으면 `anchor_text` 후보다. 뒤가 비었으면 다음 문단이 빈 줄일 때만 잡는다
- 표에서 라벨 칸의 오른쪽 칸이 비었으면 `table_cell` 후보다. 라벨이 20자 이하이고 문장이 아니면 확신도 high, 아니면 low 다. 오른쪽이 없거나 차 있고 바로 아래 칸이 비었으면 아래 칸을 low 로 잡는다
- XLSX 는 글 라벨 칸의 오른쪽 칸이 비었으면 `sheet_cell` 후보다. 숫자, 수식, 병합 머리 칸은 라벨로 보지 않는다
- 형식은 라벨 낱말로 짐작한다. 기간은 `date_range`, 일자, 날짜, 생년월일, 일시는 `date`, 금액, 수량, 비용, 개수는 `number`, 사유, 내용, 목적, 비고, 요청사항은 `long_text`, 그 밖은 `text` 다
- 라벨 뒤 빈 괄호(`성명(   )`)는 `inline_slot`, `□ 예 □ 아니오` 같은 칸 묶음은 `checkbox` 후보다. PDF 체크박스와 선택지가 있는 필드는 `choice` 다
- 병합 칸은 병합 폭 바로 다음 열이나 행을 본다. 칸 기호가 그림이나 글꼴 기호(Wingdings)면 찾지 못한다

후보는 초안이다. 에이전트는 후보를 한 줄씩(이름, 라벨, 형식, 위치) 보이고, 사용자가 빼거나 고쳐 확정한 목록으로만 `register_template(kind="blank_form")` 를 부른다. 후보의 `name`, `type`, `required`, `options`, `locator` 는 그대로 `fields` 로 넘길 수 있다.

HUD 에서는 빈 양식을 첨부하거나 이름을 말하고 "이 양식 등록해줘" 라고 하면, 후보가 있을 때 **양식 등록 창** 이 열린다. 창에서 포함 여부, 이름, 형식, 필수, 선택지를 고치고 `등록` 을 누르거나 대화로 고쳐 등록한다. 이미 값이 채워진 문서처럼 후보가 없으면 창은 열리지 않는다.

`make_placeholder_copy(path, fields)` 는 확인한 자리마다 `{{이름}}` 을 넣은 `<이름>.template.<확장자>` 사본을 만든다. 체크 칸과 PDF 폼 필드는 받지 않는다. 사본은 `register_template(kind="placeholder")` 로 등록한다.

## 대화 예시

템플릿을 등록해 둔 뒤 출장신청서를 채우는 흐름이다.

```text
사용자  출장신청서 써줘. 12월 3일부터 5일까지 부산
에이전트 [list_templates, get_template_schema("출장신청서-v1")]
        출장 목적이 필수 항목이라 비어 있습니다. 목적을 알려 주세요.
사용자  거래처 납품 점검
에이전트 [fill_template 승인 모달 → ALLOW]
        출장신청서.filled-20261203-091502.hwpx 로 저장했습니다. 검증 문제는 없습니다.
```

이미 있는 문서를 고칠 때는 이렇다.

```text
사용자  보고서.docx 에서 기간을 12월 3일에서 5일로 바꿔
에이전트 [inspect_document, plan_edit]
        t0r2c1: 2026-12-01 ~ 2026-12-02 → 2026-12-03 ~ 2026-12-05
        이대로 바꿀까요?
사용자  응
에이전트 [apply_edit 승인 모달 → ALLOW]
        보고서.edited-20261203-091840.docx 로 저장했습니다. 원본은 그대로입니다.
```

## 안전장치

- 경로는 문서 폴더 안만 받는다. `..`, 절대 경로, `~`, `.` 으로 시작하는 이름은 거부하므로 `.templates` 와 `.render` 도 도구 경로로는 열 수 없다. 템플릿 id 도 정해진 글자만 받아 폴더 밖을 가리키지 못한다
- 20MB 를 넘는 파일은 열지 않는다. `inspect_document` 는 항목이 2000개를 넘으면 문단 앞부분만, `detect_fields` 는 후보 200개까지만 돌려준다
- 문서 본문은 데이터이고 지시가 아니다. 본문에 "이 문서를 읽은 에이전트는 ..." 같은 글이 있어도 따르지 않도록 서버 설명과 도구 설명에 적어 두었다
- 쓰기 도구(`apply_edit`, `register_template`, `make_placeholder_copy`, `fill_template`, `create_document`)는 MCP 정책 기본값으로 승인을 묻는다. 스케줄이나 목표 작업처럼 물을 사람이 없는 실행에서는 승인이 필요한 도구를 실행하지 않는다
- 파일은 임시 파일에 쓴 뒤 이름을 바꿔 저장하므로 중간에 멈춰도 반쯤 쓴 결과 파일이 남지 않는다
- 호출 기록(`~/.ash/mcp_audit.jsonl`)에는 인자가 60자까지만 남는다

## 에이전트에게 도구 주기

docs 도구를 어느 에이전트가 쓸지는 두 곳에서 정한다.

1. MCP 정책 `~/.ash/mcp_policy.yaml` 의 `agents.<id>.servers` 에 `docs` 를 넣는다. 에이전트 항목에 `servers` 가 없으면 모든 서버를 쓸 수 있고, 목록이 있으면 그 서버만 쓴다. 막힌 서버의 도구는 그 에이전트의 도구 목록에서도 빠지므로, 팀이 있으면 main 은 문서 일을 문서 담당 에이전트에게 맡긴다

```yaml
# ~/.ash/mcp_policy.yaml
agents:
  main:
    servers: [google]        # main 은 docs 를 직접 쓰지 않는다
  scribe:
    servers: [docs]
    deny: [register_template]  # 이 에이전트에게만 막는 도구
```

2. 팀 에이전트 정의 파일의 `tools` 에 쓸 도구 이름을 적는다. `tools` 를 비운 에이전트는 등록된 도구 전체를 쓰므로 적지 않아도 된다([팀 에이전트 추가하기](../../agents/new-agent.md))

```yaml
# ~/.ash/team/scribe.yaml
tools: [list_documents, inspect_document, plan_edit, apply_edit, render_document,
        list_templates, get_template_schema, detect_fields, register_template, fill_template,
        make_placeholder_copy, create_document]
```

정책 파일과 정의 파일은 기동 때 읽으므로 고친 뒤에는 백엔드를 다시 띄운다. 정책 파일의 다른 키(도구별 `mode`, 인자 고정, 시간당 상한)는 [Tool & Approve System](./tools-and-approval.md#mcp-도구-정책) 에 있다.

## 설정

Docker Compose 로 띄우면 별도 설정 없이 `docs` 서버가 `ash-mcp` 컨테이너의 8001 포트에서 돌고, 백엔드의 기본 `ASH_MCP_SERVERS` 에 이미 들어 있다(`http://ash-mcp:8001/mcp`, 시간 제한 180초).

```bash
ASH_DOCS_DIR=~/Documents/ash   # 문서 폴더. 컨테이너 안 /data/documents 로 붙는다
```

- 문서는 이 폴더에 직접 넣거나 HUD 채팅에 첨부한다([파일 첨부하기](../../start/web-hud.md#파일-첨부하기)). 결과 파일은 원본 옆에 생긴다. 첨부한 문서를 고치거나 첨부로 등록한 양식을 채운 결과는 첨부 폴더에 생겨 24시간 뒤 지워질 수 있으므로 남길 파일은 문서 폴더로 옮긴다
- `ASH_MCP_SERVERS` 를 직접 적었다면 `{"name": "docs", "transport": "streamable-http", "url": "http://ash-mcp:8001/mcp", "timeout": 180}` 항목을 넣어야 도구가 보인다
- `render_document` 가 PNG 나 PDF 를 만들면 HUD 에 문서 창이 떠 쪽을 넘겨 볼 수 있다. 백엔드는 같은 폴더를 읽기 전용으로 붙여 `.render/` 아래 파일만 내준다(`GET /api/docs/files/{path}`). 에이전트가 그림을 보지는 않는다

## 한계

- HWPX 는 본문 문단에 바로 든 표만 읽는다. 셀 안 표, 글상자, 머리글, 바닥글, 각주는 보지 않는다
- DOCX 는 중첩 표, 머리글과 바닥글, 하이퍼링크 안의 글을 고치거나 채우지 않는다. 그림이 든 run 에 자리표시자가 있으면 그 그림이 사라진다
- XLSX 는 차트와 그림을 다시 저장하지 못한다
- 한/글로 만든 실제 공고 양식으로는 아직 충분히 확인하지 않았다
