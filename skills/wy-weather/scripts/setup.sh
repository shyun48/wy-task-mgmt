#!/usr/bin/env bash
# wy-weather setup wizard — Trino 인증 정보 등록
# 결과: ~/.config/wy-weather/config.env (chmod 600)

set -euo pipefail

CONFIG_DIR="${HOME}/.config/wy-weather"
CONFIG_FILE="${CONFIG_DIR}/config.env"

if [[ -f "$CONFIG_FILE" && "${1:-}" != "--force" ]]; then
    echo "[wy-weather] 이미 setup 됨: $CONFIG_FILE"
    echo "  재설정: bash \"$0\" --force"
    exit 0
fi

echo "[wy-weather setup] Trino 인증 정보 등록"
echo "  결과 저장 위치: $CONFIG_FILE (chmod 600)"
echo

# 1) .env 파일 경로 직접 입력
while true; do
    read -r -p ".env 파일 경로 (Trino 인증 변수 위치): " ENV_FILE
    ENV_FILE="${ENV_FILE/#\~/$HOME}"  # ~ 확장
    if [[ -z "$ENV_FILE" ]]; then
        echo "  경로 비었음. 다시 입력하세요."
        continue
    fi
    if [[ -f "$ENV_FILE" ]]; then
        # 절대경로로 정규화
        ENV_FILE="$(cd "$(dirname "$ENV_FILE")" && pwd)/$(basename "$ENV_FILE")"
        break
    fi
    echo "  파일 없음: $ENV_FILE"
done

# 2) 키 이름 입력 (USER / PASS 컬럼명)
read -r -p "Trino USER 변수명 [RTO_TRINO_USER]: " USER_KEY
USER_KEY="${USER_KEY:-RTO_TRINO_USER}"

read -r -p "Trino PASS 변수명 [RTO_TRINO_PASS]: " PASS_KEY
PASS_KEY="${PASS_KEY:-RTO_TRINO_PASS}"

# 3) 검증 — 두 키가 .env에 실제로 있는지 (값은 출력 안 함)
MISSING=()
if ! grep -qE "^[[:space:]]*(export[[:space:]]+)?${USER_KEY}=" "$ENV_FILE"; then
    MISSING+=("$USER_KEY")
fi
if ! grep -qE "^[[:space:]]*(export[[:space:]]+)?${PASS_KEY}=" "$ENV_FILE"; then
    MISSING+=("$PASS_KEY")
fi
if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "  ⚠️  다음 키가 ${ENV_FILE}에 없습니다: ${MISSING[*]}"
    read -r -p "  그래도 진행할까요? [y/N]: " yn
    [[ "$yn" =~ ^[Yy]$ ]] || { echo "  취소됨."; exit 1; }
fi

# 4) config 저장
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

cat > "$CONFIG_FILE" <<EOF
# wy-weather config — auto-generated $(date '+%Y-%m-%d %H:%M:%S')
# 인증값 자체는 저장하지 않음. .env 경로와 키 이름만 저장.
TRINO_ENV_FILE="${ENV_FILE}"
TRINO_USER_KEY="${USER_KEY}"
TRINO_PASS_KEY="${PASS_KEY}"
EOF
chmod 600 "$CONFIG_FILE"

echo
echo "✅ setup 완료"
echo "  config: $CONFIG_FILE"
echo "  .env 경로: $ENV_FILE"
echo "  USER 키: $USER_KEY"
echo "  PASS 키: $PASS_KEY"
echo
echo "테스트: bash $(dirname "$0")/run.sh 2025-08-19 2025-08-19 --top 5"
