"""Hudson Fleet — Claude Code 세션 대시보드. 실행: python3 server.py → http://127.0.0.1:8765 (포트는 HUDSON_FLEET_PORT)
코드는 fleet/ 에 기능별로 있다. 보통은 세션마다 뜨는 MCP 서버(mcp_server.py)가 lead() 로 띄운다.

리더 선출: 세션마다 MCP 서버가 하나씩 뜨고, 그중 포트를 먼저 연 하나만 화면과 1분 기록을 맡는다.
나머지는 1초마다 다시 열어 보다가, 맡던 세션이 끝나 포트가 비면 하나가 이어받는다 (화면은 1~2초 멈췄다 이어진다)."""
import threading
import time
from http.server import ThreadingHTTPServer

from fleet.config import ORIGIN, PORT
from fleet.db import DB, load_settings
from fleet.recorder import record
from fleet.web import H


def serve(srv):
    load_settings()  # 설정 화면에서 바꾼 값이 환경 변수보다 먼저
    threading.Thread(target=record, daemon=True).start()
    srv.serve_forever()


def lead():
    """포트를 열 때까지 1초마다 시도하고, 열면 그 프로세스가 끝날 때까지 서버를 맡는다 (MCP 서버의 백그라운드 스레드)."""
    while True:
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
        except OSError:  # 다른 세션이 맡고 있다
            time.sleep(1)
            continue
        print(f"→ {ORIGIN} 대시보드를 맡았습니다 · 지표 DB: {DB}")
        return serve(srv)


if __name__ == "__main__":
    print(f"→ {ORIGIN} · 지표 DB: {DB}")
    serve(ThreadingHTTPServer(("127.0.0.1", PORT), H))
