"""저장소: Supabase REST API (pending) + 파일 (로그)."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests

from .models import Draft, PostType


DATA_DIR = Path("data")
DRAFT_FILE = "초안.md"
POSTS_FILE = "투고목록.md"
REPLIES_FILE = "답글목록.md"


class DraftStorage:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Supabase REST API 설정
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        self.has_supabase = bool(self.supabase_url and self.supabase_key)

    # ── 초안 로그 ────────────────────────────────────────────
    def append_draft(self, draft: Draft) -> None:
        with open(self.data_dir / DRAFT_FILE, "a", encoding="utf-8") as f:
            f.write(self._format_draft(draft))

    # ── 게시 로그 ────────────────────────────────────────────
    def append_published(self, draft: Draft, post_id: Optional[str]) -> None:
        target = REPLIES_FILE if draft.type == PostType.REPLY else POSTS_FILE
        with open(self.data_dir / target, "a", encoding="utf-8") as f:
            f.write(self._format_published(draft, post_id))

    # ── 최근 본문 조회 (validator용) ────────────────────────
    def recent_post_texts(self, n: int = 20) -> List[str]:
        path = self.data_dir / POSTS_FILE
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8")
        bodies = self._extract_bodies(text)
        return bodies[-n:]

    # ── 승인 대기 큐 (Slack 인터랙션용) ──────────────────────
    def save_pending(self, draft: Draft) -> None:
        """Supabase pending 테이블에 저장 (REST API)."""
        if not self.has_supabase:
            print("[warn] Supabase 미연결, pending 저장 생략")
            return

        try:
            reply_to = None
            if draft.reply_to:
                reply_to = {
                    "id": draft.reply_to.id,
                    "author_username": draft.reply_to.author_username,
                    "text": draft.reply_to.text,
                    "created_at": draft.reply_to.created_at.isoformat(),
                    "parent_post_id": draft.reply_to.parent_post_id,
                    "permalink": draft.reply_to.permalink,
                }
            payload = {
                "draft_id": draft.id,
                "type": draft.type.value,
                "text": draft.text,
                "created_at": draft.created_at.isoformat(),
                "slack_ts": draft.slack_ts,
                "reply_to": reply_to,
                "status": draft.status.value,
            }
            url = f"{self.supabase_url}/rest/v1/pending"
            headers = {
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            print(f"[db] pending 저장: {draft.id[:8]}")
        except Exception as e:
            print(f"[err] pending 저장 실패: {e}")

    def pop_pending(self, draft_id: str) -> Optional[Draft]:
        """Supabase에서 조회 후 삭제 (REST API)."""
        if not self.has_supabase:
            print("[warn] Supabase 미연결, pending 조회 생략")
            return None

        try:
            headers = {
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
            }
            # 조회
            url = f"{self.supabase_url}/rest/v1/pending?draft_id=eq.{draft_id}"
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                print(f"[err] pending에 {draft_id[:8]} 없음")
                return None

            draft = self._row_to_draft(data[0])

            # 삭제
            url = f"{self.supabase_url}/rest/v1/pending?draft_id=eq.{draft_id}"
            headers["Prefer"] = "return=minimal"
            resp = requests.delete(url, headers=headers, timeout=10)
            resp.raise_for_status()
            print(f"[db] pending 제거: {draft_id[:8]}")

            return draft
        except Exception as e:
            print(f"[err] pending 조회/삭제 실패: {e}")
            return None

    def get_pending(self, draft_id: str) -> Optional[Draft]:
        """Supabase에서 조회만 (삭제 없음) - REST API."""
        if not self.has_supabase:
            return None

        try:
            headers = {
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
            }
            url = f"{self.supabase_url}/rest/v1/pending?draft_id=eq.{draft_id}"
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if not data:
                return None
            return self._row_to_draft(data[0])
        except Exception as e:
            print(f"[err] pending 조회 실패: {e}")
            return None

    # ── 내부 유틸 ────────────────────────────────────────────
    @staticmethod
    def _row_to_draft(row: dict) -> Draft:
        """DB 행을 Draft 객체로 변환."""
        from .models import DraftStatus, Mention

        reply_to = None
        if row.get("reply_to"):
            mention_data = row["reply_to"]
            reply_to = Mention(
                id=mention_data.get("id"),
                author_username=mention_data.get("author_username"),
                text=mention_data.get("text"),
                created_at=mention_data.get("created_at"),
                parent_post_id=mention_data.get("parent_post_id"),
                permalink=mention_data.get("permalink"),
            )

        return Draft(
            id=row["draft_id"],
            type=PostType(row["type"]),
            text=row["text"],
            created_at=datetime.fromisoformat(row["created_at"]),
            slack_ts=row.get("slack_ts"),
            reply_to=reply_to,
            status=DraftStatus(row.get("status", "pending")),
            published_post_id=row.get("published_post_id"),
        )

    @staticmethod
    def _format_draft(d: Draft) -> str:
        head = (f"### [{d.type.value}] {d.created_at:%Y-%m-%d %H:%M:%S}\n"
                f"- id: `{d.id}`\n- status: {d.status.value}\n")
        if d.reply_to:
            head += f"- reply_to: @{d.reply_to.author_username} — {d.reply_to.text[:60]}\n"
        return f"{head}\n{d.text}\n\n---\n\n"

    @staticmethod
    def _format_published(d: Draft, post_id: Optional[str]) -> str:
        head = (f"### [{d.type.value}] {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                f"- draft_id: `{d.id}`\n- thread_id: `{post_id or 'dry-run'}`\n")
        if d.reply_to:
            head += f"- reply_to: @{d.reply_to.author_username}\n"
        return f"{head}\n{d.text}\n\n---\n\n"

    @staticmethod
    def _extract_bodies(md: str) -> List[str]:
        """`---` 구분자로 나뉜 각 블록에서 메타라인을 제외한 본문을 뽑는다."""
        bodies: List[str] = []
        for block in md.split("\n---\n"):
            block = block.strip()
            if not block:
                continue
            lines = [
                ln for ln in block.splitlines()
                if not ln.startswith(("###", "- "))
            ]
            body = "\n".join(lines).strip()
            if body:
                bodies.append(body)
        return bodies
