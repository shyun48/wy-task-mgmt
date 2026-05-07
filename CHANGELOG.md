# Changelog

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
