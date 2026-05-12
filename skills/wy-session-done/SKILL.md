---
name: wy-session-done
description: 세션 종료 시 활성 과제의 progress/phase/handoff MD 갱신 + 클라우드 동기화 폴더 미러링 + (선택) Jira 댓글에 세션 요약 append. 페이즈 종료/단순 세션 종료 모드. 최초 1회 셋업(사용자명+Drive 경로) 필요. /wy-session-done 호출 시 사용.
argument-hint: "[--no-jira]"
---

# wy-session-done

세션 마무리 → progress.md / 현재 페이즈 MD / handoffs/<ts>.md 갱신 → Drive 미러링.

**트리거**: `/wy-session-done`, "세션 종료", "오늘 작업 마무리", "Drive에 정리해줘"

## 절차

### 0. 셋업 확인
```bash
test -f ~/.claude/skills/wy-session-done/config.json
```
없으면 → **Step 1**. 있으면 → **Step 2**.

### 1. 셋업 인터뷰 (1회)
사용자에게 다음을 묻고 setup.py 실행:
- `user_name`: Drive에 표시될 본인 이름 (자유 형식)
- `drive_root`: 클라우드 동기화 폴더 절대경로. 후보 자동 감지: `ls ~/Library/CloudStorage/`
- `local_root`: 워크스페이스 루트 (기본 = 현재 디렉토리)

```bash
"$(command -v python3 || command -v python)" ${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills/..}/skills/wy-session-done/scripts/setup.py \
  --drive-root '<...>' --user-name '<...>' --local-root '<...>'
```

### 2. 활성 과제 감지
**우선**: 사용자 입력에서 폴더경로/과제ID/슬러그 추출 → registry.md 매칭.
**자동**: registry.md 의 활성 행 추출. 0개=종료 / 1개=자동 / 다중=mtime 순으로 사용자 선택. 한글 이름 + 영문 경로 함께 표시.

선택된 폴더를 `$TASK_DIR`.

### 3. 종료 유형
```
[1] 페이즈 종료 — 현재 페이즈 마무리 + 다음 페이즈 신규
[2] 단순 세션 종료 — 현재 페이즈에 진행분만 append
```

### 4. 폴더 구조 점검
없으면 templates 기반 생성: `progress.md`, `phases/01_initial.md`, `handoffs/`. `phases/` 의 가장 큰 번호 = 현재 페이즈.

### 5-A. 페이즈 종료 처리
1. 현재 페이즈 MD 의 `## 페이즈 종료 요약` 채움(결과/한계/다음 컨텍스트), 상단 상태 → `completed`
2. 다음 페이즈 초안 제시(이름·목표·체크리스트 2~3개) → 사용자 확인 → `phases/0(N+1)_<slug>.md` 생성
3. progress.md 갱신: 활성 페이즈 / 페이즈 진행도 / 최종 갱신 / 다음 할 일
4. `handoffs/<YYYY-MMDD-HHMM>.md` 생성 (`{{END_TYPE}}=phase-done`)

### 5-B. 단순 세션 종료
1. 현재 페이즈 `## 세션 로그`에 오늘 항목 append (한 일/이슈/다음)
2. progress.md 갱신 (최종 갱신 / 다음 할 일 / 최근 핸드오프)
3. `handoffs/<YYYY-MMDD-HHMM>.md` 생성 (`{{END_TYPE}}=session-done`)

### 6. registry.md 갱신
해당 행 `최종 갱신`/`상태` 컬럼 업데이트.

### 7. Jira 댓글 갱신 (선택)

`--no-jira` 플래그면 전체 스킵. 그 외엔 다음 순서로 진행.

**7-A. Jira 키 추출**
1. `brief.md` 또는 `01_ask.md` 상단의 `> **Jira**: [<KEY>](<URL>)` 마커에서 `[A-Z]+-\d+` 추출
2. 없으면 `registry.md` 의 현재 과제 행 Jira 컬럼에서 추출
3. 그래도 없으면 안내 후 스킵: `Jira 매핑 없음 — /wy-new-task <폴더경로> 로 발급 가능`

`$JIRA_KEY` 보관.

**7-B. MCP 가용성 확인**
`ToolSearch` 로 `atlassian|jira` 검색 → `jira_add_comment` 도구 존재 확인. 없으면 안내 후 스킵.

