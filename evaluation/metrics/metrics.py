import math

# 질의 이해 -> 
# slot f1, 누적 slot f1


# retrieval metrics
def hit_at_k(relevant_isbns, retrieved_isbns, k=20):
    '''
    top K 중 relevant 1개 이상 포함 여부
    '''
    if set(relevant_isbns) & set(retrieved_isbns[:k]):
        return 1
    return 0


def recall_at_k(relevant_isbns, retrieved_isbns, k=20):
    '''
    top K에 포함된 개수 / relevant N개
    '''
    relevant_count = len(set(relevant_isbns) & set(retrieved_isbns[:k]))
    return  relevant_count / len(relevant_isbns)

# ranking metrics
def mrr_at_k(relevant_isbns, reranked_isbns, k=10):
    '''
    첫 번째 relevant item의 순위에 따라 가중치를 주는 지표
    '''
    for i, item in enumerate(reranked_isbns[:k], start=1):
        if item in relevant_isbns:
            return 1 / i
    return 0


def ndcg_at_k(relevant_isbns, reranked_isbns, k=5):
    '''
    상위 K개 순위의 관련도 점수에 가중치를 주는 지표
    단, 관련도 점수는 binary relevance (1 또는 0)로 가정
    참고: https://lsjsj92.tistory.com/663
    '''
    dcg = 0 
    for i, item in enumerate(reranked_isbns[:k], start=1):
        if item in relevant_isbns:
            dcg += 1 / math.log2(i + 1) # DCG 계산
    
    ideal_dcg = 0
    ideal_dcg = sum(
        1 / math.log2(i + 1) 
        for i in range(1, min(len(relevant_isbns), k) + 1)
        ) # 이상적인 DCG 계산

    return dcg / ideal_dcg if ideal_dcg else 0


def graded_ndcg_at_k(relevance_scores, reranked_isbns, k=10):
    '''
    Graded NDCG: grade 2→gain=2, grade 3→gain=3, grade 0/1→gain=0.
    relevance_scores: {isbn: final_grade}
    '''
    def gain(grade):
        return grade if grade >= 2 else 0

    dcg = sum(
        gain(relevance_scores.get(isbn, 0)) / math.log2(i + 1)
        for i, isbn in enumerate(reranked_isbns[:k], start=1)
    )
    ideal_gains = sorted([gain(g) for g in relevance_scores.values()], reverse=True)[:k]
    idcg = sum(
        g / math.log2(i + 1)
        for i, g in enumerate(ideal_gains, start=1)
    )
    return dcg / idcg if idcg else 0


def hard_negative_at_k(hard_negative_isbns, reranked_isbns, k=5):
    '''
    상위 K개에 hard negative가 포함된 개수
    '''
    hard_negative_set = set(hard_negative_isbns)
    top_k = reranked_isbns[:k]

    return sum(1 for isbn in top_k if isbn in hard_negative_set)


# availability
def availability_hit_at_k():
    return
def intent_and_available_at_k():
    return