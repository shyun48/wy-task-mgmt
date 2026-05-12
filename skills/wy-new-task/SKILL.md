---
name: wy-new-task
description: 신규 과제 폴더 + Jira 티켓을 한 번에 생성. 폴더만 있으면 Jira 발급(역방향), Jira만 있으면 폴더 스캐폴드(정방향), 둘 다 있으면 매핑만 등록(복구). Atlassian MCP 미셋업 시 Jira 단계 자동 스킵. /wy-new-task 호출 시 사용.
user-invocable: true
argument-hint: "[<폴더경로>|<JIRA-KEY>|--no-jira|--project-key <KEY>|--due <YYYY-MM-DD>|--part <NAME>] [<제목>]"
---

# wy-new-task

신규 과제와 Jira 티켓 생성/매핑.

## 4가지 모드

| 모드 | 트리거 | 동작 |
|------|--------|------|
| **A 신규** | 인자 없음 (또는 현재 dir 비어있음) | 인터뷰 → 폴더 + Jira → 매핑 |
| **B 역방향** | 폴더 경로 / `02_analyses/...`/`03_tasks/...` 시작 / 현재 dir에 brief.md | 폴더 읽어 Jira 발급 |
| **C 정방향** | `--from-jira <KEY>` 또는 `[A-Z]+-\d+` 패턴 | Jira 읽어 폴더 스캐폴드 |
| **D 복구** | 폴더 경로 + Jira 키 동시 | 매핑만 등록 |

`--no-jira` 플래그 → 모드 무관 Jira 단계 스킵.

## 절차

> ⚠️ **인터뷰 원칙 (모든 호출에 동일 적용)**
> 사용자에게 묻는 모든 질문은 본 문서 끝의 `## 인터뷰 대본 (verbatim)` 의 **문구 그대로** 사용한다.
> - 한 번에 **하나씩**, 명시된 **순서대로** 묻는다.
> - 두 질문을 합치거나 "한꺼번에 알려주세요" 식으로 묻지 않는다.
> - 즉흥 재작성·요약·다국어 번역 금지. 한글 그대로.
> - 각 질문의 스킵 조건이 충족되면 그 질문만 건너뛴다. 그 외 질문은 항상 묻는다.
> - 마지막에 Q-FINAL (요약 확인)은 모든 모드에서 1회 필수.

### 0. 모드 결정 + Jira 가용성 + 프로젝트 키
사용자 인자에서 모드 추출(위 표). `ToolSearch` 로 `atlassian|jira` 검색해 MCP 도구 확인. 없으면 `JIRA_AVAILABLE=false`, 사용자에게 "MCP 미셋업, 로컬만 생성" 안내.

**Jira 프로젝트 키 결정** — 우선순위:
1. `--project-key <KEY>` 플래그
2. 해당 로컬 프로젝트의 `01_projects/<project>/.jira.json` 의 `project_key` 필드
3. 글로벌 기본값 `~/.claude/skills/wy-new-task/config.json` 의 `default_project_key`
4. 위 셋 다 없으면 → **Q1, Q2** (대본 그대로) 묻고 `~/.claude/skills/wy-new-task/config.json` 에 `{"jira_instance": "...", "default_project_key": "..."}` 저장

결정된 값을 `$JIRA_PROJECT_KEY` 로 보관 후 Step 3 에서 사용.

**파트(컴포넌트) 결정** — 우선순위:
1. `--part <NAME>` 플래그
2. `~/.claude/skills/wy-new-task/config.json` 의 `part`
3. `~/.claude/skills/wy-session-done/config.json` 의 `part` (재사용)
4. 위 셋 다 없으면 → **Q3** (대본 그대로) 묻고 wy-new-task config 에 저장

값을 `$PART` 로 보관. Jira 이슈의 `components` 필드에 사용.

### 1. 메타 수집

**모드 A** — 인터뷰 (모든 신규는 타입 T = 테스크 고정).
대본의 **Q4 → Q5 → Q6 → Q7 → Q8** 순서로 묻는다 (각 Q 의 스킵 조건 존중). slug 는 Q4 답변(제목)에서 자동 변환(lowercase+hyphen)으로 생성, 별도 질문하지 않음.

**모드 B** — 폴더 읽기:
- 폴더 정규화 → `brief.md`/`01_ask.md`, `goals.md` Read
- 메타 추출(타입=폴더 prefix — 기존 F-/S- 과제는 그대로 인식, 신규는 항상 T, slug=폴더명, 제목=brief 첫 H1, 골=goals.md 핵심)
- 이미 매핑됨(`Jira:` 또는 `[A-Z]+-\d+`) 있으면 종료(except `--force`)
- 프로젝트 추론 실패 시 → **Q5** 그대로 묻기

