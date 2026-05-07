"""
Trino 쿼리 클라이언트 — 회사 데이터 웨어하우스 조회 유틸리티

Usage:
    from trino_client import trino_query, trino_engine

    # 단건 쿼리
    df = trino_query("SELECT 1 AS test")

    # 카탈로그/스키마 지정
    df = trino_query("SELECT * FROM some_table LIMIT 10", catalog="hive", schema="raw_log")

    # 엔진 직접 사용
    engine = trino_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT ..."))

환경변수:
    RTO_TRINO_USER — Trino 계정 ID (미설정 시 CLI에서만 입력 프롬프트)
    RTO_TRINO_PASS — Trino 계정 PW (미설정 시 CLI에서만 입력 프롬프트)
"""
import logging
import os
import re
import sys
import getpass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
import pandas as pd
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)
from sql_loader import load_sql

# ── .env 자동 로드 (프로젝트 루트 / deploy/ 둘 다 지원) ──
try:
    from dotenv import load_dotenv
    _HERE = Path(__file__).resolve()
    # 후보: 같은 폴더 / 상위 / deploy_v3 / deploy 절대경로 (Trino 인증 .env 위치)
    _env_candidates = [
        _HERE.parent / ".env",
        _HERE.parent.parent / ".env",
        _HERE.parent.parent.parent / ".env",
        Path("/Users/suhyun.kim/Documents/claude/deploy_v3/.env"),
        Path("/Users/suhyun.kim/Documents/claude/deploy/.env"),
    ]
    for _env_path in _env_candidates:
        if _env_path.exists():
            load_dotenv(_env_path, override=False)  # 기존 shell env 우선
            break
except ImportError:
    pass  # python-dotenv 미설치 시 shell env 만 사용

# ── Trino 접속 정보 ──
TRINO_HOST = "trino-auth.emr.ds.woowa.in"
TRINO_PORT = 443
TRINO_CATALOG = "hive_zeppelin"
TRINO_SCHEMA = "sbbi"

_engine_cache = {}

# H3 hex ID 형식: 15자리 hex 문자열
_H3_PATTERN = re.compile(r'^[0-9a-fA-F]{15}$')


def _get_credentials():
    """환경변수에서 인증정보 획득. 미설정 시 CLI만 대화형 입력, 비대화형은 예외."""
    user = os.environ.get("RTO_TRINO_USER")
    pw = os.environ.get("RTO_TRINO_PASS")
    if user and pw:
        return user, pw
    # 비대화형 환경(K8s, CI 등)에서는 block 방지를 위해 예외
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Trino 인증정보 미설정: RTO_TRINO_USER / RTO_TRINO_PASS 환경변수를 설정하세요. "
            "비대화형 환경에서는 input() 프롬프트를 사용할 수 없습니다."
        )
    if not user:
        user = input("Trino 계정 ID: ")
    if not pw:
        pw = getpass.getpass("Trino 계정 PW: ")
    return user, pw


def trino_engine(catalog=None, schema=None):
    """SQLAlchemy Trino 엔진 생성 (캐싱)"""
    cat = catalog or TRINO_CATALOG
    sch = schema or TRINO_SCHEMA
    cache_key = f"{cat}/{sch}"

    if cache_key in _engine_cache:
        return _engine_cache[cache_key]

    user, pw = _get_credentials()
    url = f"trino://{quote_plus(user)}:{quote_plus(pw)}@{TRINO_HOST}:{TRINO_PORT}/{cat}/{sch}"
    engine = create_engine(
        url,
        connect_args={
            "http_scheme": "https",
        },
    )
    _engine_cache[cache_key] = engine
    return engine


def _ensure_limit(query, limit=1000000):
    """회사 Trino 정책: outer LIMIT 필수 — 없으면 자동 추가"""
    q = query.strip().rstrip(";")
    if re.search(r'\bLIMIT\s+\d+\s*$', q, re.IGNORECASE):
        return q
    return f"{q}\nLIMIT {limit}"


