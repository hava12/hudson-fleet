"""Hudson Fleet — Claude Code 세션 대시보드. 실행: python3 server.py → http://127.0.0.1:8765 (포트는 HUDSON_FLEET_PORT)
코드는 fleet/ 에 기능별로 있다. 이 파일은 훅(hooks/start.sh)과 README 가 부르는 진입점이다."""
import threading
from http.server import ThreadingHTTPServer

from fleet.config import ORIGIN, PORT
from fleet.db import DB, load_settings
from fleet.recorder import record
from fleet.web import H

if __name__ == "__main__":
    print(f"→ {ORIGIN} · 지표 DB: {DB}")
    load_settings()  # 설정 화면에서 바꾼 값이 환경 변수보다 먼저
    threading.Thread(target=record, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
