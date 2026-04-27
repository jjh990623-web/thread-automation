"""Threads 멘션·답글 수집.

Meta Threads Graph API:
  GET /{user-id}/mentions    — 나를 태그한 글
  GET /{user-id}/replies     — 내 글에 달린 답글
docs: https://developers.facebook.com/docs/threads/reply-management
"""

import os
from datetime import datetime
from typing import List, Optional

import requests

from .models import Mention

THREADS_API = "https://graph.threads.net/v1.0"


class ThreadsCollector:
    def __init__(
        self,
        access_token: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.access_token = access_token or os.getenv("THREADS_ACCESS_TOKEN")
        self.user_id = user_id or os.getenv("THREADS_USER_ID")
        self.dry_run = not (self.access_token and self.user_id)

    def fetch_mentions(self, since: datetime) -> List[Mention]:
        """`since` 이후의 멘션·답글을 합쳐 반환."""
        if self.dry_run:
            print("[collector] dry-run — 더미 멘션 1건 반환")
            return [
                Mention(
                    id="dryrun-mention-1",
                    author_username="tea_lover",
                    text="@호지프릭스 호지차 티백 너무 향이 좋네요!",
                    created_at=datetime.now(),
                )
            ]

        items = self._get_mentions(since) + self._get_replies(since)
        seen = set()
        unique: List[Mention] = []
        for m in items:
            if m.id not in seen:
                seen.add(m.id)
                unique.append(m)
        return unique

    def _get_mentions(self, since: datetime) -> List[Mention]:
        # TODO: 실제 endpoint 필드/페이지네이션 확인 후 채우기
        url = f"{THREADS_API}/{self.user_id}/mentions"
        params = {
            "fields": "id,username,text,timestamp,permalink",
            "since": int(since.timestamp()),
            "access_token": self.access_token,
        }
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        return [self._to_mention(d) for d in r.json().get("data", [])]

    def _get_replies(self, since: datetime) -> List[Mention]:
        # TODO: replies endpoint는 post 단위라 내 최근 글 id 목록 순회 필요.
        # 1차 스켈레톤에서는 빈 리스트.
        return []

    @staticmethod
    def _to_mention(d: dict) -> Mention:
        return Mention(
            id=d["id"],
            author_username=d.get("username", "unknown"),
            text=d.get("text", ""),
            created_at=datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
            if "timestamp" in d
            else datetime.now(),
            parent_post_id=d.get("root_post", {}).get("id") if isinstance(d.get("root_post"), dict) else None,
            permalink=d.get("permalink"),
        )
