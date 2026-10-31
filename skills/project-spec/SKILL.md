---
name: project-spec
description: 지금 작업 중인 프로젝트를 읽고 기획명세서를 HTML 한 파일로 만든다. 구성은 개요, 기능 명세, 기능별 플로우차트, 시스템 아키텍처, ERD, 진행 히스토리 6장이다. 결과 파일은 스킬을 실행한 폴더에 생긴다. "기획명세서 만들어 줘", "명세서 뽑아 줘", "ERD 포함해서 프로젝트 정리해 줘", "spec 문서 만들어" 같은 요청에 쓴다.
---

# 기획명세서 만들기

## 결과물
- 실행한 폴더(현재 작업 폴더)에 `<폴더이름>-기획명세서.html` 하나를 만든다. 사용자가 대상 폴더를 따로 말하면 그 폴더를 조사하고 그 폴더에 만든다. 외부 파일 없이 혼자 열리는 HTML이다.
- 같은 이름이 이미 있으면 먼저 읽는다. 진행 히스토리는 이어 쓰고, 문서 버전(v0.1 → v0.2)을 올린 뒤 덮어쓴다.
- 도식은 mermaid로 그린다. 인터넷이 없으면 도식 대신 원문이 보이므로, 그때 쓸 안내 문구를 넣어 둔다.

## 절대 규칙
- **코드와 문서에서 확인한 사실만 쓴다.** 추측으로 채우지 않는다. 모르는 것은 칸에 `확인 필요`라고 적고 마지막에 모아서 알린다.
- **비밀 값은 쓰지 않는다.** `.env`, 키, 토큰, 비밀번호, 개인정보는 이름만 적고 값은 적지 않는다.
- 근거를 남긴다. 기능과 표는 어느 파일에서 확인했는지 `파일경로:줄`로 적는다.
- 질문은 꼭 필요할 때만, 한 번에 3개 이내로 한다(예: 대상 이용자, 범위에서 뺄 것). 코드로 알 수 있는 것은 묻지 않는다.
- 글은 쉬운 공문서 쓰기 규칙을 따른다. 짧은 문장과 개조식 표로 쓰고, 코드 이름은 꼭 필요할 때만 괄호로 붙인다.

## 1단계: 조사 (쓰기 전에 끝낸다)
1. 개요 재료: `README*`, `CLAUDE.md`, `docs/`, 패키지 파일(`package.json`, `build.gradle`, `pyproject.toml` 등)
2. 기능 재료: 화면·라우트·컨트롤러·API·명령·이벤트 처리 코드, 설정 파일, 시험 코드(시험 이름이 곧 기능 규칙인 경우가 많다)
3. 아키텍처 재료: 진입점, 서버·워커·큐·배치, 배포 설정(`Dockerfile`, `wrangler.*`, `*.yaml`, CI), 외부 서비스 호출, 환경 변수 이름
   - 의존성 재료: 패키지 파일과 잠금 파일(`package-lock.json`, `gradle.lockfile`, `poetry.lock` 등)의 버전, HTML의 CDN `<script>`·importmap 주소, 소스의 `import` 문
4. ERD 재료: 마이그레이션·`schema.sql`·ORM 엔티티(JPA `@Entity`, Prisma, TypeORM, Django models 등)·DB 생성 코드. DB가 없으면 데이터가 어디에 있는지(파일·메모리·외부 서비스) 확인한다
5. 히스토리 재료: **hudson-fleet 기록이 있으면 먼저 쓴다.**
   - `project_list`로 이 프로젝트를 고르고(이름·완료 조건으로 판단, 애매하면 사용자에게 한 번 묻는다) `project_history(id)`를 부른다. 도구가 지연 로드면 ToolSearch로 `select:mcp__plugin_hudson-fleet_fleet__project_list,mcp__plugin_hudson-fleet_fleet__project_history`
   - 받는 것: 프로젝트 정보(완료 조건 → 개요의 목표·범위), 작업(날짜·상태·결과·흐름도 → 진행 히스토리·기능 명세의 상태), push 커밋(`remote`·`cwd`가 이 저장소인 것만), 자료(결정 근거)
   - 그다음 `git log --date=short --pretty='%ad %s' -n 200`, `CHANGELOG*`로 빈 곳을 채운다. fleet이 없으면 이것만 쓴다
