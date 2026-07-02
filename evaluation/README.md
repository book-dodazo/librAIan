# Evaluation

librAIan 도서 추천 시스템의 평가 프레임워크.

## 폴더 구조

```
evaluation/
├── docs/             # 평가 설계 문서
├── dataset/          # 평가용 데이터셋 (최종)
│   └── archive/      # 중간 생성 결과물 (iteration 파일들)
├── metrics/          # 평가 지표 계산 유틸리티
├── notebooks/        # 데이터셋 생성 및 평가 실험 노트북 (번호순 실행)
└── results/          # 평가 결과 저장 위치
```

## 주요 파일 설명

### docs/
- [framework_overview.md](docs/framework_overview.md) — 전체 평가 프레임워크 설계 (평가 구조, 쿼리 유형, 메트릭 개요)
- [schema_field_guide.md](docs/schema_field_guide.md) — session_eval.jsonl 각 필드 상세 설명
- [labeling_guide.md](docs/labeling_guide.md) — 평가 샘플 생성 워크플로우 (역할 분담, 단계별 작성법)
- [scoring_rubric.md](docs/scoring_rubric.md) — 정성 평가 루브릭 (인간+LLM 이중 채점 기준, 점수 기준표)
- [task_assignment.md](docs/task_assignment.md) — 팀원별 작업 분담 및 체크포인트

### dataset/
- `onboarding_data.json` — 5개 페르소나 × 3명 = 15개 사용자 프로파일
- `scenario_data.json` — 21개 평가 시나리오 (대화 스크립트, RAG 쿼리, 사용자 데이터)
- `session_data_start.json` — 세션 초기 데이터 템플릿
- `scenario_data_after_retrieval.json` — 검색 결과가 추가된 시나리오 데이터
- `scenario_data_after_anchor_rewrite.json` — anchor 기반 query rewrite가 적용된 시나리오 데이터
- `goldset_candidates.json` / `.jsonl` — 골드셋 후보 풀 (BM25/Dense/Hybrid 검색 결과 병합, judge 라벨링 전)
- `goldset_all_scenarios1~3.json` — 3개 LLM judge 각각의 관련도 등급 원본 결과
- `goldset_final.json` — 최종 골드셋 (21개 시나리오 전체, 3개 LLM judge 합의 등급, 2,519건)
- `goldset_final_6.json` — 노트북 실험용 서브셋 (6개 시나리오, 476건)
- `embedding_metric_results.csv` — 임베딩 모델 비교 실험 결과 (CLOVA/KURE/BGE-M3-KO)
- `chunk_metric_results.csv` — 청킹 전략 비교 실험 결과 (full-text vs. chunk)

### dataset/archive/
골드셋 생성 과정의 중간 iteration 파일들 (최종 분석에는 사용하지 않음).

### metrics/
- [metrics.py](metrics/metrics.py) — IR 평가 지표 함수 (Hit@K, Recall@K, MRR@K, NDCG@K, HardNegative@K)

### notebooks/ (번호 순서대로 실행)

**골드셋 생성**
- [01_goldset_initial_generation.ipynb](notebooks/01_goldset_initial_generation.ipynb) — (초기 버전) BM25/Dense/Hybrid 검색 후 LLM judge로 후보 책 라벨링
- [01a_goldset_retrieval.ipynb](notebooks/01a_goldset_retrieval.ipynb) — 후보 풀 검색: 3개 retriever(BM25/Dense/Hybrid) Top-40 병합 → `goldset_candidates`
- [01b_goldset_llm_judge.ipynb](notebooks/01b_goldset_llm_judge.ipynb) — LLM judge 관련도 등급(0~3) 라벨링 (HCX-007, temperature 0, seed 42)
- [02_goldset_generation_v2.ipynb](notebooks/02_goldset_generation_v2.ipynb) — 개선된 버전의 골드셋 생성
- [03_goldset_consensus_grading.ipynb](notebooks/03_goldset_consensus_grading.ipynb) — 3개 judge 결과 합의 → 최종 등급/confidence 결정 (`goldset_final`)
- [04_goldset_merge_reruns.ipynb](notebooks/04_goldset_merge_reruns.ipynb) — 재실행 결과를 최종 골드셋에 병합
- [05_goldset_rerun_specific_scenarios.ipynb](notebooks/05_goldset_rerun_specific_scenarios.ipynb) — S03/S20 시나리오 재실행
- [12_goldset_review.ipynb](notebooks/12_goldset_review.ipynb) — 골드셋 품질 검토

> 최신 골드셋 파이프라인은 **01a(검색) → 01b(LLM judge) → 03(3-judge 합의)** 흐름을 따른다. (01/02는 초기 버전)

**검색 · 리랭킹 평가**
- [07_eval_retrieval_comparison.ipynb](notebooks/07_eval_retrieval_comparison.ipynb) — BM25 vs Dense vs Hybrid 검색 성능 비교
- [08_eval_reranking_comparison.ipynb](notebooks/08_eval_reranking_comparison.ipynb) — 리랭킹 전/후 성능 비교 (⚠️ CLOVA Reranker 기준 — 레거시. 현재 운영 리랭커는 BGE Cross-Encoder이며, 모델 선정 실험은 [experiments/rerank](../experiments/rerank/) 참고)
- [09_embedding_chunking_evaluation.ipynb](notebooks/09_embedding_chunking_evaluation.ipynb) — 임베딩 모델 및 청킹 전략 비교
- [10_embedding_eval_result.ipynb](notebooks/10_embedding_eval_result.ipynb) — 임베딩 모델 평가 결과 정리
- [11_chunk_3_method_evaluation.ipynb](notebooks/11_chunk_3_method_evaluation.ipynb) — 청킹 3가지 방법 평가

### results/
- [output_schema.md](results/output_schema.md) — 평가 결과 출력 파일 스키마 (retrieval_results.jsonl 등)
