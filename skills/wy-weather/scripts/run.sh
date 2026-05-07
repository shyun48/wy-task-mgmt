#!/usr/bin/env bash
# wy-weather run wrapper
#   1) ~/.config/wy-weather/config.env source (없으면 setup.sh 자동 호출)
#   2) .env에서 USER/PASS 값만 추출하여 RTO_TRINO_USER/PASS로 export
#   3) venv python으로 lib/weather_intensity.py 실행

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LIB_DIR="${SKILL_DIR}/lib"
CONFIG_FILE="${HOME}/.config/wy-weather/config.env"

# config 없으면 setup wizard 자동 진입
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "[wy-weather] config 없음 → setup 시작"
    bash "${SCRIPT_DIR}/setup.sh"
    [[ -f "$CONFIG_FILE" ]] || { echo "[wy-weather] setup 실패"; exit 1; }
fi

# config 로드 (TRINO_ENV_FILE, TRINO_USER_KEY, TRINO_PASS_KEY)
# shellcheck disable=SC1090
source "$CONFIG_FILE"

# .env에서 두 키만 추출 (그 외 변수 오염 안 함)
extract_value() {
    local key="$1" file="$2" line val
    line=$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}=" "$file" | head -n1)
    [[ -z "$line" ]] && return 1
    val="${line#*=}"
    # surrounding quote 제거 (싱글/더블)
    val="${val#\"}"; val="${val%\"}"
    val="${val#\'}"; val="${val%\'}"
    printf '%s' "$val"
}

USER_VAL=$(extract_value "$TRINO_USER_KEY" "$TRINO_ENV_FILE") || {
    echo "[wy-weather] ❌ ${TRINO_ENV_FILE}에서 ${TRINO_USER_KEY} 추출 실패"
    echo "  재설정: bash ${SCRIPT_DIR}/setup.sh --force"
    exit 1
}
PASS_VAL=$(extract_value "$TRINO_PASS_KEY" "$TRINO_ENV_FILE") || {
    echo "[wy-weather] ❌ ${TRINO_ENV_FILE}에서 ${TRINO_PASS_KEY} 추출 실패"
    echo "  재설정: bash ${SCRIPT_DIR}/setup.sh --force"
    exit 1
}

export RTO_TRINO_USER="$USER_VAL"
export RTO_TRINO_PASS="$PASS_VAL"

# Python 실행기 결정 (override: WY_WEATHER_PYTHON)
PY="${WY_WEATHER_PYTHON:-}"
if [[ -z "$PY" ]]; then
    if [[ -x "${HOME}/Documents/claude/venv/bin/python" ]]; then
        PY="${HOME}/Documents/claude/venv/bin/python"
    else
        PY="$(command -v python3 || command -v python)"
    fi
fi
[[ -x "$PY" ]] || { echo "[wy-weather] ❌ python 실행기 없음: $PY"; exit 1; }

cd "$LIB_DIR"
exec "$PY" weather_intensity.py "$@"