**7-C. 사용자 확인**
```
🪪 Jira <JIRA_KEY> 에 세션 요약을 댓글로 남길까요? (Y/n)
```
n → 스킵하고 Step 8 으로.

**7-D. 댓글 본문 빌드**
방금 작성한 `handoffs/<ts>.md` 와 (phase-done 경우) 현재 페이즈 MD 에서 발췌:

```markdown
### 🗒️ 세션 종료 — {YYYY-MM-DD HH:MM KST} · {phase-done|session-done}

**과제**: {TASK_ID} {TASK_SLUG} · 페이즈 {PHASE_NUM} {PHASE_NAME}

#### 이번 세션 요약
{handoff "## 이번 세션 요약" 본문}

#### 다음 세션 진입 시
{handoff "## 다음 세션 진입 시" 본문}

<!-- phase-done 일 때만 아래 블록 추가 -->
#### 페이즈 종료 요약 — 페이즈 {PHASE_NUM}
{phase MD "## 페이즈 종료 요약" 본문}

---
_wy-session-done · handoffs/{HANDOFF_FILE}_
```

빈 섹션(placeholder 만 있는 경우)은 출력 생략. 5KB 초과 시 본문 잘라내고 `(이하 생략 — handoff 파일 참조)` 표기.

**7-E. 댓글 등록**
MCP `jira_add_comment(issue_key=$JIRA_KEY, comment=<본문>)` 호출. 실패해도 Step 8 진행, 결과 리포트에 노출.

**7-F. 상태 전환 (phase-done 한정)**
session-done 이면 스킵. phase-done 이면:
1. `jira_get_transitions(issue_key=$JIRA_KEY)` → 가능 transition 목록 출력
2. 사용자 프롬프트:
   ```
   현재 페이즈 종료 — Jira 상태 전환할까요?
     [1] To Do → In Progress  …
     [2] In Progress → Done   …
     [n] 스킵
   선택:
   ```
3. 번호 선택 시 `jira_transition_issue(issue_key, transition_id)` 호출
4. 사용자 묵묵부답/`n` → 스킵

### 8. 동기화
```bash
SD=${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills/..}/skills/wy-session-done/scripts
FILE_LIST=$(mktemp)  # 변경 MD 절대경로 줄단위 기록
"$(command -v python3 || command -v python)" "$SD/secret_scan.py" "$FILE_LIST"   # exit≠0 → 중단, 정리 후 재시도
"$(command -v python3 || command -v python)" "$SD/sync.py" --dry-run             # 미리보기 후 사용자 확인
"$(command -v python3 || command -v python)" "$SD/sync.py"                       # 실제 동기화
```

결과 리포트: 종료유형 / 과제(한글이름) / 페이즈 / 로컬 갱신 / **Jira 댓글·transition** / Drive 업로드·충돌 / Drive 위치.

### 9. /clear 안내 (마무리)
세션 종료가 끝났으니 다음 세션을 깨끗하게 시작하기 위해 사용자에게 안내:
```
세션 종료 + 동기화 완료. 이어서 새 작업을 시작하려면 `/clear` 입력 후 `/wy-session-resume` 으로 컨텍스트 회복하세요.
```
사용자가 추가 작업 의사 보이면 `/clear` 권유 보류, 그렇지 않으면 권유.

## 주의
- 폴더/slug 영문만(한글 이름은 registry "이름" 컬럼). macOS NFD/Drive 호환.
- 단방향(로컬→Drive). Drive쪽 mtime 최신이면 `.drive-conflict-<ts>.md` 백업.
- whitelist `*.md` 만 업로드. `out/ bak/ credentials/ .omc/ venv/ __pycache__/ .pytest_cache/` 강제 제외.
- 민감정보 자동 redaction 안 함. secret_scan 차단 시 사용자가 정리.
- 시간은 KST.
- Jira 단계는 **선택**. 매핑 없음 / MCP 미가용 / 사용자 거절 / 호출 실패 어떤 경우든 Drive 동기화는 계속 진행.
- Jira 댓글에 민감정보가 들어가지 않도록 handoff "이번 세션 요약"에 secret 키워드를 적지 말 것. secret_scan 은 Drive 업로드만 게이트하고 Jira 댓글은 검사하지 않음.
- transition 은 **phase-done 일 때만** 묻고, 사용자가 명시적으로 번호 선택해야만 실행. session-done 에선 절대 transition 호출 금지.
