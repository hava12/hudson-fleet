"""설정(환경 변수)·경로·claude CLI 호출."""
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


# 설정은 모두 환경 변수 — ~/.claude/settings.json 의 "env" 에 적으면 훅·MCP·서버가 함께 받는다. 바꾸면 서버 재시작.
# DB 옆 .env (KEY=VALUE 줄) 도 읽는다. 플러그인을 업데이트해도 남는 곳. 환경 변수에 이미 있으면 그쪽이 먼저
ENV_FILE = Path.home() / ".local" / "share" / "hudson-fleet" / ".env"
if ENV_FILE.is_file():
    for line in ENV_FILE.read_text().splitlines():
        k, eq, v = line.partition("=")
        if eq and not k.strip().startswith("#"):
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))

CONFIG = [  # (이름, 기본값, 설명)
    ("HUDSON_FLEET_PORT", "8765", "대시보드 서버 포트"),
    ("HUDSON_FLEET_DB", str(Path.home() / ".local" / "share" / "hudson-fleet" / "metrics.db"), "SQLite 파일 경로"),
    ("HUDSON_FLEET_AUTO_SUMMARY", "1", "에이전트 기록이 없는 세션이 끝날 때 AI 로 작업 정리 (0 이면 끔 — 토큰 절약)"),
    ("HUDSON_FLEET_SUMMARY_MODEL", "haiku", "작업 정리에 쓰는 모델"),
    ("HUDSON_FLEET_RETENTION_DAYS", "0", "1분 지표(samples) 보관 일수. 0 이면 지우지 않음"),
    ("HUDSON_FLEET_TERMINAL", "Ghostty", "끝난 세션을 다시 열 터미널 앱: Ghostty 또는 Terminal"),
    ("HUDSON_FLEET_GIST", "", "프로필 카드(완료 작업 태그별 건수 SVG)를 30분마다 덮어쓸 Gist id. 비우면 끔"),
    ("HUDSON_FLEET_GIST_USER", "", "Gist 를 올릴 gh 계정 (gh auth token --user). 비우면 gh 의 현재 계정"),
]
CFG = {k: os.environ.get(k) or d for k, d, _ in CONFIG}
PORT = int(CFG["HUDSON_FLEET_PORT"])
ORIGIN = f"http://127.0.0.1:{PORT}"
PROJECTS = Path.home() / ".claude" / "projects"
SESSIONS = Path.home() / ".claude" / "sessions"
DEAD = {"stopped", "completed", "done", "failed"}


# 대시보드가 내부용으로 돌리는 claude -p 는 MCP 서버·훅을 띄우지 않는다.
# 안 그러면 호출마다 사용자의 MCP 서버(예: Java 서버)와 다른 플러그인의 SessionStart 훅이 전부 실행된다.
QUIET = ("--no-session-persistence", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
         "--settings", '{"disableAllHooks":true}')


def claude(*args, cwd=None):
    r = subprocess.run(["claude", *args], cwd=cwd, capture_output=True, text=True, timeout=60)
    return (r.stdout or r.stderr).strip()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
