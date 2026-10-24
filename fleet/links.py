"""외부 서비스 연결: GitHub·Jira REST. 토큰은 설정 화면(⚙ → 연결)에서 넣는다 (DB settings 표).
gh 같은 도구를 설치하지 않아도 되게 표준 라이브러리(urllib)만 쓴다. 에이전트는 fleet MCP 도구로 이 서버를 거쳐 부른다.
ponytail: 인증은 이 파일의 github()·jira() 두 곳만 — Jira 를 OAuth 로 바꾸게 되면 jira() 만 고친다."""
import base64
import json
import urllib.error
import urllib.request

from .config import CFG


class LinkError(Exception):
    """사용자에게 그대로 보여 줄 연결 오류."""


def _json(req, who):
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise LinkError(f"{who} 가 토큰을 거절했습니다 ({e.code}). 토큰 값과 권한을 확인하세요") from None
        raise LinkError(f"{who} 오류 {e.code}: {e.read()[:200].decode(errors='replace')}") from None
    except urllib.error.URLError as e:
        raise LinkError(f"{who} 에 연결하지 못했습니다: {e.reason}") from None


def _req(url, head, body, method):
    data = json.dumps(body).encode() if body is not None else None
    return urllib.request.Request(url, data, {"Accept": "application/json", "Content-Type": "application/json",
                                              "User-Agent": "hudson-fleet", **head}, method=method)


def _on(name, label):
    if CFG[f"HUDSON_FLEET_{name}_ON"] != "1":
        raise LinkError(f"{label} 연결이 꺼져 있습니다. 설정(⚙) → 연결에서 '사용'을 켜세요")


def github(path, body=None, method=None):
    _on("GITHUB", "GitHub")
    tok = CFG["HUDSON_FLEET_GITHUB_TOKEN"]
    if not tok:
        raise LinkError("GitHub 토큰이 없습니다. 설정(⚙) → 연결에서 넣으세요")
    return _json(_req("https://api.github.com" + path, {"Authorization": "Bearer " + tok,
                                                        "X-GitHub-Api-Version": "2022-11-28"}, body, method), "GitHub")


def jira(path, body=None, method=None):
    _on("JIRA", "Jira")
    site, email, tok = (CFG[f"HUDSON_FLEET_JIRA_{k}"] for k in ("SITE", "EMAIL", "TOKEN"))
    if not (site and email and tok):
        raise LinkError("Jira 사이트·이메일·토큰을 모두 넣으세요. 설정(⚙) → 연결")
    auth = base64.b64encode(f"{email}:{tok}".encode()).decode()  # Jira Cloud: 이메일 + API 토큰 기본 인증
    return _json(_req(f"https://{site}{path}", {"Authorization": "Basic " + auth}, body, method), "Jira")


def check(service):
    """연결 확인: 토큰 주인의 이름을 돌려준다."""
    if service == "github":
        return github("/user")["login"]
    if service == "jira":
        me = jira("/rest/api/3/myself")
        return me.get("displayName") or me.get("emailAddress")
    raise LinkError("service 는 github 또는 jira")
