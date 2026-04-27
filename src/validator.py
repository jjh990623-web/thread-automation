"""초안 검사: 금지 표현, 중복, 과한 홍보."""

from typing import List, Tuple

import yaml

from .models import Draft


class DraftValidator:
    def __init__(self, brand_voice_path: str = "config/brand_voice.yaml"):
        with open(brand_voice_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.banned_phrases: List[str] = cfg.get("banned_phrases", [])
        self.promo_keywords: List[str] = cfg.get("promo_keywords", [])
        self.max_promo_per_window: int = cfg.get("max_promo_per_window", 2)
        self.similarity_threshold: float = cfg.get("similarity_threshold", 0.6)

    def validate(self, draft: Draft, recent_posts: List[str]) -> Tuple[bool, str]:
        for phrase in self.banned_phrases:
            if phrase in draft.text:
                return False, f"금지 표현 '{phrase}' 포함"

        for past in recent_posts:
            sim = self._jaccard(draft.text, past)
            if sim >= self.similarity_threshold:
                return False, f"최근 글과 유사도 {sim:.2f} — 중복 가능성"

        is_promo = any(kw in draft.text for kw in self.promo_keywords)
        if is_promo:
            promo_count = sum(
                1 for p in recent_posts
                if any(kw in p for kw in self.promo_keywords)
            )
            if promo_count >= self.max_promo_per_window:
                return False, f"최근 홍보글 {promo_count}회 — 과한 홍보 우려"

        return True, "OK"

    @staticmethod
    def _jaccard(a: str, b: str) -> float:
        # TODO: 한글에 더 적합한 유사도(임베딩 cosine 등)로 교체
        wa = {w for w in a.split() if len(w) >= 2}
        wb = {w for w in b.split() if len(w) >= 2}
        if not wa or not wb:
            return 0.0
        return len(wa & wb) / len(wa | wb)
