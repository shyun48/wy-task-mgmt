# Changelog

## v0.10.0 — 2026-05-12

### Added
- **`/wy-session-done` Jira 연동**: 세션 종료 시 활성 과제 Jira 티켓에 세션 요약 댓글 자동 등록 (선택).
  - 댓글 본문: handoff `이번 세션 요약` + `다음 세션 진입 시`, phase-done 일 땐 `페이즈 종료 요약` 추가.
  - Jira 키 추출: `brief.md` / `01_ask.md` 상단 마커 → `registry.md` 폴백.
  - 트리거 기본 켜짐, 매번 사용자에게 `(Y/n)` 확인. `--no-jira` 플래그로 강제 스킵.
  - phase-done 한정으로 `jira_get_transitions` 결과 보여주고 상태 전환 여부 사용자 선택.
  - MCP 미가용 / 매핑 없음 / 호출 실패 시 안내만 하고 Drive 동기화는 정상 진행.

### Changed
- **`/wy-new-task` 인터뷰 락다운**: 호출마다 문구가 달라지던 인터뷰를 `## 인터뷰 대본 (verbatim)` 섹션으로 고정.
  - Q1~Q8 + Q-FINAL 의 한글 문구를 SKILL.md 에 verbatim 으로 박아 즉흥 재작성 금지.
  - Step 0/1 본문은 "Q번호" 로 참조만 하도록 단순화 — 단일 출처 보장.
  - 스킵 조건(플래그/config 캐시)을 각 Q 옆에 명시. 모드 A/B/C 진입 시 어느 Q 가 추가로 묻는지 명시.

## v0.9.1 — 2026-05-08

### Fixed
- `wy-weather`: `raw_log.log_ts` 가 KST 로 동작함이 Redash 검증으로 확인됨 → 모든 `+ INTERVAL '9' HOUR` 변환 제거.
  - SQL: `log_ts AS kst_ts`, `HOUR(log_ts)`, `MINUTE(log_ts)` 직접 사용
  - Python: raw period 계산을 영업일 KST 기준 `[start 06:00, end+1 06:00)` 으로 변경
  - 이전 결과는 9시간 미래로 시프트되었으므로 v0.9.0 결과 재검증 필요

## v0.9.0 — 2026-05-07

### Added
- **`/wy-weather` 스킬**: 우천 강도 표준화 (구군 × 30분 슬롯 dBZ 기반 5단계 등급화)
  - 핵심 함수: `fetch`, `top_severe`, `find_similar`
  - CLI + import 두 가지 사용법 (`scripts/run.sh` / `lib/weather_intensity.py`)
  - 첫 셋업 wizard: `scripts/setup.sh` → `~/.config/wy-weather/config.env` (인증값 미저장, .env 경로 + 키 이름만)
  - self-contained `lib/`: `weather_intensity.py`, `trino_client.py`, `sql_loader.py`, `sql/`, `data/h3_district_map.json` (172개 구군)
  - 5단계 등급: NONE/LIGHT/LIGHT-MODERATE/MODERATE/HEAVY/EXTREME (임계 25/30/40/50/55 dBZ)
  - 운영 영업일 KST 06:00 기준, 운영시간 06:00~27:00 (24+ 표기)
  - 4-key (`part_date`, `timeline`, `pickup_rgn1_nm`, `pickup_rgn2_nm`) 로 운영지표(weather_fee 등) 직접 join 가능

### Notes
- 관련 위키: https://woowahanbros.atlassian.net/wiki/spaces/REALTIMEOP/pages/1127191985
- 관련 과제: F-2026-0506-001

## v0.8.7 — 이전

`/wy-new-task` type T 통일.

## v0.8.6

목표일자 + 파트(Jira component) 추가.

## v0.8.5

`/clear` 안내 + 폴더명 복수 가드.