def trino_query(query, catalog=None, schema=None, params=None, limit=1000000):
    """Trino 쿼리 실행 → DataFrame 반환

    Args:
        query: SQL 문자열
        catalog: Trino 카탈로그 (기본: hive_zeppelin)
        schema: Trino 스키마 (기본: sbbi)
        params: SQL 바인드 파라미터 dict
        limit: 자동 LIMIT (기본 1000000, 회사 정책)

    Returns:
        pd.DataFrame
    """
    engine = trino_engine(catalog, schema)
    q = _ensure_limit(query, limit)
    with engine.connect() as conn:
        result = conn.execute(text(q), params or {})
        columns = list(result.keys())
        rows = result.fetchall()
    return pd.DataFrame(rows, columns=columns)


def trino_query_to_csv(query, output_path, catalog=None, schema=None,
                       chunk_size=100000):
    """Trino 쿼리 → CSV 저장 (chunk 단위 fetch/write로 OOM 방지)

    Args:
        query: SQL 문자열
        output_path: CSV 저장 경로
        catalog, schema: Trino 카탈로그/스키마
        chunk_size: 한 번에 fetch할 행 수 (기본 100,000)
    """
    engine = trino_engine(catalog, schema)
    q = _ensure_limit(query)
    total_rows = 0
    with engine.connect() as conn:
        result = conn.execute(text(q))
        columns = list(result.keys())
        first_chunk = True
        while True:
            rows = result.fetchmany(chunk_size)
            if not rows:
                break
            df_chunk = pd.DataFrame(rows, columns=columns)
            df_chunk.to_csv(
                output_path,
                index=False,
                encoding="utf-8-sig",
                mode="w" if first_chunk else "a",
                header=first_chunk,
            )
            total_rows += len(df_chunk)
            first_chunk = False
    logger.info(f"💾 {total_rows}행 → {output_path}")
    return total_rows


# ── 입력값 검증 헬퍼 ──

def _validate_date(d):
    """YYYY-MM-DD 형식 + 달력 유효성 검증"""
    if not isinstance(d, str):
        raise ValueError(f"날짜 형식 오류 (YYYY-MM-DD 필요): {d!r}")
    try:
        datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"날짜 형식 오류 (YYYY-MM-DD 필요): {d!r}")
    return d


def _validate_positive_int(val, name="value"):
    """양의 정수 검증"""
    if not isinstance(val, int) or val <= 0:
        raise ValueError(f"{name}은 양의 정수여야 합니다: {val!r}")
    return val


def _validate_h3_hexes(hexes):
    """H3 hex ID 리스트 형식 검증 + 소문자 정규화"""
    if not hexes:
        return hexes
    normalized = []
    for h in hexes:
        if not isinstance(h, str) or not _H3_PATTERN.match(h):
            raise ValueError(f"유효하지 않은 H3 hex ID: {h!r} (15자리 hex 문자열 필요)")
        normalized.append(h.lower())
    return normalized


# ── 기상 데이터 전용 헬퍼 ──

# rainfallType 우선순위: 강수 강도 기반 (사전순 MAX() 대체)
# THUNDERSTORM > SNOW > SLEET > RAIN > DRIZZLE
_PRECIP_TYPE_PRIORITY = """
    CASE
      WHEN MAX(CASE WHEN {col} = 'THUNDERSTORM' THEN 1 ELSE 0 END) = 1 THEN 'THUNDERSTORM'
      WHEN MAX(CASE WHEN {col} = 'SNOW' THEN 1 ELSE 0 END) = 1 THEN 'SNOW'
      WHEN MAX(CASE WHEN {col} = 'SLEET' THEN 1 ELSE 0 END) = 1 THEN 'SLEET'
      WHEN MAX(CASE WHEN {col} = 'RAIN' THEN 1 ELSE 0 END) = 1 THEN 'RAIN'
      WHEN MAX(CASE WHEN {col} = 'DRIZZLE' THEN 1 ELSE 0 END) = 1 THEN 'DRIZZLE'
      ELSE MAX({col})
    END
""".strip()


