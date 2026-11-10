"""Figma 플러그인의 [토큰 보내기] — 받은 이름표를 설정의 토큰 파일(HUDSON_FLEET_TOKENS_CSS)에 CSS 로 쓴다.
플러그인은 Figma 안(출처 null)에서 부르므로 출처 검사를 받지 않는다. 그래서 다른 웹사이트가 보내도
색·크기·다른 이름표 말고는 파일에 들어가지 않게, 이름과 값을 한 칸씩 형식으로 거른다."""
import os
import re

from .config import CFG

HEAD = ("/* Figma 변수에서 만든 파일 — 손으로 고치지 말고 Figma 에서 고친 뒤 hudson-fleet 플러그인의 [토큰 보내기]로 다시 만든다.\n"
        "   밝은 화면 색은 Figma 에 모드가 없어(무료 요금제) style.css 맨 위에 그대로 둔다 */")
NAME = re.compile(r"--[\w-]{1,60}")
VALUE = re.compile(r"#[0-9a-f]{6}(?:[0-9a-f]{2})?|\d{1,4}(?:\.\d{1,2})?px|var\(--[\w-]{1,60}\)")


def tokens_css(items):
    """[{name, value, dark}] → (CSS 글, None) 또는 (None, 오류 문장)."""
    if not isinstance(items, list) or not 0 < len(items) <= 500:
        return None, "이름표가 없거나 너무 많습니다 (1~500개)"
    base, dark = [], []
    for t in items:
        n, v = (str(t.get(k, "")) if isinstance(t, dict) else "" for k in ("name", "value"))
        if not NAME.fullmatch(n) or not VALUE.fullmatch(v):
            return None, f"형식이 맞지 않는 이름표: {n[:60]} = {v[:60]}"
        (dark if t.get("dark") else base).append(f"  {n}:{v};")
    return "\n".join(filter(None, [HEAD, base and ":root{\n" + "\n".join(base) + "\n}",
                                   dark and "@media (prefers-color-scheme:dark){:root{\n" + "\n".join(dark) + "\n}}"])) + "\n", None


def save_tokens(body):
    """POST /api/tokens {tokens: [...]} → (응답, 코드). 파일 경로는 응답에 넣지 않는다 (다른 출처도 읽을 수 있음)."""
    path = os.path.expanduser(CFG["HUDSON_FLEET_TOKENS_CSS"])
    if not path:
        return {"error": "대시보드 설정(⚙)에서 토큰 파일 위치(HUDSON_FLEET_TOKENS_CSS)를 먼저 정하세요"}, 409
    if not os.path.isdir(os.path.dirname(path)):
        return {"error": "토큰 파일을 둘 폴더가 없습니다. 설정(⚙)의 토큰 파일 위치를 확인하세요"}, 409
    css, err = tokens_css(body.get("tokens"))
    if err:
        return {"error": err}, 400
    with open(path, "w") as f:
        f.write(css)
    return {"ok": True, "n": css.count("\n  --"), "file": os.path.basename(path)}, 200


if __name__ == "__main__":  # 확인: python3 -m fleet.tokens
    css, err = tokens_css([{"name": "--acc", "value": "#b4c5ff", "dark": True}, {"name": "--dis-bg", "value": "#ffffff1f", "dark": True},
                           {"name": "--fs-m", "value": "15px"}, {"name": "--link", "value": "var(--acc)", "dark": True}])
    assert not err and ":root{\n  --fs-m:15px;\n}" in css and "dark){:root{\n  --acc:#b4c5ff;\n  --dis-bg:#ffffff1f;\n  --link:var(--acc);\n}}" in css, css
    for bad in ({"name": "--x", "value": "red;}body{display:none"}, {"name": "x", "value": "1px"}, {"name": "--x", "value": "url(//evil)"}, "--x"):
        assert tokens_css([bad])[1], bad
    assert tokens_css([])[1] and tokens_css(None)[1]
    print("자체 검사 통과")
