---
name: wy-weather
description: 우천 강도 표준화 — 구군 × 30분 슬롯 dBZ 기반 5단계 등급화. 비교 분석 표본 추출 / 전일자 우천 강한 지역 점검에 자연어로 호출. 자세한 동작·예시는 SKILL.md 본문에 정의됨.
user-invocable: true
---

# wy-weather — 우천 강도 표준화

## 트리거 (자연어)

다음 표현이 보이면 본 스킬 호출:
- "우천 강도", "기상 강도", "비 강한 지역", "전일자 우천", "어제 비"
- "기상 비교", "같은 비 온 날", "기상 표본", "find_similar"
- "weather_intensity", "intensity_level"

## 무엇을 하나

특정 기간·지역·시간대의 비 온 정도를 **5단계 등급**으로 표준화하고, 동일 기상조건의 다른 시점 슬롯을 자동 매칭한다.

- 격자: 구군(`pickup_rgn1_nm` × `pickup_rgn2_nm`) × 30분 슬롯
- 시간: 운영시간 06:00~27:00 (KST 06시 기준 영업일, 새벽은 24~27시 표기)
- 강도 정의: **선형 Z 평균** `10·log10(mean(10^(dBZ/10)))`
- 등급: L0 NONE / L1 LIGHT / L2 LIGHT-MODERATE / L3 MODERATE / L4 HEAVY / L5 EXTREME (임계 25/30/40/50/55 dBZ)

## 첫 사용 — 셋업

Trino 인증이 필요하다. 처음 호출 시 자동 setup wizard 진입:

```bash
bash $SKILL_DIR/scripts/setup.sh
```

생성 위치: `~/.config/wy-weather/config.env` (chmod 600)

setup이 묻는 것:
1. Trino `.env` 파일 경로 (자동 탐색 후보 제시 + 직접 입력 가능)
   - 그 파일에 `RTO_TRINO_USER` / `RTO_TRINO_PASS` 가 있으면 OK
2. 또는 `RTO_TRINO_USER` / `RTO_TRINO_PASS` 직접 입력

이미 setup 됐으면 스킵.

## 사용법

### A) CLI (단발 점검)

```bash
bash $SKILL_DIR/scripts/run.sh 2025-08-19 2025-08-19 --top 10
bash $SKILL_DIR/scripts/run.sh 2025-07-01 2025-07-31 --start 11:00 --end 13:00 --top 5 --group-by part_date -o jul_lunch.csv
```

### B) 분석 노트북에서 import

```python
import sys
sys.path.insert(0, "/Users/<user>/.claude/plugins/marketplaces/wy-task-mgmt/skills/wy-weather/lib")
from weather_intensity import fetch, top_severe, find_similar

ref = fetch("2025-07-17", "2025-07-17", "11:00", "13:00")
ref_target = ref[ref["pickup_rgn2_nm"] == "강남구"]

pool = fetch("2025-07-01", "2025-07-31", "11:00", "13:00")
matched = find_similar(ref_target, pool, dbz_tolerance=2.0)
```

## 핵심 결정 사항 (요약)

- **dBZ 평균 = 선형 Z 평균** (산술평균 금지 — 강한 hex가 약한 hex에 희석됨)
- **두 단계 평균**: H3 hex × 분 raw → hex × 30분 슬롯 (SQL) → 구군 × 슬롯 (Python)
- **강수 컷오프 dBZ ≥ 25** — 그 미만 hex는 노이즈로 카운트 안 함
- **태풍 / 뇌우 격상 없음** — 강도 충분히 크면 dBZ만으로 L4/L5에 잡힘. 태풍은 풍속 데이터 부재로 별도 사안
- **강수 0인 슬롯은 결과에서 제외** — dense 분석 필요 시 운영 timeline frame과 left join

## 출력 스키마

`(part_date, timeline, pickup_rgn1_nm, pickup_rgn2_nm)` 4-key + `mean_dbz_when_rain`, `precip_coverage`, `weighted_dbz`, `intensity_level`(0~5), `intensity_label`, `dominant_precip_type`, `precip_hex_count`, `total_hex_count`, …

→ 4-key로 `weather_fee` / RPI / 60분초과율 등 운영지표와 직접 join.

## 폴더 구조

```
wy-weather/
├── SKILL.md                          ← 본 문서
├── lib/                              ← self-contained 모듈
│   ├── weather_intensity.py          (메인: fetch + top_severe + find_similar + CLI)
│   ├── trino_client.py
│   ├── sql_loader.py
│   ├── sql/weather_intensity_district.sql
│   └── data/h3_district_map.json
└── scripts/
    ├── setup.sh                      ← config.env wizard (Phase 3-2)
    └── run.sh                        ← config.env source → python lib/weather_intensity.py
```

## 관련 자료

- 위키: https://woowahanbros.atlassian.net/wiki/spaces/REALTIMEOP/pages/1127191985
- 과제: F-2026-0506-001
- 운영효율화파트 통합 README의 "1. 참조 자료 / 02.기상" 섹션