# ── 운영시간 / 우천 강도 등급 상수 ──
# 운영 영업일: KST 06:00~익일 03:00 (운영시간 06~27시). 새벽 0~3시는 24~27시로 표기.
_OP_MIN_START = 360    # 06:00
_OP_MIN_END   = 1620   # 27:00 (= 익일 03:00)

# 등급 임계 (mean_dbz_when_rain 기준, 선형 Z 평균 후 dBZ 환산값)
_INTENSITY_BINS   = [-float("inf"), 25.0, 30.0, 40.0, 50.0, 55.0, float("inf")]
_INTENSITY_LABELS = ["NONE", "LIGHT", "LIGHT-MODERATE", "MODERATE", "HEAVY", "EXTREME"]
_PRECIP_PRIORITY  = ["THUNDERSTORM", "SNOW", "SLEET", "RAIN", "DRIZZLE"]
_DBZ_PRECIP_THRESHOLD = 25.0   # 강수로 카운트할 hex 최소 dBZ


def _parse_op_minute(t):
    """운영시간 'HH:MM' → 분 단위 정수. 24+ 표기 허용 (예: '26:00' = 1560)."""
    if not isinstance(t, str):
        raise ValueError(f"시간 형식 오류 (HH:MM 필요): {t!r}")
    parts = t.split(":")
    if len(parts) != 2:
        raise ValueError(f"시간 형식 오류 (HH:MM 필요): {t!r}")
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"시간 형식 오류 (HH:MM 필요): {t!r}")
    if not (0 <= m < 60):
        raise ValueError(f"분 범위 오류 (0~59): {t!r}")
    return h * 60 + m


def fetch_weather_national(start_date, end_date):
    """전국 분 단위 기상 시계열 조회 (Layer C 백테스트용)

    Args:
        start_date: 'YYYY-MM-DD' (KST 기준)
        end_date: 'YYYY-MM-DD' (KST 기준, inclusive)

    Returns:
        DataFrame: event_date, kst_time, max_dbz, max_rainfall, precip_type, hex_count
    """
    _validate_date(start_date)
    _validate_date(end_date)
    if start_date > end_date:
        raise ValueError(f"start_date가 end_date보다 늦을 수 없습니다: {start_date} > {end_date}")

    precip_col = "JSON_EXTRACT_SCALAR(data, '$.weatherContext.rainfallType')"
    precip_agg = _PRECIP_TYPE_PRIORITY.format(col=precip_col)

    query = load_sql("weather/weather_national.sql", precip_agg=precip_agg)
    return trino_query(query, params={
        "start_ts": f"{start_date} 00:00:00",
        "end_ts": f"{end_date} 00:00:00",
    })


def fetch_weather_district_onset(start_date, end_date):
    """H3 hex별 강수 onset 조회 (구군 매핑용)

    Args:
        start_date, end_date: 'YYYY-MM-DD' (KST)

    Returns:
        DataFrame: event_date, h3_hex, precip_type, onset_kst, onset_hour, onset_minute, max_dbz, precip_minutes
    """
    _validate_date(start_date)
    _validate_date(end_date)
    if start_date > end_date:
        raise ValueError(f"start_date가 end_date보다 늦을 수 없습니다: {start_date} > {end_date}")

    query = load_sql("weather/weather_district_onset.sql")
    return trino_query(query, params={
        "start_ts": f"{start_date} 00:00:00",
        "end_ts": f"{end_date} 00:00:00",
    })


