#!/bin/sh
# 대시보드 서버 실행. requirements.txt 에 패키지가 있으면 venv 를 만들어 그 python 으로 띄우고,
# 없으면 시스템 python3 으로 띄운다. requirements.txt 가 바뀌면 다시 설치한다 (내용 해시를 venv 에 적어 둔다).
# MCP 서버(mcp_server.py)는 세션마다 시스템 python3 으로 뜨므로 이 venv 를 쓰지 않는다.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REQ="$ROOT/requirements.txt"
PY=python3
if grep -v '^[[:space:]]*#' "$REQ" 2>/dev/null | grep -q '[^[:space:]]'; then  # 주석·빈 줄 말고 한 줄이라도 있으면
  VENV="${HUDSON_FLEET_VENV:-$HOME/.local/share/hudson-fleet/venv}"
  SUM=$(shasum "$REQ" | cut -d' ' -f1)
  if [ "$(cat "$VENV/.req" 2>/dev/null)" != "$SUM" ]; then
    echo "$(date '+%F %T') 의존성 설치: $REQ → $VENV"
    python3 -m venv "$VENV" && "$VENV/bin/pip" install -q -r "$REQ" && echo "$SUM" > "$VENV/.req" \
      || { echo "의존성 설치 실패 — 서버를 띄우지 않습니다"; exit 1; }
  fi
  PY="$VENV/bin/python"
fi
echo "$(date '+%F %T') 서버 시작: $PY"
exec "$PY" "$ROOT/server.py"
