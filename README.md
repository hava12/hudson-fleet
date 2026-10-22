# hudson-fleet

내 PC에서 돌고 있는 Claude Code 세션들을 한 화면에서 보는 로컬 대시보드입니다.

살아 있는 세션의 상태, 서브에이전트, 작업 내용, 연결된 MCP 서버를 봅니다.

## 설치 (Claude Code 플러그인)

```
/plugin install hudson-fleet --marketplace hava12/hudson-fleet
```

Claude Code 2.1.275 이전이면 두 단계로 설치합니다.

```
/plugin marketplace add hava12/hudson-fleet
/plugin install hudson-fleet@hudson-fleet
```

설치하면 세 가지가 함께 들어옵니다.

- **SessionStart 훅**: 세션이 시작될 때 대시보드 서버(8765)가 없으면 백그라운드로 띄웁니다. 세션이 다 끝나도 서버는 남습니다. 플러그인을 업데이트했다면 떠 있는 서버를 한 번 꺼야 새 코드로 뜹니다.
- **MCP 서버 `fleet`**: 에이전트가 작업을 시작·완료·중단·반려할 때 직접 기록합니다 (아래 "작업 기록").
- **Bash 훅** (`hooks/bash_files.py`): Bash 실행 전후로 작업 폴더를 훑어, 그 사이 수정 시각이 바뀐 파일을 바뀐 파일 목록에 넣습니다. 대화 기록에는 Bash 가 바꾼 파일이 드러나지 않기 때문입니다.

브라우저에서 http://127.0.0.1:8765 를 엽니다.

## 직접 실행

```sh
python3 server.py   # → http://127.0.0.1:8765
```

- Python 3.9 이상, 표준 라이브러리만 씁니다.
- `claude` CLI가 PATH에 있어야 합니다.
- 그래프 라이브러리(cytoscape, dagre)는 CDN에서 받으므로 인터넷 연결이 필요합니다.

## 작업 기록 (MCP)

| 도구 | 하는 일 |
|---|---|
| `task_start(text, tag)` | 작업을 시작하며 한 행을 만든다. id 를 돌려준다 |
| `task_update(id, status, note?)` | done 완료 · stopped 중단 · rejected 반려 · todo 남은 일 |
| `task_list()` | 이 세션의 작업 목록 (압축 뒤 이어받기) |

어느 세션의 호출인지는 MCP 서버의 부모 프로세스(claude)로 찾습니다. `~/.claude/sessions/<pid>.json`의 `sessionId`를 읽으므로 에이전트가 세션 ID를 몰라도 됩니다.

에이전트가 기록하지 않은 세션만 haiku 가 대화에서 작업을 정리합니다. 웹에서 분류·태그를 바꾸거나 지울 수 있고, 사람이 고친 행은 다시 정리할 때도 남습니다.

태그는 일의 종류입니다: 개발 · 디자인 · 기획 · 테스트 · 문서 · 디버그 · 데이터 · 운영 · 기타. 정의는 `fleet/tasks.py` 의 `TAGS` 한 곳에 있고, MCP 도구 설명과 haiku 프롬프트가 같은 표를 씁니다. 목록에 없는 값은 기타로 저장합니다.

## 기능

상단 메뉴는 **현황 · 세션 기록 · MCP 서버** 세 개이고, 오른쪽 위에 구독 사용량(5시간·1주일)을 작게 보여 줍니다.

**현황** (5초마다 갱신, 끝났거나 실패한 세션과 1회성 `claude -p` 실행은 빼고 보여 줍니다)

- **상태별 노드**: 프로젝트 → 세션 → 실행 중인 서브에이전트. 세션 색은 상태(작업 중·입력 대기·쉬는 중)입니다.
- **숫자 타일**: 상태별 세션 수와 서브에이전트 수. 누르면 그 상태의 세션만 표와 그래프에 남깁니다.
- **위치별 실행 중인 세션**: 작업 폴더별 표. 실행 앱(IntelliJ IDEA, Ghostty 등)과 종료 버튼이 있습니다.
- **작업 현황 리스트**: 세션마다 정리된 작업 3건(완료·중단·남은 일)과 바뀐 파일 수. 더보기는 오른쪽 패널에서 전체를 엽니다.
- **오른쪽 패널** (폭 조절 가능): 세션 제목, 기록할 작업, 바뀐 파일 트리(A 생성·M 수정·D 삭제), 파일마다 "처음 → 지금" diff.

**세션 기록**

- 대시보드 서버가 켜져 있는 동안 끝난 세션을 1분 안에 저장합니다. 종료 이유, 토큰, 기록할 작업, 바뀐 파일을 남깁니다.
- **다시 열기**: 상세 패널의 [이어서 열기]는 같은 세션 ID 로(`claude --resume`), [복사해 열기]는 기록을 남긴 채 새 ID 로(`--fork-session`) 터미널 새 창에서 엽니다.

**MCP 서버**

- `claude mcp list` 결과를 출처별(claude.ai 커넥터·플러그인·직접 설정) 그래프로 그립니다. 색은 연결 상태입니다.

작업 정리(haiku)는 버튼을 누를 때와 세션이 끝날 때만 실행되며 Claude 구독 사용량을 씁니다.

## 설정 (환경 변수)