6. 이 대화에서 사용자가 정한 사항(범위, 정책, 결정)도 재료다. 출처를 `대화(날짜)`로 적는다

## 2단계: 6장 쓰기

### 1. 개요
- 한 줄 정의, 누구를 위한 것인지, 해결하는 문제
- 범위: 포함하는 것과 하지 않는 것(명시된 것만)
- 현재 상태(완료·개발 중·예정 개수), 기준일, 저장소 위치, 문서 버전

### 2. 기능 명세
표로 쓴다: `번호(F-01…) | 기능 | 내용(동작·규칙·수치) | 근거(파일:줄) | 상태`
- 상태는 `완료`, `개발 중`, `예정` 셋만 쓴다. 칩으로 색을 구분한다.
- 수치(제한, 시간, 크기, 개수)는 코드에 있는 값 그대로 쓴다.
- 기능이 많으면 화면·도메인 단위로 묶고 소제목을 단다.

### 3. 기능별 플로우차트
- 기능 명세의 번호마다 mermaid `flowchart TD` 하나를 그린다. 아주 단순한 기능 여럿은 하나로 묶어도 된다(묶은 번호를 제목에 적는다).
- 흐름: 시작(누가·무엇이 시작하나) → 단계 → 조건 분기 → 결과(사용자가 보는 것)
- 단계마다 어디서 일어나는지 붙인다: `[화면]`, `[서버]`, `[DB]`, `[외부]`
- 도식 하나에 노드는 12개 이내로 한다. 도식 아래에 한 줄 설명을 붙인다.
- fleet 작업의 흐름도(`flow`: trigger → steps → outputs)가 있으면 초안으로 쓰고, 코드와 대조해 지금 동작과 다른 곳을 고친다. 같은 기능의 흐름도가 여럿이면 최신 것을 기준으로 한다.
- **접고 펼 수 있게** 만든다. 플로우차트마다 `<details class="flow"><summary>번호 기능 이름 · 상태 칩 · 한 줄 요약</summary> 도식·설명 </details>`로 감싸고 처음엔 접어 둔다. 장 맨 위에 `모두 펼치기`·`모두 접기` 버튼을 둔다.
- 접힌 칸 안의 도식은 크기를 잴 수 없어 깨지므로, 펼칠 때 그린다(뼈대의 스크립트가 처리한다).

### 4. 시스템 아키텍처
- mermaid `flowchart LR` 하나: 사용자(브라우저·앱) → 서버·워커 → DB·저장소 → 외부 서비스. 화살표에 통신 방식(HTTPS, WebSocket, SQL, 큐)을 적는다
- 표: `구성요소 | 맡는 일 | 기술·버전 | 위치(파일·폴더)`
- **의존성 트리**: `<pre class="tree">`에 `├──`·`└──` 줄로 그린다. 묶음은 아래 순서로 하고, 없는 묶음은 뺀다.
  - 화면(브라우저): CDN 라이브러리와 쓰는 하위 모듈, 외부 리소스
  - 서버·런타임: 플랫폼·프레임워크·라이브러리
  - 개발·시험: 빌드·배포 도구, 시험 도구(직접 의존성만 쓰고, 그 아래 주요 의존성은 한 단계만, 전체 개수를 덧붙인다)
  - 외부 서비스: 호출하는 API 주소(도메인까지)
  - 내부 모듈: 진입 파일부터 `import` 관계
- 버전은 잠금 파일·URL에 적힌 정확한 값을 쓴다. 범위(^1.2)만 있으면 그대로 적고, 모르면 `확인 필요`
- 배포 환경, 환경 변수 이름(값 없이), 보안 장치(인증, 권한, 제한)를 짧게 정리한다

