#!/bin/sh
# SessionStart: 대시보드 서버(HUDSON_FLEET_PORT, 기본 8765)가 없을 때만 백그라운드로 띄우고 바로 끝난다.
# 세션이 여러 개여도 서버는 하나, 세션이 다 끝나도 서버는 남는다.
# ponytail: 포트만 확인한다 — 플러그인을 업데이트하면 떠 있는 서버를 한 번 꺼야 새 코드로 뜬다
nc -z 127.0.0.1 "${HUDSON_FLEET_PORT:-8765}" 2>/dev/null && exit 0
nohup python3 "${CLAUDE_PLUGIN_ROOT}/server.py" >/dev/null 2>&1 &
exit 0
