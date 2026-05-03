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

### 0. 모드 결정 + Jira 가용성 + 프로젝트 키
사용자 인자에서 모드 추출(위 표). `ToolSearch` 로 `atlassian|jira` 검색해 MCP 도구 확인. 없으면 `JIRA_AVAILABLE=false`, 사용자에게 "MCP 미셋업, 로컬만 생성" 안내.

**Jira 프로젝트 키 결정** — 우선순위:
1. `--project-key <KEY>` 플래그
2. 해당 로컬 프로젝트의 `01_projects/<project>/.jira.json` 의 `project_key` 필드
3. 글로벌 기본값 `~/.claude/skills/wy-new-task/config.json` 의 `default_project_key`
4. 위 셋 다 없으면 사용자에게 묻고 글로벌 config 에 저장 (이후 재사용)

config 미존재 시 첫 인터뷰:
```
Atlassian Cloud 인스턴스 도메인? (예: cloud.jira.woowa.in)
기본 Jira 프로젝트 키? (예: REALTIMEOP, OPS, TEAM)
```
→ `~/.claude/skills/wy-new-task/config.json` 에 `{"jira_instance": "...", "default_project_key": "..."}` 저장.

이렇게 결정된 값을 `$JIRA_PROJECT_KEY` 로 보관 후 Step 3 에서 사용.

**파트(컴포넌트) 결정** — 우선순위:
1. `--part <NAME>` 플래그
2. `~/.claude/skills/wy-new-task/config.json` 의 `part`
3. `~/.claude/skills/wy-session-done/config.json` 의 `part` (재사용)
4. 사용자에게 묻고 wy-new-task config 에 저장 (이후 재사용)

값을 `$PART` 로 보관. Jira 이슈의 `components` 필드에 사용.

### 1. 메타 수집

**모드 A** — 인터뷰 (모든 신규는 타입 T = 테스크 고정):
1. 제목 (한글)
2. slug — Claude 가 제목에서 자동 변환(lowercase+hyphen) 후 그대로 사용 (확인 생략)
3. 프로젝트 — `ls 01_projects/` 후보 + "없음" 옵션. 신규는 `01_projects/<name>/` 자동 생성
4. 한 줄 골 (측정 가능)
5. **목표일자** (YYYY-MM-DD, 자연어 `+7d`/`next-week` 등 허용 → ISO로 정규화)
6. Jira 동시 생성? (Y/n) — MCP 가용+프로젝트 지정시 기본 Y

**모드 B** — 폴더 읽기:
- 폴더 정규화 → `brief.md`/`01_ask.md`, `goals.md` Read
- 메타 추출(타입=폴더 prefix — 기존 F-/S- 과제는 그대로 인식, 신규는 항상 T, slug=폴더명, 제목=brief 첫 H1, 골=goals.md 핵심)
- 이미 매핑됨(`Jira:` 또는 `[A-Z]+-\d+`) 있으면 종료(except `--force`)
- 프로젝트 추론 실패 시 사용자 묻기

**모드 C** — Jira 읽기:
- Atlassian MCP 로 issue 조회(summary/description/labels/parent epic/project key)
- 타입=항상 T (모든 신규는 테스크). Jira 라벨에 `analysis` 가 있어도 T로 생성 (기존 F 과제는 별도 수기 마이그레이션)
- slug=summary 한→영 변환 시도, 실패 시 입력
- 프로젝트=parent epic의 `.jira.json` 검색, 미매칭 시 묻기

**모드 D** — 직행 (Step 4-C 매핑 기록 후 종료).

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