### 5. ERD
- mermaid `erDiagram`으로 실제 표와 관계를 그린다. 관계 선에 짧은 한국어 이름을 붙인다.
- 표마다 열 표를 붙인다: `열 | 형 | 제약(PK·FK·UNIQUE·NOT NULL·CHECK) | 설명`
- 계획만 있고 아직 없는 표는 이름 끝에 `_planned`를 붙이고 그렇다고 적는다.
- 저장하지 않는 데이터(대화, 위치, 개인정보 등)가 있으면 따로 적는다.
- DB가 없으면 "DB 없음"이라고 쓰고, 데이터가 어디에 어떤 모양으로 있는지 표로 대신한다.

### 6. 진행 히스토리
- 표: `날짜 | 한 일 | 근거(커밋·작업 기록·대화)` — 오래된 것부터, 같은 날 비슷한 일은 한 줄로 묶는다. fleet 작업은 `#id`, 커밋은 짧은 해시로 적는다
- 남은 일(`todo`)·중단(`stopped`) 작업은 `다음 할 일`로 옮긴다
- 마지막에 `다음 할 일` 표: `할 일 | 맡은 사람(개발·운영 등) | 상태`

## 3단계: HTML 만들기
아래 뼈대를 쓴다. 색은 토큰으로만 정하고 밝은·어두운 화면을 둘 다 맞춘다. 표·도식은 가로로 넘치면 그 칸 안에서만 스크롤되게 한다.

