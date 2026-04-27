"""파일 기반 저장소.

  data/초안.md          모든 초안의 타임로그
  data/투고목록.md       승인·게시된 일상/홍보글
  data/답글목록.md       승인·게시된 답글
  data/pending.json     Slack 승인 대기 중인 draft (id → Draft JSON)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .models import Draft, PostType


DATA_DIR = Path("data")
DRAFT_FILE = "초안.md"
POSTS_FILE = "투고목록.md"
REPLIES_FILE = "답글목록.md"
PENDING_FILE = "pending.json"


class DraftStorage:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

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
        pending = self._load_pending()
        pending[draft.id] = draft.model_dump(mode="json")
        self._write_pending(pending)

    def pop_pending(self, draft_id: str) -> Optional[Draft]:
        pending = self._load_pending()
        raw = pending.pop(draft_id, None)
        self._write_pending(pending)
        return Draft(**raw) if raw else None

    def get_pending(self, draft_id: str) -> Optional[Draft]:
        raw = self._load_pending().get(draft_id)
        return Draft(**raw) if raw else None

    # ── 내부 유틸 ────────────────────────────────────────────
    def _load_pending(self) -> Dict[str, dict]:
        path = self.data_dir / PENDING_FILE
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_pending(self, data: Dict[str, dict]) -> None:
        path = self.data_dir / PENDING_FILE
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")

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
