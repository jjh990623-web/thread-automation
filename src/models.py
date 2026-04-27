from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class PostType(str, Enum):
    DAILY = "daily"     # 일상 글
    PROMO = "promo"     # 제품 홍보
    REPLY = "reply"     # 멘션·답글에 대한 답변


class DraftStatus(str, Enum):
    PENDING = "pending"        # Slack 전송, 승인 대기
    APPROVED = "approved"      # OK 받음 — 게시 직전
    REJECTED = "rejected"      # 거절
    PUBLISHED = "published"    # 게시 완료


class Mention(BaseModel):
    """수집된 멘션·답글 1건."""
    id: str
    author_username: str
    text: str
    created_at: datetime
    parent_post_id: Optional[str] = None   # 내 글에 달린 답글이면 그 글 id
    permalink: Optional[str] = None


class Draft(BaseModel):
    """LLM이 생성한 초안 1건."""
    id: str
    type: PostType
    text: str
    created_at: datetime
    status: DraftStatus = DraftStatus.PENDING
    reply_to: Optional[Mention] = None     # type == REPLY 일 때만
    slack_ts: Optional[str] = None         # OK 후 follow-up 메시지에 사용
    published_post_id: Optional[str] = None
    rejection_reason: Optional[str] = None