```html
<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{프로젝트} 기획명세서</title>
<style>
:root{--bg:#f5f6f8;--paper:#fff;--ink:#1c2028;--muted:#5f6775;--line:#dde1e7;--accent:#2d5fa8;
--done:#2f7d5b;--done-bg:#e3f2ea;--wip:#9a5b12;--wip-bg:#fbeedd;--plan:#6b7280;--plan-bg:#eceef1}
@media (prefers-color-scheme:dark){:root{--bg:#12151b;--paper:#191d25;--ink:#e6e9ef;--muted:#9aa3b2;--line:#2b313c;
--accent:#8db4f0;--done:#6fcf9f;--done-bg:#183026;--wip:#f0b86a;--wip-bg:#3a2a17;--plan:#a3abb8;--plan-bg:#242a34;color-scheme:dark}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 "Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:40px 16px 80px;display:grid;gap:24px}
section{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:24px;display:grid;gap:12px;min-width:0}
h1{margin:0;font-size:clamp(28px,5vw,40px)} h2{margin:0;font-size:22px} .meta,.muted{color:var(--muted);font-size:13px}
nav ul{display:flex;flex-wrap:wrap;gap:6px;list-style:none;padding:0;margin:0}
nav a{display:block;padding:3px 10px;border:1px solid var(--line);border-radius:999px;color:var(--ink);text-decoration:none;font-size:13px}
.scroll{overflow-x:auto} table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;vertical-align:top;padding:8px 10px;border-bottom:1px solid var(--line)} th{color:var(--muted);font-size:12px;white-space:nowrap}
code{font:12.5px ui-monospace,Menlo,monospace;background:var(--bg);padding:1px 5px;border-radius:4px}
.chip{display:inline-block;font-size:12px;font-weight:600;padding:1px 8px;border-radius:999px;white-space:nowrap}
.done{color:var(--done);background:var(--done-bg)} .wip{color:var(--wip);background:var(--wip-bg)} .plan{color:var(--plan);background:var(--plan-bg)}
pre.mermaid{background:var(--bg);border-radius:8px;padding:12px;margin:0;min-width:520px}
pre.tree{background:var(--bg);border-radius:8px;padding:14px 16px;margin:0;font:13px/1.6 ui-monospace,Menlo,monospace;overflow-x:auto}
details.flow{border:1px solid var(--line);border-radius:8px;padding:0 14px}
details.flow summary{cursor:pointer;padding:10px 0;font-weight:600} details.flow[open]{padding-bottom:14px}
.btns{display:flex;gap:8px} .btns button{font:inherit;font-size:13px;padding:3px 10px;border:1px solid var(--line);border-radius:6px;background:var(--paper);color:var(--ink);cursor:pointer}
</style></head><body><div class="wrap">
<header><div class="meta">기획명세서 · v0.1 · 기준일 YYYY-MM-DD</div><h1>{프로젝트}</h1><p>{한 줄 정의}</p>
<nav><ul><li><a href="#overview">개요</a></li><li><a href="#features">기능 명세</a></li><li><a href="#flows">기능별 플로우차트</a></li>
<li><a href="#architecture">시스템 아키텍처</a></li><li><a href="#erd">ERD</a></li><li><a href="#history">진행 히스토리</a></li></ul></nav></header>
<section id="overview"><h2>1. 개요</h2>…</section>
<section id="flows"><h2>3. 기능별 플로우차트</h2>
<div class="btns"><button type="button" data-all="open">모두 펼치기</button><button type="button" data-all="close">모두 접기</button></div>
<details class="flow"><summary>F-01 로그인 · <span class="chip done">완료</span> · 한 줄 요약</summary><div class="scroll"><pre class="mermaid">…</pre></div><p class="muted">설명</p></details>
</section>
<!-- features · architecture(.tree 포함) · erd · history 도 section 모양 -->
<p class="muted">도식이 글로만 보이면 인터넷 연결을 확인하세요(mermaid 를 불러와 그립니다).</p>
</div>
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs";
mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "default" });
// 보이는 도식만 그리고, 접힌 플로우차트는 펼칠 때 그린다(접힌 채 그리면 크기를 못 재 깨진다).
// 여러 개를 한꺼번에 펼쳐도 한 번에 하나씩 그린다(동시에 그리면 일부가 오류로 깨진다)
let queue = Promise.resolve();
const draw = (nodes) => { if (nodes.length) queue = queue.then(() => mermaid.run({ nodes })).catch(() => {}); };
const pending = (root) => [...root.querySelectorAll("pre.mermaid:not([data-processed])")];
draw(pending(document).filter((p) => !p.closest("details:not([open])")));
document.querySelectorAll("details.flow").forEach((d) => d.addEventListener("toggle", () => d.open && draw(pending(d))));
document.querySelectorAll("[data-all]").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll("details.flow").forEach((d) => { d.open = b.dataset.all === "open"; });
}));
</script></body></html>
```

mermaid를 쓸 때 지킬 것(어기면 도식이 깨진다):
- 노드 id는 영문·숫자로 짓고, 보이는 글은 큰따옴표 안에 쓴다: `A["로그인 [서버]"]`
- 글 안에 `"`, `<`, `>`는 쓰지 않는다. 줄바꿈은 `<br/>`만 쓴다
- `erDiagram`의 열 설명은 큰따옴표 안에 쓴다: `TEXT id PK "무작위 번호"`
- `pre.mermaid` 안의 `&`, `<`, `>`는 HTML 문자(`&amp;` 등)로 바꾼다

## 4단계: 점검과 보고
1. 파일을 쓴 뒤 다시 읽어 6장이 모두 있는지 확인한다. 기능 명세 번호와 플로우차트 번호도 서로 맞는지 확인한다.
2. 비밀 값이 들어가지 않았는지 `key|secret|token|password` 같은 낱말로 훑는다.
3. `humanize-korean:humanize-scan` 스킬이 있으면 본문 문장을 점검해 고친다(표 칸 낱말·코드 이름은 빼고).
4. 사용자에게 이렇게 알린다:
   - 파일의 전체 경로와 여는 명령(`! open <경로>`)
   - 장별 개수(기능 N개, 플로우차트 N개, 표 N개)
   - `확인 필요`로 남긴 항목 목록
