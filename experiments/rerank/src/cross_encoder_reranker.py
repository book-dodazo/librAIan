"""
CrossEncoder 공통 래퍼 (sentence-transformers 기반)

지원 모델:
  BGE  - BAAI/bge-reranker-v2-m3          (568M)
  GTE  - Alibaba-NLP/gte-multilingual-reranker-base  (305M)
  Jina - jinaai/jina-reranker-v2-base-multilingual   (278M)
"""
from __future__ import annotations

from typing import Callable

from sentence_transformers import CrossEncoder


MODELS = {
    "BGE":  "BAAI/bge-reranker-v2-m3",
    "GTE":  "Alibaba-NLP/gte-multilingual-reranker-base",
    "Gemma": "BAAI/bge-reranker-v2-gemma",  # GPU 16GB+ 필요
    "Jina": "jinaai/jina-reranker-v2-base-multilingual",
}

# custom code 실행 허용이 필요한 모델 목록
TRUST_REMOTE_CODE_MODELS = {
    "Alibaba-NLP/gte-multilingual-reranker-base",
}


class CrossEncoderReranker:
    def __init__(self, model_name: str, device: str = "cpu", max_length: int = 512):
        self.model_name = model_name
        trust = model_name in TRUST_REMOTE_CODE_MODELS
        self.model = CrossEncoder(
            model_name,
            max_length=max_length,
            device=device,
            trust_remote_code=trust,
        )

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        text_fn: Callable[[dict], str],
        batch_size: int = 32,
    ) -> list[dict]:
        """
        query: semantic_query 문자열
        candidates: gold_candidate_pool의 candidates 리스트
        text_fn: book dict → document text 변환 함수 (book_text_variants.VARIANTS[X])

        반환: [{"book": dict, "score": float, "rank": int}, ...]  내림차순 정렬
        """
        pairs = [(query, text_fn(c)) for c in candidates]
        scores = self.model.predict(pairs, batch_size=batch_size, show_progress_bar=False)

        ranked = sorted(
            zip(candidates, scores.tolist()),
            key=lambda x: x[1],
            reverse=True,
        )
        return [
            {"book": c, "score": s, "rank": i + 1}
            for i, (c, s) in enumerate(ranked)
        ]


def load_all_rerankers(device: str = "cpu", max_length: int = 512) -> dict[str, CrossEncoderReranker]:
    """세 모델을 모두 로드하여 반환. GPU 메모리가 부족하면 모델 하나씩 사용."""
    return {
        name: CrossEncoderReranker(model_id, device=device, max_length=max_length)
        for name, model_id in MODELS.items()
    }