**모드 C** — Jira 읽기:
- Atlassian MCP 로 issue 조회(summary/description/labels/parent epic/project key)
- 타입=항상 T (모든 신규는 테스크). Jira 라벨에 `analysis` 가 있어도 T로 생성 (기존 F 과제는 별도 수기 마이그레이션)
- slug=summary 한→영 변환 시도, 실패 시 사용자 입력(이때도 별도 Q 신설 금지 — 한 줄로 "영문(자동) 값을 입력해주세요" 만)
- 프로젝트=parent epic의 `.jira.json` 검색, 미매칭 시 → **Q5** 그대로 묻기
- Jira 의 `duedate` 비어있으면 → **Q7** 그대로 묻기

**모드 D** — 직행 (Step 4-C 매핑 기록 후 종료, 인터뷰 없음 — Q-FINAL 만 실행).

### 2. 폴더 생성 (모드 A/C)

```bash
${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills/..}/skills/wy-new-task/scripts/create_task.py \
  --type T --title "<제목>" --slug "<slug>" \
  --project "<project|''>" --goal "<골>" \
  --local-root "<local_root>" --mode "<A|C>" \
  ${DUE_DATE:+--due-date "$DUE_DATE"} \
  ${PART:+--part "$PART"} \
  ${JIRA_KEY:+--from-jira "$JIRA_KEY"}
```

스크립트가 ID 발급(`{F|S|T}-YYYY-MMDD-NNN`, NNN=같은 날짜 최대치+1) → 폴더 스캐폴드(brief|01_ask, goals, progress, phases/01_initial, handoffs/) → registry.md + 프로젝트 registry.md 행 삽입 → JSON stdout. JSON 파싱해 `$TASK_ID` `$TASK_DIR` 보관.

### 3. Jira 발급 (모드 A/B/C, JIRA_AVAILABLE && 프로젝트 지정)

**3-A. 프로젝트 Epic 확인/생성**
`01_projects/<project>/.jira.json` 의 `epic_key` 사용. 없으면 Atlassian MCP `create_issue` 로 Epic 생성:
- project_key=${JIRA_PROJECT_KEY}, issue_type=Epic
- summary=프로젝트 한글명, labels=`["wy-task-mgmt","auto-generated"]`

성공 시 `.jira.json` 저장: `{"epic_key": "...", "project": "...", "created_at": "..."}`.

**3-B. Issue 생성 (Epic 하위)**
- project_key=${JIRA_PROJECT_KEY}, issue_type=Task, parent=epic_key
- summary=과제 한글 제목, description=골+brief 발췌
- duedate=`$DUE_DATE` (ISO 8601, 있을 때만)
- components=`[{"name": "$PART"}]` (있을 때만 — 컴포넌트가 프로젝트에 미리 등록되어 있어야 함, 없으면 사용자에게 안내)
- labels=`["wy-task-mgmt", "task", "<project>"]`

issue_key, issue_url 확보.

**3-C. 매핑 기록**
- `brief.md`/`01_ask.md` 최상단:
  ```
  > **Jira**: [{key}]({url})
  > **Epic**: [{epic_key}](...)
  ```
- `registry.md` 의 해당 행 Jira 컬럼에 `[키](URL)` 추가

### 4. 마무리

```
✓ 생성 완료
  ID:    <task_id>
  경로:  <task_dir>
  프로젝트: <project|(없음)>
  Jira:  <키+URL|(생성 안 함)>
```

모드 A/C → "deep-interview 들어갈까요?" → Y면 deep-interview 호출.
이후 `/wy-goal-loop <폴더>` 로 진입 가능.

## 주의
- 폴더/slug 영문만. 한글은 brief.md/registry "이름" 컬럼.
- **부모 디렉토리는 항상 복수**: `01_projects/`, `02_analyses/`, `03_tasks/`, `04_docs/`. 단수 폴더(`01_project` 등) 절대 생성 금지.
- Jira 프로젝트 키는 `--project-key` > `.jira.json` > 글로벌 config > 첫 인터뷰 순으로 해결. 첫 인터뷰 결과는 `~/.claude/skills/wy-new-task/config.json` 에 저장되어 재사용.
- 자동 추측 금지(프로젝트 추론은 항상 사용자 확인). slug 는 한글 제목에서 자동 변환.
- 모드 시작 시 폴더↔registry↔Jira 일관성 체크. 끊긴 거 발견하면 묻고 복구.

