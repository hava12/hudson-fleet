"""외부 서비스 연결: GitHub·Jira REST. 토큰은 설정 화면(⚙ → 연결)에서 넣는다 (DB settings 표).
gh 같은 도구를 설치하지 않아도 되게 표준 라이브러리(urllib)만 쓴다. 에이전트는 fleet MCP 도구로 이 서버를 거쳐 부른다.
ponytail: 인증은 이 파일의 github()·jira() 두 곳만 — Jira 를 OAuth 로 바꾸게 되면 jira() 만 고친다."""
import base64
import json
import re
import urllib.error
import urllib.parse
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


def jira_issues():
    """나에게 할당되고 아직 끝나지 않은 이슈 (최근 업데이트 순, 50건까지)."""
    q = urllib.parse.urlencode({"jql": "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC",
                                "fields": "summary,status,priority,project,issuetype,updated", "maxResults": 50})
    site = CFG["HUDSON_FLEET_JIRA_SITE"]
    return [{"key": i["key"], "url": f"https://{site}/browse/{i['key']}", "title": f["summary"],
             "status": f["status"]["name"], "cat": f["status"]["statusCategory"]["key"],  # new · indeterminate · done
             "project": f["project"]["key"], "type": f["issuetype"]["name"],
             "priority": (f.get("priority") or {}).get("name"),
             "updated": re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", f["updated"])}  # +0900 → +09:00 (Safari 가 읽게)
            for i in jira("/rest/api/3/search/jql?" + q).get("issues", []) for f in [i["fields"]]]


def _adf_text(n):
    """Jira 본문(ADF: 문서 구조 JSON)을 글로 — 글자만 모으고 문단·제목·코드 끝에서 줄을 바꾼다."""
    if isinstance(n, list):
        return "".join(_adf_text(x) for x in n)
    if not isinstance(n, dict):
        return ""
    t = "\n" if n.get("type") == "hardBreak" else n.get("text", "") + _adf_text(n.get("content", []))
    return t + "\n" if n.get("type") in ("paragraph", "heading", "codeBlock") else t


def jira_issue(key):
    """이슈 하나의 제목·본문 (맡기기 지시문용)."""
    i = jira(f"/rest/api/3/issue/{urllib.parse.quote(key)}?fields=summary,description")
    return {"key": i["key"], "title": i["fields"]["summary"], "url": f"https://{CFG['HUDSON_FLEET_JIRA_SITE']}/browse/{i['key']}",
            "body": _adf_text(i["fields"].get("description")).strip()}


def github_prs():
    """열려 있는 내 PR 과 나에게 리뷰 요청된 PR (검색 API, 최근 업데이트 순)."""
    def find(q):
        items = github("/search/issues?" + urllib.parse.urlencode({"q": q, "sort": "updated", "per_page": 50}))["items"]
        return [{"num": p["number"], "title": p["title"], "url": p["html_url"], "draft": p.get("draft", False),
                 "repo": p["repository_url"].split("/repos/", 1)[1], "updated": p["updated_at"]} for p in items]
    return {"mine": find("is:pr is:open author:@me"), "review": find("is:pr is:open review-requested:@me")}


def check(service):
    """연결 확인: 토큰 주인의 이름을 돌려준다."""
    if service == "github":
        return github("/user")["login"]
    if service == "jira":
        me = jira("/rest/api/3/myself")
        return me.get("displayName") or me.get("emailAddress")
    raise LinkError("service 는 github 또는 jira")
