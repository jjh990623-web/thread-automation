# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

'호지프릭스' 호지차 티백 브랜드의 Thread SNS 마케팅 자동화 도구. 원본 요구사항은 [프로그램 개발 요청서.md](프로그램 개발 요청서.md) 참고. 6단계 파이프라인(수집 → 생성 → 검사 → 초안 저장/Slack → 사용자 승인 → Threads 게시)을 Python으로 구현.

## 명령어

```bash
python -m pip install -r requirements.txt
cp .env.example .env                       # 키는 비워두면 dry-run

python -m src.main run                     # 1~4단계: 답글 + daily + promo
python -m src.main run --type daily        # 답글 + daily만
python -m src.main run --type promo        # 답글 + promo만
python -m src.main run --type reply-only   # 답글만 (게시글 생성 없음)
python -m src.main approve <draft_id>      # 6단계: pending에서 꺼내 Threads 게시
python -m src.main reject  <draft_id>      # pending에서만 제거
```

`--type`은 게시글 생성만 제한한다 — 멘션/답글 수집과 답글 초안 생성은 매 run에서 항상 실행된다. 스케줄러는 시간대별로 적절한 타입을 골라 호출한다 (예: 아침 daily, 저녁 promo).

`.env`의 `ANTHROPIC_API_KEY` / `THREADS_*` / `SLACK_BOT_TOKEN` 중 어느 하나라도 비어 있으면 그 모듈은 **dry-run**으로 떨어져 실제 호출 대신 stdout 로그만 찍는다 — 부분적으로 키를 채워가며 단계별로 검증할 수 있다.

## 아키텍처

### 6단계 파이프라인과 모듈 매핑

| 단계 | 모듈 | 호출되는 명령 |
|---|---|---|
| 1. 멘션·답글 수집 | [src/collector.py](src/collector.py) | `run` |
| 2. 브랜드 톤 초안 생성 | [src/generator.py](src/generator.py) + [config/](config/) | `run` |
| 3. 금지어·중복·과한 홍보 검사 | [src/validator.py](src/validator.py) | `run` |
| 4. 초안.md 저장 + Slack 발송 | [src/storage.py](src/storage.py) + [src/slack_notifier.py](src/slack_notifier.py) | `run` |
| 5. Slack OK 체크 | (외부 인터랙션 서버 — 아직 미구현) | — |
| 6. 투고/답글목록.md + Threads 게시 | [src/storage.py](src/storage.py) + [src/publisher.py](src/publisher.py) | `approve` |

### 모듈 간 상태 전달이 일어나는 지점

- **`run` ↔ `approve`는 다른 프로세스다.** Slack 클릭은 별도 인터랙션 서버에서 들어오므로, 두 명령 사이의 상태는 `data/pending.json`(`storage.save_pending` / `pop_pending`)이 디스크에 들고 있다. 새 모듈을 추가할 때 in-memory 큐를 가정하면 안 된다.
- **validator는 `data/투고목록.md`에서 최근 본문을 역파싱해 입력으로 받는다.** [storage.py](src/storage.py)의 `recent_post_texts()` → `_extract_bodies()`가 `### …`/`- …` 메타라인을 걸러내고 본문만 추려준다. 게시 로그 포맷을 바꾸면 이 파서도 같이 손봐야 한다.
- **5단계(Slack OK)의 통합점은 `cmd_approve(draft_id)`다.** 어떤 인터랙션 서버를 붙이든 OK 버튼은 결국 이 함수에 draft_id를 전달하면 된다 — 독립 Bolt 앱이든 webhook이든 같은 진입점.

### 브랜드 보이스 / 검사 규칙의 출처

브랜드 말투(LLM system prompt)와 구조화된 규칙은 **분리되어 있다**:

- [config/brand_tone.md](config/brand_tone.md) — 페르소나·톤·금지/권장 사항 등 자유 형식. 파일 전체가 LLM의 system prompt로 그대로 들어간다.
- [config/brand_voice.yaml](config/brand_voice.yaml) — `banned_phrases`, `promo_keywords`, `max_promo_per_window`, `similarity_threshold`, `brand_tone_path` 등 코드가 직접 읽는 구조화된 값. validator도 여기를 읽는다.