모두 환경 변수로 정합니다. `~/.claude/settings.json` 의 `"env"` 에 적으면 Claude Code 가 훅·MCP 서버에 넘겨 주고, 훅이 띄우는 대시보드 서버도 같은 값을 받습니다. 바꾼 뒤에는 떠 있는 서버를 끄면 다음 세션 시작 때 새 값으로 뜹니다. 지금 적용된 값은 웹의 **설정** 메뉴에서 봅니다.

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `HUDSON_FLEET_PORT` | `8765` | 대시보드 서버 포트 |
| `HUDSON_FLEET_DB` | `~/.local/share/hudson-fleet/metrics.db` | SQLite 파일 경로 |
| `HUDSON_FLEET_AUTO_SUMMARY` | `1` | 에이전트 기록이 없는 세션이 끝날 때 AI 로 작업 정리. `0` 이면 끔 |
| `HUDSON_FLEET_SUMMARY_MODEL` | `haiku` | 작업 정리에 쓰는 모델 |
| `HUDSON_FLEET_RETENTION_DAYS` | `0` | 1분 지표(samples) 보관 일수. `0` 이면 지우지 않음 |
| `HUDSON_FLEET_TERMINAL` | `Ghostty` | 끝난 세션을 다시 열 터미널 앱: `Ghostty` 또는 `Terminal` |

## 데이터

SQLite 파일 하나에 저장합니다 (`HUDSON_FLEET_DB`).

| 표 | 내용 |
|---|---|
| `sessions` | 세션 1행. 상태(work·wait·idle·closed)와 그 상태가 된 시각, 종료 이유, 토큰 |
| `session_tasks` | 세션의 기록할 작업 N행. 표시 순서(`sort`), 분류(todo·done·stopped·rejected), 태그(`tag`, 일의 종류), 기록 주체(agent·haiku·human) |
| `task_events` | 작업마다 시작·완료·중단·반려·삭제 이력 (추가만) |
| `session_files` | 세션이 바꾼 파일 N행. A/M/D, 편집 횟수, 추가·삭제 줄 수 |
| `samples` | 1분마다 상태별 세션 수, 서브에이전트 수, 5시간·1주일 사용률 |
| `daily` | 날짜별 토큰 합계 (캐시 읽기 제외) |

## 코드 구조

`server.py` 는 실행 진입점이고, 기능은 `fleet/` 에 나뉘어 있습니다. 위층은 아래층만 가져다 씁니다 (거꾸로 가져오면 순환 import).

| 파일 | 하는 일 |
|---|---|
| `fleet/config.py` | 환경 변수 설정, 경로, `claude` CLI 호출 |
| `fleet/db.py` | SQLite 표 만들기, 제목·지표 조회 |
| `fleet/transcripts.py` | 대화 기록(`.jsonl`) 읽기: 개요, 편집 이벤트, 토큰 |
| `fleet/agents.py` | 살아 있는 세션: `claude agents`, 프로세스, 그래프, MCP 상태, 다시 열기 |
| `fleet/files.py` | 세션이 바꾼 파일의 A/M/D 와 "처음 → 지금" diff |
| `fleet/tasks.py` | 작업 기록(추가·수정·조회)과 haiku 정리, `TAGS` |
| `fleet/usage.py` | `/usage` 사용률, 세션별 5시간 몫, 날짜별 토큰 |
| `fleet/pushes.py` | Claude 가 실행한 git push 기록 |
| `fleet/recorder.py` | 1분 주기 기록 스레드: 지표, 세션 상태, 끝난 세션 마감 |
| `fleet/web.py` | HTTP API 와 화면 |
| `mcp_server.py` | 작업 기록 MCP 서버 (stdio). `fleet/tasks.py` 로 DB 에 바로 씁니다 |

```
6  recorder · web
5  tasks
4  files
3  agents · usage · pushes
2  transcripts
1  db
0  config
```

## API

| 경로 | 내용 |
|---|---|
| `GET /api/sessions?status=closed\|work\|wait\|idle&limit=50` | 세션과 작업·파일 목록 |
| `GET /api/pushes?limit=200` | Claude 가 실행한 git push (시각·레포·브랜치·커밋 메시지·세션). 대화 기록이 지워져도 DB 에 남습니다 |
| `GET /api/metrics?hours=24` | 1분 단위 지표 |
| `GET /api/daily` | 날짜별 토큰 (최근 1년) |
| `GET /api/usage` | 5시간·1주일 사용률 (`/usage` 결과) |
| `GET /api/mcp` | MCP 서버 연결 상태 |
| `GET /api/config` | 지금 적용된 설정 값 |

## 보안

- 서버는 `127.0.0.1`에서만 열립니다.
- 다른 출처(Origin)에서 오는 POST 요청은 거부합니다.
- 파일 열람은 그 세션이 편집한 파일만 허용합니다.
- 종료는 `claude agents` 목록에 있는 세션만 할 수 있습니다.

## 한계

- 종료된 대화형 세션은 서버가 켜져 있을 때 끝난 것만 기록됩니다.
- 종료 이유 `exited`는 직접 종료·창 닫기·크래시를 구분하지 못합니다.
- Bash 가 바꾼 파일은 수정 시각으로만 찾습니다. 지운 파일은 못 잡고, Bash 가 도는 동안 사람이 고친 파일도 섞이며, 편집 조각(diff)이 없어 새로 만든 파일만 내용 비교가 됩니다. `.git`·`node_modules`·`build` 등은 건너뛰고 한 번에 5만 개까지만 훑습니다.
- 서브에이전트 실행 여부(`meta.json`의 `finished`)와 "처음" 파일 상태(`~/.claude/file-history`)는 공식 형식이 아니라 바뀔 수 있습니다.
- MCP 목록은 홈 폴더 기준입니다. 프로젝트에만 설정한 서버는 빠질 수 있습니다.
