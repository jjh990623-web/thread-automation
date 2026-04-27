"""호지프릭스 Thread SNS 자동화 — 진입점.

워크플로 (요청서 6단계):
  run     1) 멘션·답글 수집  2) 초안 생성  3) 검사  4) 초안.md + Slack 발송
  approve 5) Slack OK 후 호출되는 게시 명령
                           6) 투고목록.md / 답글목록.md 저장 + Threads 게시

사용 예:
  # 의존성 설치 (최초 1회)
  python -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  cp .env.example .env  # 필요한 키만 채우면 되고, 비워두면 dry-run

  # 파이프라인 1회 실행 (스케줄러 없이)
  python -m src.main run

  # Slack에서 OK 클릭 → 인터랙션 핸들러가 아래 호출
  python -m src.main approve <draft_id>
"""

import argparse
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

from .collector import ThreadsCollector
from .generator import ContentGenerator
from .models import Draft, DraftStatus, PostType
from .publisher import ThreadsPublisher
from .slack_notifier import SlackNotifier
from .storage import DraftStorage
from .validator import DraftValidator


def cmd_run(args) -> int:
    """전체 파이프라인 1회 실행. --type 으로 생성할 게시글 타입 제한."""
    collector = ThreadsCollector()
    generator = ContentGenerator()
    validator = DraftValidator()
    notifier = SlackNotifier()
    storage = DraftStorage()

    recent = storage.recent_post_texts(n=50)
    drafts: list[Draft] = []

    # 1) 멘션·답글 → 답글 초안 (--type 무관, 항상 처리)
    since = datetime.now() - timedelta(hours=24)
    for mention in collector.fetch_mentions(since):
        d = generator.generate_reply(mention)
        ok, reason = validator.validate(d, recent)
        if not ok:
            print(f"[skip reply] {d.id[:8]}: {reason}")
            continue
        drafts.append(d)

    # 2) 게시글: --type 에 따라 daily / promo / 둘 다 / 없음
    post_types: list[PostType] = []
    if args.type in ("all", "daily"):
        post_types.append(PostType.DAILY)
    if args.type in ("all", "promo"):
        post_types.append(PostType.PROMO)

    for ptype in post_types:
        d = generator.generate_post(ptype, recent_topics=recent)
        ok, reason = validator.validate(d, recent)
        if not ok:
            print(f"[skip {ptype.value}] {d.id[:8]}: {reason}")
            continue
        drafts.append(d)

    # 3) 초안 저장 + Slack 전송 + pending 큐에 등록
    for d in drafts:
        storage.append_draft(d)
        ts = notifier.send_draft(d)
        if ts:
            d.slack_ts = ts
        storage.save_pending(d)
        print(f"[ok] {d.type.value}/{d.id[:8]} → 초안.md 저장, Slack 전송")

    print(f"\n총 {len(drafts)}건 초안 처리 완료. Slack에서 OK 후 "
          f"`python -m src.main approve <draft_id>` 호출.")
    return 0


def cmd_approve(args) -> int:
    """Slack OK 후 호출 — pending 큐에서 꺼내 (모달에서 받은 수정본 적용 후) Threads 게시 + 게시 로그 기록."""
    edited_text = getattr(args, "edited_text", None)
    print(f"[2/5] cmd_approve 시작: draft_id={args.draft_id[:8]}")

    storage = DraftStorage()
    publisher = ThreadsPublisher()
    notifier = SlackNotifier()

    print(f"[2.1] pending 큐에서 draft 로드 중...")
    draft = storage.pop_pending(args.draft_id)
    if draft is None:
        print(f"[err] pending에 {args.draft_id} 없음", file=sys.stderr)
        return 1
    print(f"[2.2] draft 로드 성공: type={draft.type.value}")

    if edited_text and edited_text.strip() and edited_text.strip() != draft.text.strip():
        print(f"[2.3] 모달에서 수정된 본문 적용")
        draft.text = edited_text.strip()
    else:
        print(f"[2.3] 원본 본문 사용")

    print(f"[3/5] Threads 게시 시작...")
    draft.status = DraftStatus.APPROVED
    post_id = publisher.publish(draft)
    print(f"[3.5] Threads 게시 완료: post_id={post_id}")

    draft.published_post_id = post_id
    draft.status = DraftStatus.PUBLISHED

    print(f"[4/5] 게시 로그 저장 중...")
    storage.append_published(draft, post_id)
    notifier.send_published(draft, post_id)

    print(f"[ok] 게시 완료: draft={draft.id[:8]} thread_id={post_id}")
    return 0


def cmd_reject(args) -> int:
    """Slack Reject — pending 큐에서 제거만."""
    storage = DraftStorage()
    draft = storage.pop_pending(args.draft_id)
    if draft is None:
        print(f"[err] pending에 {args.draft_id} 없음", file=sys.stderr)
        return 1
    print(f"[ok] 거절 처리: {draft.id[:8]}")
    return 0


def main() -> int:
    # Windows 콘솔(cp949)에서 em-dash·이모지 등이 깨지지 않게 UTF-8로 고정
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    load_dotenv()

    p = argparse.ArgumentParser(prog="thread-automation")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="수집·생성·검사·Slack 발송")
    p_run.add_argument(
        "--type",
        choices=["all", "daily", "promo", "reply-only"],
        default="all",
        help="생성할 게시글 타입 (default: all). reply-only는 게시글 생성 없이 답글만 처리.",
    )
    p_run.set_defaults(func=cmd_run)

    p_app = sub.add_parser("approve", help="승인 후 Threads 게시")
    p_app.add_argument("draft_id")
    p_app.set_defaults(func=cmd_approve)

    p_rej = sub.add_parser("reject", help="거절 처리 (큐에서 제거)")
    p_rej.add_argument("draft_id")
    p_rej.set_defaults(func=cmd_reject)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
