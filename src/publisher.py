"""Threads API 게시.

게시 절차 (2단계):
  1) POST /{user-id}/threads          — 컨테이너 생성 → creation_id
  2) POST /{user-id}/threads_publish  — creation_id 게시 → media_id (= thread id)
docs: https://developers.facebook.com/docs/threads/posts
"""

import os
from typing import Optional

import requests

from .models import Draft, PostType

THREADS_API = "https://graph.threads.net/v1.0"


class ThreadsPublisher:
    def __init__(self):
        self.access_token = os.getenv("THREADS_ACCESS_TOKEN")
        self.user_id = os.getenv("THREADS_USER_ID")
        self.dry_run = not (self.access_token and self.user_id)

    def publish(self, draft: Draft) -> Optional[str]:
        if self.dry_run:
            print(f"[publisher] dry-run — {draft.type.value}/{draft.id[:8]} 게시 시뮬레이션")
            print(f"            본문: {draft.text}")
            return None

        creation_id = self._create_container(draft)
        return self._publish_container(creation_id)

    def _create_container(self, draft: Draft) -> str:
        data = {
            "media_type": "TEXT",
            "text": draft.text,
            "access_token": self.access_token,
        }

        # 답글 타입이면 원글 ID를 reply_to_id로 추가
        if draft.type == PostType.REPLY and draft.reply_to and draft.reply_to.parent_post_id:
            data["reply_to_id"] = draft.reply_to.parent_post_id

        r = requests.post(
            f"{THREADS_API}/{self.user_id}/threads",
            data=data,
            timeout=15,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Threads API {r.status_code}: {r.text}")
        return r.json()["id"]

    def _publish_container(self, creation_id: str) -> str:
        r = requests.post(
            f"{THREADS_API}/{self.user_id}/threads_publish",
            data={
                "creation_id": creation_id,
                "access_token": self.access_token,
            },
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["id"]
