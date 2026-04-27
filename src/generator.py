"""브랜드 보이스 기반 초안 생성 (Claude API).

비용 최적화: system 블록에 cache_control(5분 TTL)을 걸어 brand_tone + 과거 글 prefix를
캐시한다. 같은 run 안에서 daily/promo 두 호출이 system을 공유하므로 두 번째 호출은
cache hit으로 input 토큰의 ~90%가 0.1× 단가로 처리된다. Sonnet 4.6의 최소 캐시
prefix는 2048토큰 — 과거 글이 충분히 누적된 후에만 캐시가 실제로 활성화된다.
"""

import os
import uuid
from datetime import datetime
from typing import List, Optional

import yaml

from .models import Draft, Mention, PostType


class ContentGenerator:
    def __init__(
        self,
        brand_voice_path: str = "config/brand_voice.yaml",
        prompts_path: str = "config/prompts.yaml",
    ):
        with open(brand_voice_path, "r", encoding="utf-8") as f:
            self.brand_voice = yaml.safe_load(f)
        with open(prompts_path, "r", encoding="utf-8") as f:
            self.prompts = yaml.safe_load(f)

        # 브랜드 톤 본문은 .md 파일에서 통째로 읽어 system prompt로 사용
        brand_tone_path = self.brand_voice.get("brand_tone_path", "config/brand_tone.md")
        with open(brand_tone_path, "r", encoding="utf-8") as f:
            self.brand_tone = f.read().strip()

        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self.dry_run = not self.api_key
        self._client = None  # lazy

    @property
    def client(self):
        if self._client is None and not self.dry_run:
            import anthropic  # 지연 import — dry-run에서는 패키지 없어도 동작
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def generate_post(
        self,
        post_type: PostType,
        recent_topics: Optional[List[str]] = None,
    ) -> Draft:
        if post_type == PostType.REPLY:
            raise ValueError("REPLY 타입은 generate_reply()를 사용하세요.")
        prompt = self.prompts[post_type.value]
        text = self._call_llm(prompt, recent_topics or [])
        return Draft(
            id=str(uuid.uuid4()),
            type=post_type,
            text=text,
            created_at=datetime.now(),
        )

    def generate_reply(self, mention: Mention) -> Draft:
        prompt = self.prompts["reply"].format(
            author=mention.author_username, text=mention.text
        )
        # 답글은 멘션 컨텍스트만 필요 — 과거 글 목록 불필요
        text = self._call_llm(prompt, recent_topics=[])
        return Draft(
            id=str(uuid.uuid4()),
            type=PostType.REPLY,
            text=text,
            created_at=datetime.now(),
            reply_to=mention,
        )

    def _call_llm(self, prompt: str, recent_topics: List[str]) -> str:
        if self.dry_run:
            return f"[dry-run 초안] {prompt.splitlines()[0][:60]}…"

        system_blocks = self._build_system_blocks(recent_topics)
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_blocks,
            messages=[{"role": "user", "content": prompt}],
        )

        u = msg.usage
        cw = u.cache_creation_input_tokens or 0
        cr = u.cache_read_input_tokens or 0
        print(
            f"[gen] tokens — cache_write={cw} cache_read={cr} "
            f"input={u.input_tokens} output={u.output_tokens}"
        )
        return msg.content[0].text.strip()

    def _build_system_blocks(self, recent_topics: List[str]) -> list:
        """system을 [brand_tone, recent_posts] 2블록으로 구성하고 끝에 cache_control."""
        blocks = [{"type": "text", "text": self.brand_tone}]
        if recent_topics:
            recent_md = self._format_recent(recent_topics)
            blocks.append({"type": "text", "text": recent_md})
        # 마지막 블록에 cache_control — prefix 전체(brand_tone + recent)가 캐시 대상
        blocks[-1]["cache_control"] = {"type": "ephemeral"}
        return blocks

    @staticmethod
    def _format_recent(recent_topics: List[str]) -> str:
        body = "\n\n".join(f"[{i+1}] {t}" for i, t in enumerate(recent_topics))
        return (
            "\n\n## 최근 게시한 글\n\n"
            "아래는 호지프릭스 계정에 이미 올라간 글들입니다. 새 글을 작성할 때는 "
            "이 목록과 **소재·어휘·문장 구조가 명확히 달라야** 합니다. "
            "같은 풍경·감각·계절감을 반복하지 마세요.\n\n"
            f"{body}\n"
        )
