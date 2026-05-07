"""weather_intensity.py — 구군 × 30분 슬롯 우천 강도 표준화 + 분석 워크플로우 (단일 파일)

용도:
    1) fetch        : 기간/운영시간 → 강도 DataFrame (구군×30분 슬롯)
    2) top_severe   : 우천 강한 슬롯/지역 상위 K개 추출 (전일자 점검 등)
    3) find_similar : 기준 슬롯과 동일 기상조건 슬롯 후보 매칭 (비교 분석 표본 추출)

import 사용:
    from utils.weather_intensity import fetch, top_severe, find_similar

    # 사건 발생일의 점심 피크 강도
    ref = fetch("2025-07-17", "2025-07-17", "11:00", "13:00")
    ref_gangnam = ref[ref["pickup_rgn2_nm"] == "강남구"]

    # 같은 기상 조건의 다른 날 표본 (대조군)
    pool = fetch("2025-07-01", "2025-07-31", "11:00", "13:00")
    matched = find_similar(ref_gangnam, pool)
    # → (part_date, timeline, pickup_rgn1_nm, pickup_rgn2_nm) 키로 운영지표 left join 분석

CLI:
    # 어제 우천 강한 지역 top 10
    python weather_intensity.py 2025-08-19 2025-08-19 --top 10

    # 한 달 디너+심야(18:00~26:00) 일별 top 5
    python weather_intensity.py 2025-07-01 2025-07-31 --start 18:00 --end 26:00 \\
                                --top 5 --group-by part_date -o jul_dinner_top.csv

산출 컬럼:
    part_date, timeline, pickup_rgn1_nm, pickup_rgn2_nm,
    mean_dbz_when_rain, precip_coverage, weighted_dbz,
    mean_dbz_linear, mean_dbz_arith, max_dbz,
    intensity_level (0~5), intensity_label (NONE/LIGHT/.../EXTREME),
    dominant_precip_type, precip_hex_count, total_hex_count

NOTE:
    - 강수 0인 (구군, 슬롯)은 결과에서 제외됨. 운영 timeline frame에 left join으로 채울 것.
    - 시간 입력은 운영 표기(06:00~27:00). 새벽 0~3시는 24~27시로.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trino_client import fetch_weather_intensity_district


# ── 1) fetch: 얇은 래퍼 (분석 노트북 단축용) ─────────────────────

def fetch(start_date, end_date, start_time="06:00", end_time="27:00"):
    """기간 + 운영시간 → 우천 강도 DataFrame (구군 × 30분 슬롯)."""
    return fetch_weather_intensity_district(start_date, end_date, start_time, end_time)


# ── 2) top_severe: 강도 상위 K ────────────────────────────────────

_VALID_SORT_COLS = {
    "weighted_dbz", "mean_dbz_when_rain", "precip_coverage",
    "max_dbz", "mean_dbz_linear", "intensity_level",
}


def top_severe(df, n=10, by="weighted_dbz", group_by=None):
    """강도 상위 K 슬롯 추출.

    Args:
        df: fetch() 결과
        n: 상위 K개
        by: 정렬 기준 컬럼 (weighted_dbz | mean_dbz_when_rain | precip_coverage | max_dbz | ...)
        group_by: 그룹별 top-N (str 또는 list, 예: 'part_date', ['part_date','pickup_rgn1_nm'])
                  None이면 전체에서 top-N
    """
    if df.empty:
        return df
    if by not in _VALID_SORT_COLS:
        raise ValueError(f"by는 {sorted(_VALID_SORT_COLS)} 중 하나여야 합니다: {by!r}")

    if group_by is None:
        return df.sort_values(by, ascending=False).head(n).reset_index(drop=True)

    keys = [group_by] if isinstance(group_by, str) else list(group_by)
    return (
        df.sort_values(keys + [by], ascending=[True] * len(keys) + [False])
          .groupby(keys, sort=False).head(n).reset_index(drop=True)
    )


# ── 3) find_similar: 동일 기상조건 슬롯 매칭 ──────────────────────

def find_similar(reference, candidate,
                 match_cols=("intensity_level", "timeline", "pickup_rgn2_nm"),
                 dbz_tolerance=None):
    """기준(reference) 슬롯들과 동일 기상조건의 후보(candidate) 슬롯 찾기.

    비교 분석에서 "같은 비가 온 다른 날" 표본을 만들 때 사용.

    Args:
        reference: 기준 DataFrame (특정 날짜·지역의 사건 슬롯들)
        candidate: 매칭 후보 DataFrame (다른 기간 슬롯들)
        match_cols: 동일해야 할 컬럼 (기본: 등급 + 시간대 + 구)
                    예: ('intensity_level',) 만 두면 등급만 동일 → 표본 풀 넓어짐
        dbz_tolerance: None이면 등급만 일치 검사. 실수면 mean_dbz_when_rain 차이 이내 추가 필터

    Returns:
        DataFrame: candidate 중 매칭된 슬롯들. 원본 컬럼 유지.
    """
    if reference.empty or candidate.empty:
        return candidate.iloc[0:0]

    cols = list(match_cols)
    missing = [c for c in cols if c not in reference.columns or c not in candidate.columns]
    if missing:
        raise ValueError(f"match_cols 누락 컬럼: {missing}")

    ref_keys = (
        reference[cols + ["mean_dbz_when_rain"]]
        .rename(columns={"mean_dbz_when_rain": "_ref_dbz"})
        .drop_duplicates(cols)
    )
    out = candidate.merge(ref_keys, on=cols, how="inner")
    if dbz_tolerance is not None:
        out = out[(out["mean_dbz_when_rain"] - out["_ref_dbz"]).abs() <= float(dbz_tolerance)]
    return out.drop(columns=["_ref_dbz"]).reset_index(drop=True)


# ── CLI ───────────────────────────────────────────────────────────

_PRINT_COLS = [
    "part_date", "timeline", "pickup_rgn1_nm", "pickup_rgn2_nm",
    "intensity_label", "mean_dbz_when_rain", "precip_coverage",
    "weighted_dbz", "dominant_precip_type",
]


def _cli():
    p = argparse.ArgumentParser(
        description="우천 강도 표준화 (구군 × 30분 슬롯). 분석/표본추출용 단일 파일.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("start_date", help="YYYY-MM-DD (운영 영업일 시작, KST 06:00 기준)")
    p.add_argument("end_date",   help="YYYY-MM-DD (운영 영업일 끝, inclusive)")
    p.add_argument("--start", default="06:00", help="운영시간 시작 (기본 06:00)")
    p.add_argument("--end",   default="27:00", help="운영시간 끝 (exclusive, 기본 27:00)")
    p.add_argument("--top",   type=int, default=None,
                   help="상위 N개만 출력 (--by 기준)")
    p.add_argument("--by",    default="weighted_dbz",
                   choices=sorted(_VALID_SORT_COLS),
                   help="--top 정렬 기준 (기본 weighted_dbz)")
    p.add_argument("--group-by", default=None,
                   help="그룹별 top-N 키 (예: part_date 또는 part_date,pickup_rgn1_nm)")
    p.add_argument("-o", "--output", default=None,
                   help="CSV 저장 경로 (미지정 시 stdout 핵심 컬럼만 출력)")
    args = p.parse_args()

    df = fetch(args.start_date, args.end_date, args.start, args.end)

    if args.top is not None:
        gb = None
        if args.group_by:
            gb = [k.strip() for k in args.group_by.split(",")] if "," in args.group_by else args.group_by
        df = top_severe(df, n=args.top, by=args.by, group_by=gb)

    if args.output:
        df.to_csv(args.output, index=False, encoding="utf-8-sig")
        print(f"💾 {len(df)}행 → {args.output}")
        return

    if df.empty:
        print("(강수 슬롯 없음)")
        return

    with pd.option_context("display.max_rows", 200, "display.width", 180,
                           "display.float_format", lambda x: f"{x:.2f}"):
        print(df[_PRINT_COLS].to_string(index=False))


if __name__ == "__main__":
    _cli()