def fetch_weather_realtime(h3_hexes=None, minutes_back=5):
    """실시간 기상 조회 (engine.py 연동용)

    Args:
        h3_hexes: H3 hex ID 리스트 (None이면 전국)
        minutes_back: 최근 N분 (기본 5분, 양의 정수)

    Returns:
        DataFrame: h3_hex, dbz, rainfall, precip_type, temperature
    """
    _validate_positive_int(minutes_back, "minutes_back")
    h3_hexes = _validate_h3_hexes(h3_hexes)

    precip_col = "JSON_EXTRACT_SCALAR(data, '$.weatherContext.rainfallType')"
    precip_agg = _PRECIP_TYPE_PRIORITY.format(col=precip_col)

    hex_filter = ""
    if h3_hexes:
        # 검증 완료된 hex ID만 사용 (영숫자 15자리 보장)
        hex_list = ",".join(f"'{h}'" for h in h3_hexes)
        hex_filter = f"AND event_id IN ({hex_list})"

    query = load_sql(
        "weather/weather_realtime.sql",
        precip_agg=precip_agg,
        minutes_back=minutes_back,
        hex_filter=hex_filter,
    )
    return trino_query(query)


def fetch_weather_intensity_district(start_date, end_date,
                                     start_time="06:00", end_time="27:00"):
    """구군 × 30분 슬롯 단위 우천 강도 표준화.

    dBZ는 로그 스케일이라 산술평균 시 강한 hex가 약한 hex에 희석됨.
    선형 Z(=10^(dBZ/10)) 평균 후 다시 dBZ로 환산하는 정석 방식 사용.
    H3 hex × 분 raw → hex × 슬롯 → 구군 × 슬롯 단계로 두 번 선형 Z 평균.

    Args:
        start_date, end_date: 'YYYY-MM-DD' (운영 영업일, KST 06:00 기준)
        start_time, end_time: 'HH:MM', 운영 06:00~27:00 범위, end exclusive.
                              새벽 0~3시는 24~27시로 표기 (예: '26:00' = 익일 02:00)

    Returns:
        DataFrame with columns:
            part_date, timeline, pickup_rgn1_nm, pickup_rgn2_nm,
            mean_dbz_when_rain   : 강수 hex(dBZ≥25)만의 선형 Z 평균  ← 강도 본체
            precip_coverage      : 구군 전체 hex 대비 강수 hex 비율   ← 범위
            weighted_dbz         : coverage × mean_dbz_when_rain      ← 종합
            mean_dbz_linear      : 구군 전체 hex 기준 선형 Z 평균 (비강수 hex Z=0)
            mean_dbz_arith       : 강수 hex 산술 dBZ 평균 (참고용)
            max_dbz              : 슬롯 내 hex 최대 dBZ
            intensity_level      : 0~5 (mean_dbz_when_rain 기준)
            intensity_label      : NONE/LIGHT/LIGHT-MODERATE/MODERATE/HEAVY/EXTREME
            dominant_precip_type : 강수 hex 수 가중 + 우선순위
            precip_hex_count, total_hex_count

    Notes:
        - 강수 0인 (구군, 슬롯)은 결과에서 제외됨 (필요 시 운영 timeline frame에 left join).
        - h3_district_map.json 로드 → h3 hex를 '시도 시군구' 키로 매핑 후 split.
    """
    import json as _json
    import numpy as _np

    _validate_date(start_date)
    _validate_date(end_date)
    if start_date > end_date:
        raise ValueError(f"start_date가 end_date보다 늦을 수 없습니다: {start_date} > {end_date}")

    start_min = _parse_op_minute(start_time)
    end_min   = _parse_op_minute(end_time)
    if not (_OP_MIN_START <= start_min < end_min <= _OP_MIN_END):
        raise ValueError(
            f"운영시간 06:00~27:00 + start < end 필요: "
            f"{start_time}({start_min}) ~ {end_time}({end_min})"
        )

    # precip CTE에서 이미 raw data → precip_type 컬럼으로 추출했으므로, outer 집계는 그 컬럼 참조.
    precip_agg = _PRECIP_TYPE_PRIORITY.format(col="precip_type")

    # log_ts(UTC) 검색범위 — KST 영업일 [start 06:00, end+1 06:00) → UTC [start -3h, end +21h).
    # SQLAlchemy 2.x + Trino dialect의 dict→list-of-dict wrapping 버그 회피용으로
    # named bind 대신 SQL 안에 timestamp literal을 직접 substitute (값은 datetime이라 injection 없음).
    # start_minute/end_minute는 정수(검증된 _parse_op_minute 결과)라 함께 SQL format 치환.
    from datetime import timedelta
    ts0 = datetime.strptime(f"{start_date} 00:00:00", "%Y-%m-%d %H:%M:%S")
    ts1 = datetime.strptime(f"{end_date} 00:00:00", "%Y-%m-%d %H:%M:%S")
    log_ts_start = f"TIMESTAMP '{(ts0 - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')}'"
    log_ts_end   = f"TIMESTAMP '{(ts1 + timedelta(hours=21)).strftime('%Y-%m-%d %H:%M:%S')}'"

    sql = load_sql(
        "weather_intensity_district.sql",
        precip_agg=precip_agg,
        start_minute=start_min,
        end_minute=end_min,
        log_ts_start=log_ts_start,
        log_ts_end=log_ts_end,
    )
    raw = trino_query(sql)

    out_cols = [
        "part_date", "timeline", "pickup_rgn1_nm", "pickup_rgn2_nm",
        "mean_dbz_when_rain", "precip_coverage", "weighted_dbz",
        "mean_dbz_linear", "mean_dbz_arith", "max_dbz",
        "intensity_level", "intensity_label",
        "dominant_precip_type", "precip_hex_count", "total_hex_count",
    ]
    if raw.empty:
        return pd.DataFrame(columns=out_cols)

    # H3 → 구군 매핑 로드
    h3_map_path = Path(__file__).resolve().parent / "data" / "h3_district_map.json"
    with open(h3_map_path, encoding="utf-8") as f:
        h3_district = _json.load(f)

    hex_to_district = {}
    district_total_hex = {}
    for district_key, hexes in h3_district.items():
        district_total_hex[district_key] = len(hexes)
        for h in hexes:
            hex_to_district[h] = district_key

    raw["_district_key"] = raw["h3_hex"].map(hex_to_district)
    raw = raw[raw["_district_key"].notna()].copy()
    if raw.empty:
        return pd.DataFrame(columns=out_cols)

    splits = raw["_district_key"].str.split(" ", n=1, expand=True)
    raw["pickup_rgn1_nm"] = splits[0]
    raw["pickup_rgn2_nm"] = splits[1]

    # 강수 컷오프 dBZ ≥ 25
    rain = raw[raw["mean_dbz_linear_hex"] >= _DBZ_PRECIP_THRESHOLD].copy()
    if rain.empty:
        return pd.DataFrame(columns=out_cols)

    rain["_z"] = _np.power(10.0, rain["mean_dbz_linear_hex"] / 10.0)

    keys = ["part_date", "timeline", "pickup_rgn1_nm", "pickup_rgn2_nm", "_district_key"]
    agg = rain.groupby(keys).agg(
        z_sum=("_z", "sum"),
        precip_hex_count=("h3_hex", "nunique"),
        max_dbz=("max_dbz_hex", "max"),
        mean_dbz_arith=("mean_dbz_arith_hex", "mean"),
    ).reset_index()

    agg["mean_dbz_when_rain"] = 10.0 * _np.log10(agg["z_sum"] / agg["precip_hex_count"])
    agg["total_hex_count"]    = agg["_district_key"].map(district_total_hex)
    agg["precip_coverage"]    = agg["precip_hex_count"] / agg["total_hex_count"]
    agg["weighted_dbz"]       = agg["precip_coverage"] * agg["mean_dbz_when_rain"]
    # 비강수 hex Z=0으로 간주한 구군 전체 평균 (unconditional)
    agg["mean_dbz_linear"]    = 10.0 * _np.log10(agg["z_sum"] / agg["total_hex_count"])

    # 등급 매핑
    levels = pd.cut(
        agg["mean_dbz_when_rain"],
        bins=_INTENSITY_BINS,
        labels=list(range(len(_INTENSITY_LABELS))),
        right=False,
    ).astype(int)
    agg["intensity_level"] = levels
    agg["intensity_label"] = levels.map(dict(enumerate(_INTENSITY_LABELS)))

    # dominant_precip_type: 슬롯 내 강수 hex 수 가중 + 우선순위 tie-break
    type_keys = ["part_date", "timeline", "pickup_rgn1_nm", "pickup_rgn2_nm"]
    type_cnt = (
        rain.groupby(type_keys + ["precip_type"]).size().reset_index(name="_cnt")
    )
    type_cnt["_pri"] = type_cnt["precip_type"].map(
        lambda t: _PRECIP_PRIORITY.index(t) if t in _PRECIP_PRIORITY else 99
    )
    type_cnt = type_cnt.sort_values(
        type_keys + ["_cnt", "_pri"],
        ascending=[True] * len(type_keys) + [False, True],
    ).drop_duplicates(type_keys)
    type_cnt = type_cnt[type_keys + ["precip_type"]].rename(
        columns={"precip_type": "dominant_precip_type"}
    )

    out = agg.merge(type_cnt, on=type_keys, how="left")
    return out[out_cols].sort_values(type_keys).reset_index(drop=True)


