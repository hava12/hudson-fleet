"""설정(환경 변수)·경로·버전·claude CLI 호출."""
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


# 설정은 모두 환경 변수 — ~/.claude/settings.json 의 "env" 에 적으면 MCP 서버와 그 안의 대시보드 서버가 받는다. 바꾸면 세션을 모두 다시 연다.
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

# 버전: 이 코드의 버전과 지금 설치된 플러그인 버전. 리더가 옛 버전이면 새 버전 대기자에게 자리를 넘긴다 (server.lead)
ROOT = Path(__file__).resolve().parent.parent
VERSION = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]


def ver(v):
    """'0.5.17' → (0, 5, 17). 비교용."""
    return tuple(int(x) for x in str(v).split(".") if x.isdigit())


def installed_version():
    """~/.claude/plugins/installed_plugins.json 의 hudson-fleet 버전. 못 읽으면 None (직접 실행 등)."""
    try:
        rows = json.loads((Path.home() / ".claude" / "plugins" / "installed_plugins.json").read_text())["plugins"]
        return rows["hudson-fleet@hudson-fleet"][0]["version"]
    except (OSError, ValueError, KeyError, IndexError):
        return None


# 대시보드가 내부용으로 돌리는 claude -p 는 MCP 서버·훅을 띄우지 않는다.
# 안 그러면 호출마다 사용자의 MCP 서버(예: Java 서버)와 다른 플러그인의 SessionStart 훅이 전부 실행된다.
QUIET = ("--no-session-persistence", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
         "--settings", '{"disableAllHooks":true}')


def claude(*args, cwd=None):
    r = subprocess.run(["claude", *args], cwd=cwd, capture_output=True, text=True, timeout=60)
    return (r.stdout or r.stderr).strip()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
