"""Hudson Fleet — Claude Code 세션 대시보드. 실행: python3 server.py → http://127.0.0.1:8765 (포트는 HUDSON_FLEET_PORT)
코드는 fleet/ 에 기능별로 있다. 보통은 세션마다 뜨는 MCP 서버(mcp_server.py)가 lead() 로 띄운다.

리더 선출: 세션마다 MCP 서버가 하나씩 뜨고, 그중 포트를 먼저 연 하나만 화면과 1분 기록을 맡는다.
나머지는 1초마다 다시 열어 보다가, 맡던 세션이 끝나 포트가 비면 하나가 이어받는다 (화면은 1~2초 멈췄다 이어진다).
플러그인을 업데이트하면 새 세션의 대기자가 10초마다 리더 버전을 보고, 리더가 더 옛 버전이면 자리를 넘겨 달라고 한다.
화면의 [새 버전으로 바꾸기] 는 설치된 새 버전의 이 파일을 세션과 따로 띄우고 자리를 넘긴다 (아래 __main__)."""
import json
import socket
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

from fleet.config import ORIGIN, PORT, VERSION, installed_version, ver
from fleet.db import DB, load_settings
from fleet.recorder import record
from fleet.web import H


def serve(srv):
    """서버를 맡는다. 자리를 넘기면(/api/handover → srv.shutdown) 1분 기록도 멈추고 돌아온다."""
    load_settings()  # 설정 화면에서 바꾼 값이 환경 변수보다 먼저
    stop = threading.Event()
    threading.Thread(target=record, args=(stop,), daemon=True).start()
    try:
        srv.serve_forever()
    finally:
        stop.set()
        srv.server_close()  # 포트를 놓아야 새 리더가 연다


def ask_handover():
    """리더가 나보다 옛 버전이면 자리를 넘겨 달라고 한다. 리더가 없거나 응답이 없으면 그냥 넘어간다."""
    try:
        with urllib.request.urlopen(ORIGIN + "/api/version", timeout=2) as r:
            if ver(json.loads(r.read())["version"]) >= ver(VERSION):
                return
        req = urllib.request.Request(ORIGIN + "/api/handover", json.dumps({"version": VERSION}).encode(),
                                     {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2).close()
    except (OSError, ValueError, KeyError):
        pass


def port_free():
    """포트를 여는(bind) 대신 접속해 본다 — 비어 있는지 보기만 하고 자리를 잡지 않는다."""
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=0.5).close()
        return False
    except OSError:
        return True


def lead():
    """포트를 열 때까지 1초마다 시도하고, 열면 그 서버를 맡는다 (MCP 서버의 백그라운드 스레드).
    새 버전에 자리를 넘기면 5초 쉬었다가 다시 대기자가 된다. 옛 버전 대기자는 양보하므로 넘겨줄 때 새 버전이 먼저 연다."""
    n = free = 0
    while True:
        # 이 PC 에 더 새 버전이 설치돼 있으면 나는 옛 버전 — 포트가 3초 넘게 비어 있을 때만 맡는다.
        # 새 버전 대기자는 1초마다 시도하니 먼저 잡고, 새 버전 세션이 없으면 3초 뒤 내가 맡아 화면이 꺼지지 않는다
        if ver(installed_version()) > ver(VERSION):
            free = free + 1 if port_free() else 0
            if free <= 3:
                time.sleep(1)
                continue
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
        except OSError:  # 다른 세션이 맡고 있다
            n += 1
            if n % 10 == 0:
                ask_handover()
            time.sleep(1)
            continue
        print(f"→ {ORIGIN} 대시보드를 맡았습니다 (v{VERSION}) · 지표 DB: {DB}")
        serve(srv)
        print(f"v{VERSION} 리더 자리를 새 버전에 넘겼습니다")
        time.sleep(5)


if __name__ == "__main__":  # 직접 실행 · [새 버전으로 바꾸기]: 앞 리더가 포트를 놓을 때까지 10초 기다렸다가 맡고, 자리를 넘기면 끝난다
    for _ in range(10):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
            break
        except OSError:
            time.sleep(1)
    else:
        sys.exit(f"{PORT} 포트를 다른 프로그램이 쓰고 있습니다")
    H.log_message = lambda *a: None  # 요청마다 남는 접근 기록은 버린다 — 세션과 따로 오래 돌아 로그 파일이 끝없이 커지지 않게
    print(f"→ {ORIGIN} (v{VERSION}) · 지표 DB: {DB}", flush=True)
    serve(srv)
