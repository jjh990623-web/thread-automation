# 호지프릭스 Thread 자동화 도구 — 설정 가이드

## 🎯 현재 상태

API 결제 완료 ✓ — 다음 단계로 .env 파일을 구성하여 dry-run을 실제 API 호출로 전환합니다.

---

## 📋 필요한 API 자격증명

### 1. Claude API (Anthropic) ✓ READY

**상태:** 준비됨

```
ANTHROPIC_API_KEY=sk-ant-... (API목록.md에서 복사)
ANTHROPIC_MODEL=claude-sonnet-4-6  # 기본값 (변경 불필요)
```

**목적:** 브랜드 톤 기반 초안 생성 (daily/promo/reply)

---

### 2. Slack Bot Token ✓ READY

**상태:** 준비됨

```
SLACK_BOT_TOKEN=xoxb-... (API목록.md에서 복사)
SLACK_CHANNEL=#thread-automation  # 변경 가능 — 초안 통지를 받을 채널
SLACK_SIGNING_SECRET=... (API목록.md에서 복사)
```

**목적:** Slack에 초안 전송 + 사용자 승인/거절 대기

**필요 권한(scopes):** `chat:write`, `chat:write.public`

⚠️ **다음 확인:**
- Slack workspace에서 자동화 채널(`#thread-automation` 등)이 존재하는가?
- Bot이 그 채널에 초대되어 있는가? (`/invite @bot-name`)

---

### 3. Threads (Meta Graph API) ⚠️ PARTIALLY READY

**상태:** ACCESS_TOKEN 준비됨 (API목록.md), USER_ID 필요

```
THREADS_ACCESS_TOKEN=THA... (API목록.md에서 복사)
THREADS_USER_ID=18000000000000000  # Meta for Developers에서 조회
```

**목적:** 호지프릭스 Threads 계정에 글 게시

**USER_ID 얻는 방법:**

1. [Meta for Developers](https://developers.facebook.com/) 접속
2. 앱 설정 → Graph API Explorer 이동
3. 왼쪽 드롭다운에서 "Threads User ID" 선택
4. 쿼리 실행 후 반환된 ID 복사

또는 Threads 계정이 연결된 Instagram 계정이 있다면:
```bash
# curl로 조회
curl -X GET "https://graph.threads.net/v1.0/me?fields=id&access_token=YOUR_ACCESS_TOKEN"
```

응답 예:
```json
{
  "id": "18000000000000000"
}
```

---

## 🔧 설정 방법

### Step 1: Python 의존성 설치

```bash
python -m pip install -r requirements.txt
```

### Step 2: .env 파일 생성

`.env.example`을 복사하여 `.env` 파일을 만들고 다음 값들을 채웁니다:

```bash
cp .env.example .env
```

텍스트 에디터에서 `.env` 열고:

```env
# ── Anthropic (Claude) ──
ANTHROPIC_API_KEY=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
ANTHROPIC_MODEL=claude-sonnet-4-6

# ── Threads (Meta Graph API) ──
THREADS_ACCESS_TOKEN=THAANi6eSCpddBYlprbjFtSWdGWFUweGZAwajlnaktJLWhEbmpqNW1RamRsV3RpOUU5OC1mWVNrdzFELTB1cnBNdHgyWEhZAb0E4YmVURzZAKeTNKckJ5YU9mN2cxZAnJHWWpLVlc0R2szZA3V5NUsySmR2Tm5ya08tWi1yV04tbWJ2MFlQLU82ZAXE1V2FzS3VEOUFaUURSREZADRENlNDZAUMWdqRU5mR1oZD
THREADS_USER_ID=18000000000000000  # ← 여기에 위에서 얻은 USER_ID 붙여넣기

# ── Slack ──
SLACK_BOT_TOKEN=xoxb-10997455338677-11029144245952-twAESBLc3BSPylmMYQIiQiIf
SLACK_CHANNEL=#thread-automation
SLACK_SIGNING_SECRET=
```

### Step 3: Slack 채널 확인

- Slack workspace에서 `#thread-automation` 채널(또는 선택한 채널) 생성
- 해당 채널에 자동화 bot 초대

### Step 4: 테스트 실행

THREADS_USER_ID를 얻기 전에, Claude + Slack만 먼저 테스트:

```bash
python -m src.main run --type reply-only
```

이 명령은:
- 멘션/답글 수집 (Threads 필요 ❌)
- 답글 초안 생성 (Claude ✓)
- Slack에 초안 전송 (Slack ✓)

성공하면 Slack에서 답글 초안이 나타날 것입니다. Threads 미설정으로 인한 에러는 무시해도 괜찮습니다.

### Step 5: 전체 파이프라인 활성화

THREADS_USER_ID를 .env에 추가한 후:

```bash
python -m src.main run --type all
```

또는 특정 시간에 특정 타입만:

```bash
python -m src.main run --type daily    # 아침에 실행
python -m src.main run --type promo    # 저녁에 실행
python -m src.main run --type reply-only  # 항상
```

---

## 📊 실행 흐름

```
python -m src.main run
  ↓
  ├─ 1) Threads 멘션/답글 수집 (THREADS_ACCESS_TOKEN, THREADS_USER_ID)
  ├─ 2) Claude로 초안 생성 (ANTHROPIC_API_KEY)
  ├─ 3) 검증 (금지어, 중복 등)
  └─ 4) Slack에 초안 전송 + pending 큐 저장 (SLACK_BOT_TOKEN)
       ↓ [사용자가 Slack에서 OK 클릭]
       ↓
  python -m src.main approve <draft_id>
  └─ 5) Threads에 게시 (THREADS_ACCESS_TOKEN)
  └─ 6) 투고목록.md에 기록
```

---

## ✅ 체크리스트

- [ ] `requirements.txt` 설치 완료
- [ ] Claude API 키 복사 → `.env` ANTHROPIC_API_KEY
- [ ] Slack Bot Token 복사 → `.env` SLACK_BOT_TOKEN
- [ ] Threads Access Token 복사 → `.env` THREADS_ACCESS_TOKEN
- [ ] Threads User ID 조회 → `.env` THREADS_USER_ID
- [ ] Slack 채널 생성 및 bot 초대
- [ ] `python -m src.main run --type reply-only` 테스트 (답글 초안만)
- [ ] `python -m src.main run --type all` 테스트 (전체 파이프라인)

---

## 🔄 스케줄러 설정 (옵션)

매일 자동 실행을 원한다면:

**Windows Task Scheduler:**
- 작업 생성 → 프로그램/스크립트: `python`
- 인수: `-m src.main run --type daily`
- 경로: 프로젝트 루트 디렉터리
- 아침 9시에 실행 (또는 원하는 시간)

**Linux/Mac (cron):**
```bash
0 9 * * * cd /path/to/project && python -m src.main run --type daily
0 18 * * * cd /path/to/project && python -m src.main run --type promo
```

---

## ⚠️ 문제 해결

**"THREADS_USER_ID 없음" 에러:**
- User ID를 Meta for Developers에서 조회 후 `.env`에 추가

**Slack 메시지가 안 보임:**
- SLACK_CHANNEL이 정확한가? (#thread-automation)
- bot이 그 채널에 초대되어 있는가?
- SLACK_BOT_TOKEN이 유효한가?

**Claude 호출 오류:**
- ANTHROPIC_API_KEY가 올바른가?
- 결제가 활성화되어 있는가? (Claude Console 확인)

---

이제 필요한 API 자격증명을 준비하고 위 체크리스트를 따라가세요! 🚀
