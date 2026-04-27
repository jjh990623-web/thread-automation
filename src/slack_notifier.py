"""Slack 발송 — 초안 1건당 OK/Reject 버튼이 달린 메시지 1개."""

import os
from typing import List, Optional

from .models import Draft


class SlackNotifier:
    def __init__(self):
        self.token = os.getenv("SLACK_BOT_TOKEN")
        self.channel = os.getenv("SLACK_CHANNEL", "#thread-automation")
        self.dry_run = not self.token
        self._client = None

    @property
    def client(self):
        if self._client is None and not self.dry_run:
            from slack_sdk import WebClient
            self._client = WebClient(token=self.token)
        return self._client

    def send_draft(self, draft: Draft) -> Optional[str]:
        """초안을 Slack에 전송하고 메시지 ts를 반환. dry-run이면 None."""
        if self.dry_run:
            print(f"[slack] dry-run — {draft.type.value}/{draft.id[:8]} 전송 시뮬레이션")
            print(f"        본문: {draft.text}")
            return None

        resp = self.client.chat_postMessage(
            channel=self.channel,
            text=f"[{draft.type.value}] 새 초안 — 승인 필요",
            blocks=self._build_blocks(draft),
        )
        return resp["ts"]

    def send_published(self, draft: Draft, post_id: Optional[str]) -> None:
        if self.dry_run:
            print(f"[slack] dry-run — {draft.id[:8]} 게시완료 알림 시뮬레이션")
            return
        self.client.chat_postMessage(
            channel=self.channel,
            text=f"✅ 게시 완료: thread_id={post_id}",
            thread_ts=draft.slack_ts,
        )

    @staticmethod
    def _build_blocks(draft: Draft) -> List[dict]:
        header = f"*[{draft.type.value}]* {draft.created_at:%Y-%m-%d %H:%M}\n_ID: `{draft.id}`_"
        if draft.reply_to:
            header += (f"\n→ @{draft.reply_to.author_username}: "
                       f"{draft.reply_to.text[:80]}")
        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": header}},
            {"type": "section",
             "text": {"type": "mrkdwn", "text": f"```{draft.text}```"}},
            {"type": "actions", "elements": [
                {"type": "button",
                 "text": {"type": "plain_text", "text": "수정/게시"},
                 "style": "primary",
                 "action_id": "approve_draft",
                 "value": draft.id},
                {"type": "button",
                 "text": {"type": "plain_text", "text": "Reject"},
                 "style": "danger",
                 "action_id": "reject_draft",
                 "value": draft.id},
            ]},
        ]
