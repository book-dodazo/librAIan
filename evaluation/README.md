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
- `goldset_final.json` — 최종 골드셋 (3개 LLM judge 합의 등급, 476권)
- `goldset_final_6.json` — 노트북에서 사용하는 최종 골드셋 (6개 시나리오)
- `embedding_model_dense_eval.jsonl` — 임베딩 모델 비교 실험 결과 (CLOVA/KURE/BGE-M3-KO)
- `chunk_dense_eval.jsonl` — 청킹 전략 비교 실험 결과 (full-text vs. chunk)

### dataset/archive/
골드셋 생성 과정의 중간 iteration 파일들 (최종 분석에는 사용하지 않음).

### metrics/
- [metrics.py](metrics/metrics.py) — IR 평가 지표 함수 (Hit@K, Recall@K, MRR@K, NDCG@K 등)

### notebooks/ (번호 순서대로 실행)

**골드셋 생성 (01–06)**
- [01_goldset_initial_generation.ipynb](notebooks/01_goldset_initial_generation.ipynb) — BM25/Dense/Hybrid 검색 후 LLM judge로 후보 책 라벨링
- [02_goldset_generation_v2.ipynb](notebooks/02_goldset_generation_v2.ipynb) — 개선된 버전의 골드셋 생성
- [03_goldset_consensus_grading.ipynb](notebooks/03_goldset_consensus_grading.ipynb) — 3개 judge 결과 합의 → 최종 등급 결정
- [04_goldset_merge_reruns.ipynb](notebooks/04_goldset_merge_reruns.ipynb) — 재실행 결과를 최종 골드셋에 병합
- [05_goldset_rerun_specific_scenarios.ipynb](notebooks/05_goldset_rerun_specific_scenarios.ipynb) — S03/S20 시나리오 재실행
- [06_goldset_reevaluation_async.ipynb](notebooks/06_goldset_reevaluation_async.ipynb) — 전체 골드셋 비동기 재평가

**검색 평가 (07–09)**
- [07_eval_retrieval_comparison.ipynb](notebooks/07_eval_retrieval_comparison.ipynb) — BM25 vs Dense vs Hybrid 검색 성능 비교
- [08_eval_reranking_comparison.ipynb](notebooks/08_eval_reranking_comparison.ipynb) — 리랭킹 전/후 성능 비교 (CLOVA Reranker)
- [09_embedding_chunking_evaluation.ipynb](notebooks/09_embedding_chunking_evaluation.ipynb) — 임베딩 모델 및 청킹 전략 비교

### results/
- [output_schema.md](results/output_schema.md) — 평가 결과 출력 파일 스키마 (retrieval_results.jsonl 등)