# ── SH per-district (건당SH) 전용 헬퍼 ──
# cluster_sh_per_delivery.sql: 구군별 일별 건당SH/QSH/60분초과율 집계
# 인증: RTO_TRINO_USER / RTO_TRINO_PASS (기존 환경변수 재사용)

def fetch_sh_per_district(start_date, end_date, sql_path=None):
    """구군별 일별 건당SH (QSH/60분초과율 포함) 조회.

    Args:
        start_date: 'YYYY-MM-DD' (KST, inclusive)
        end_date:   'YYYY-MM-DD' (KST, inclusive)
        sql_path:   cluster_sh_per_delivery.sql 경로 (None이면 deploy/sql/ 기본)

    Returns:
        DataFrame: part_date, pickup_rgn1_nm, pickup_rgn2_nm, QSH, SH, QSH_ratio,
                   DT_60min, dlvry_cnt, "60분초과율", "건당SH"

    Notes:
        - SQL 템플릿은 Python `.format()` 으로 {start_date_str}/{end_date_str} 치환
        - _ensure_limit 기본 1,000,000 적용 (구군 x 일수 범위 내 충분)
    """
    _validate_date(start_date)
    _validate_date(end_date)
    if start_date > end_date:
        raise ValueError(f"start_date가 end_date보다 늦을 수 없습니다: {start_date} > {end_date}")

    if sql_path is None:
        sql = load_sql("cluster_sh_per_delivery.sql",
                       start_date_str=start_date, end_date_str=end_date)
    else:
        if not os.path.exists(sql_path):
            raise FileNotFoundError(f"cluster_sh_per_delivery.sql 없음: {sql_path}")
        with open(sql_path, encoding="utf-8") as f:
            sql = f.read().format(start_date_str=start_date, end_date_str=end_date)
    return trino_query(sql)


if __name__ == "__main__":
    print("Trino 연결 테스트...")
    df = trino_query("SELECT 1 AS test")
    print(f"✅ 연결 성공: {df}")

    print("\n기상 테이블 샘플 조회...")
    df2 = trino_query("""
        SELECT COUNT(*) AS cnt
        FROM raw_log.serverlog_ot_gateway_weather_eventstore
        WHERE log_ts >= NOW() - INTERVAL '1' HOUR
    """)
    print(f"최근 1시간 기상 레코드: {df2.iloc[0]['cnt']}건")
