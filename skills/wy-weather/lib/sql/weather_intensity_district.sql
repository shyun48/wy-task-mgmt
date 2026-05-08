-- SQL name: weather_intensity_district.sql
-- Parameters:
--   precip_agg                  : _PRECIP_TYPE_PRIORITY.format(col=...) 결과 주입 (Python format)
--   log_ts_start, log_ts_end : KST timestamp literal (영업일 [start 06:00, end+1 06:00))
--   start_minute, end_minute      : 운영시간 분 단위 정수, 360(06:00)~1620(27:00), end exclusive
-- Source : engine/utils/trino_client.py (fetch_weather_intensity_district)
-- Notes  :
--   - raw_log.log_ts 는 KST 로 동작 (Redash 검증 결과). +9h 변환 사용 안 함.
--   - 운영 영업일(part_date) = KST 06:00 기준. 새벽 0~5시 = 전일 영업일.
--     part_date = DATE(log_ts - INTERVAL '6' HOUR)
--   - 운영시간 표기: 새벽 0~5시는 24~29시로 환산.
--     op_minute_of_day = (kst_hour < 6 ? kst_hour+24 : kst_hour) * 60 + kst_minute
--   - 출력 단위: H3 hex × 30분 슬롯. Python에서 h3_district_map으로 구군 매핑 + 최종 집계/등급화.
--   - rainfallType='NONE' 및 dbz NULL 제외. dBZ 25 컷오프는 Python 후처리에서 적용.

WITH precip AS (
  SELECT
    log_ts AS kst_ts,
    HOUR(log_ts)   AS kst_hour,
    MINUTE(log_ts) AS kst_minute,
    event_id AS h3_hex,
    JSON_EXTRACT_SCALAR(data, '$.weatherContext.rainfallType') AS precip_type,
    CAST(JSON_EXTRACT_SCALAR(data, '$.weatherContext.dbzAfter10Min') AS DOUBLE) AS dbz_10m,
    CAST(JSON_EXTRACT_SCALAR(data, '$.weatherContext.rainfall')      AS DOUBLE) AS rainfall_mm
  FROM raw_log.serverlog_ot_gateway_weather_eventstore
  WHERE log_ts >= {log_ts_start}
    AND log_ts <  {log_ts_end}
    AND event_type = 'WEATHER_AGGREGATE_DATA_CHANGED'
    AND JSON_EXTRACT_SCALAR(data, '$.weatherContext.rainfallType') IS NOT NULL
    AND JSON_EXTRACT_SCALAR(data, '$.weatherContext.rainfallType') != 'NONE'
    AND CAST(JSON_EXTRACT_SCALAR(data, '$.weatherContext.dbzAfter10Min') AS DOUBLE) IS NOT NULL
),
slotted AS (
  SELECT
    DATE(kst_ts - INTERVAL '6' HOUR) AS part_date,
    CASE WHEN kst_hour < 6
         THEN (kst_hour + 24) * 60 + kst_minute
         ELSE  kst_hour       * 60 + kst_minute
    END AS op_minute_of_day,
    h3_hex,
    precip_type,
    dbz_10m,
    rainfall_mm
  FROM precip
)
SELECT
  part_date,
  -- 30분 슬롯 시작 → "HH:MM" (06:00~26:30, 24+ 운영표기)
  LPAD(CAST(CAST(FLOOR((FLOOR(op_minute_of_day / 30) * 30) / 60) AS BIGINT) AS VARCHAR), 2, '0')
    || ':' ||
  LPAD(CAST(CAST((FLOOR(op_minute_of_day / 30) * 30) % 60 AS BIGINT) AS VARCHAR), 2, '0')
    AS timeline,
  h3_hex,
  10.0 * LOG10(AVG(POWER(10.0, dbz_10m / 10.0))) AS mean_dbz_linear_hex,
  AVG(dbz_10m)      AS mean_dbz_arith_hex,
  MAX(dbz_10m)      AS max_dbz_hex,
  AVG(rainfall_mm)  AS mean_rainfall_hex,
  MAX(rainfall_mm)  AS max_rainfall_hex,
  {precip_agg}      AS precip_type,
  COUNT(*)          AS minute_count
FROM slotted
-- part_date 비교는 raw period 필터(KST 영업일 경계)로 이미 정확하므로 제거.
-- start_ts/end_ts를 두 위치에 reference하면 SQLAlchemy + Trino dialect bind 충돌.
WHERE op_minute_of_day >= {start_minute}
  AND op_minute_of_day <  {end_minute}
GROUP BY 1, 2, 3