`brand_voice.yaml`의 `brand_tone_path`만 바꾸면 어떤 markdown 파일이든 system prompt로 쓸 수 있다 — 사용자가 별도로 관리하는 브랜드 톤 문서를 그대로 가리키게 하는 것이 의도된 사용법.

[config/prompts.yaml](config/prompts.yaml)의 키(`daily`/`promo`/`reply`)는 `PostType` enum 값과 정확히 일치해야 한다 — `_build_post_prompt`가 `self.prompts[post_type.value]`로 직접 인덱스한다. 새 PostType을 추가하면 이 YAML 키도 같이 추가. `daily`/`promo` 템플릿은 `{recent_topics}`와 `{recent_count}` 두 placeholder를 받는다.

### 비답글 글의 중복 회피와 prompt caching

`daily`/`promo` 글은 [storage.py](src/storage.py)의 `recent_post_texts(n=50)`로 [data/투고목록.md](data/투고목록.md)에서 최근 본문 50건을 읽고 — **user prompt가 아니라 system block**으로 끼워 넣는다 ([generator.py:`_build_system_blocks`](src/generator.py)). 이 system 마지막 블록에 `cache_control: {type: "ephemeral"}` (5분 TTL)이 붙어 있어 같은 run 안에서 daily→promo 순서로 두 번 호출될 때 두 번째는 brand_tone + 과거 글 prefix 전체를 cache hit으로 처리한다 (input 토큰 단가 ~0.1×).

⚠️ Sonnet 4.6의 최소 캐시 prefix는 **2048 토큰**이라, brand_tone(~600 토큰) 단독으로는 silent miss다. 과거 글이 충분히 쌓여 system이 2048 토큰을 넘기 시작하면 캐시가 **자동으로** 활성화된다 — 활성화 여부는 `[gen] tokens — cache_write=N cache_read=M …` 로그로 확인. user prompt 템플릿(daily/promo)은 짧게 유지해야 캐시 hit률이 높아진다.

답글(`reply`)은 멘션 컨텍스트가 매번 달라 캐시 효과가 거의 없으므로 `recent_topics=[]`로 호출 — system은 brand_tone 단독.

validator의 Jaccard 유사도 검사는 사후 backstop이지 1차 방어선이 아니다 — 1차 방어는 system에 박힌 과거 글 목록 + 강한 프롬프트 지시.

### 호출 규칙

- `generator.generate_post(PostType.REPLY, …)`는 `ValueError`를 던진다. 답글은 반드시 `generate_reply(mention)`로 — `Mention` 컨텍스트가 필요하기 때문.
- `generator.client`는 lazy property로 `anthropic`을 지연 import한다. dry-run에서는 `anthropic` 패키지가 설치되지 않아도 동작한다 (`slack_sdk`도 동일 패턴).
- Threads 게시는 항상 2-step: `_create_container` → `_publish_container`. 단일 호출로 합치지 말 것 (Meta API 계약).

## 환경 관련 주의

- **Windows cp949 콘솔에서 UTF-8 강제**: [main.py](src/main.py)의 `main()`이 시작하자마자 `sys.stdout.reconfigure(encoding="utf-8")`를 호출한다. 새로운 진입점을 만들 때 이 호출이 빠지면 em-dash·이모지·한글 일부가 `UnicodeEncodeError`로 죽는다.
- **데이터 파일 이름은 한글이다** (`초안.md`, `투고목록.md`, `답글목록.md`). 파일명 상수는 [storage.py](src/storage.py) 상단에 모여 있다 — 영문으로 바꾸면 요청서 명세와 어긋난다.
- 이 디렉터리는 동시에 Obsidian vault이기도 하다 (`.obsidian/`). 데이터 .md 파일들이 Obsidian에서 그대로 열려 사용자가 직접 편집할 수 있다는 게 의도된 동작.

## 미완 영역 (TODO 마커)

- [src/collector.py:55](src/collector.py#L55) — Threads `replies` endpoint는 post 단위라 내 최근 글 id 목록을 순회해야 함. 현재 빈 리스트.
- [src/validator.py:43](src/validator.py#L43) — Jaccard 토큰 유사도는 한국어에 약함. 임베딩 cosine으로 교체 예정.
- Slack 인터랙션 서버(Bolt) 미구현 — OK 버튼 클릭이 `cmd_approve`로 라우팅되는 webhook 필요.