## 실패 시
- registry.md 부재 → CLAUDE.md 워크스페이스 셋업 안내
- MCP 호출 실패 → 에러 노출, Jira 단계만 롤백(로컬 폴더 유지). 추후 모드 B 재발급 가능
- ID 충돌 → NNN+1 자동 재시도(3회)

## 인터뷰 대본 (verbatim)

**규칙 (반드시 준수)**:
- 아래 질문 문구를 **그대로** 사용한다. 변형·축약·번역·합치기 금지.
- **순서대로 한 번에 하나씩** 묻는다.
- 스킵 조건이 충족된 질문만 건너뛴다.
- 사용자 답변은 짧게 요약(quote) 후 다음 질문으로 진행. 답변을 받기 전엔 다음 질문 노출 금지.
- 마지막 Q-FINAL (요약 확인)은 모든 모드에서 필수.

### Q1. Jira 인스턴스 도메인
- 스킵: `~/.claude/skills/wy-new-task/config.json` 의 `jira_instance` 존재, **또는** `--no-jira` 플래그
- 적용 모드: A / B / C (글로벌 1회 인터뷰)

```
Jira(Atlassian Cloud) 인스턴스 도메인을 알려주세요.
예) cloud.jira.woowa.in
```

### Q2. 기본 Jira 프로젝트 키
- 스킵: `--project-key` 플래그 / `01_projects/<project>/.jira.json` 의 `project_key` / 글로벌 config `default_project_key` 중 하나라도 있음, **또는** `--no-jira`
- 적용 모드: A / B / C

```
기본 Jira 프로젝트 키를 알려주세요.
예) REALTIMEOP, OPS, TEAM
```

### Q3. 파트(Jira 컴포넌트)
- 스킵: `--part` 플래그 / `wy-new-task/config.json`·`wy-session-done/config.json` 의 `part` 중 하나라도 있음, **또는** `--no-jira`
- 적용 모드: A / B / C

```
파트(Jira 컴포넌트) 이름을 알려주세요.
Jira 프로젝트에 등록된 component 명과 정확히 일치해야 합니다.
```

### Q4. 과제 한글 제목
- 스킵 없음 (모드 A 만 — 모드 B 는 `brief.md` H1, 모드 C 는 Jira summary 사용)
- 적용 모드: A

```
과제 한글 제목을 적어주세요.
```

### Q5. 프로젝트 (폴더)
- 스킵 없음 (모드 A 만)
- 적용 모드: A

선택지는 실제 `01_projects/` 스캔 결과로 채운다. 후보 0개여도 `[N] 신규 입력`, `[없음] 루트` 옵션은 항상 노출.

```
어느 프로젝트 하위로 둘까요?
  [1] {project_1}
  [2] {project_2}
  ...
  [N] 신규 입력
  [없음] 루트(프로젝트 없이)
선택:
```

### Q6. 한 줄 골 (측정 가능)
- 스킵 없음 (모드 A 만)
- 적용 모드: A

```
한 줄로 측정 가능한 골을 적어주세요.
예) "긴급 미션 발동률을 현재 12% → 5% 로 낮춘다"
```

### Q7. 목표일자
- 스킵: `--due <YYYY-MM-DD>` 플래그
- 적용 모드: A (모드 C 에서 Jira 에 `duedate` 가 없을 때도 묻는다)

```
목표일자를 적어주세요. (YYYY-MM-DD, 또는 +7d / next-week 등 자연어 허용 — ISO 로 정규화)
```

### Q8. Jira 동시 발급 여부
- 스킵: `--no-jira` 플래그 / MCP 미가용 / `$JIRA_PROJECT_KEY` 미정 중 하나라도 해당 → 자동 "n"
- 적용 모드: A

```
Jira 티켓도 같이 발급할까요? (Y/n, 기본 Y)
```

### Q-FINAL. 요약 확인 (항상 마지막, 모든 모드)
실제 값으로 슬롯을 채워 그대로 출력. 값이 비어있으면 `(없음)`.

```
다음 내용으로 진행할까요?
  제목:          {title}
  영문(자동):     {slug_auto}
  프로젝트:       {project|(없음)}
  골:            {goal}
  목표일자:       {due_date|(미지정)}
  파트:          {part|(없음)}
  Jira 발급:      {Y|n}
  Jira 프로젝트:   {JIRA_PROJECT_KEY|(없음)}
(Y/n)
```

n 응답 시 어떤 항목을 고칠지 한 번 더 묻고, 해당 Q 만 재호출. Y 면 Step 2 진행.
