from __future__ import annotations

import uuid

from app.search.rrf import RankedItem, compute_rrf


def test_compute_rrf_both_keyword_and_semantic() -> None:
    doc_both = uuid.uuid4()
    doc_kw_only = uuid.uuid4()
    doc_sem_only = uuid.uuid4()

    kw_list = [
        RankedItem(item_id=doc_both, data={"name": "both"}, rank=1, score=10.0, snippet="kw snippet"),
        RankedItem(item_id=doc_kw_only, data={"name": "kw"}, rank=2, score=5.0, snippet="kw only"),
    ]
    sem_list = [
        RankedItem(item_id=doc_both, data={"name": "both"}, rank=1, score=0.92, snippet="sem snippet"),
        RankedItem(item_id=doc_sem_only, data={"name": "sem"}, rank=2, score=0.85, snippet="sem only"),
    ]

    results = compute_rrf(kw_list, sem_list, k=60)
    assert len(results) == 3

    # doc_both must be ranked #1
    assert results[0].item_id == doc_both
    assert results[0].match_type == "BOTH"
    expected_score = round(1.0 / 61 + 1.0 / 61, 6)
    assert results[0].score == expected_score
    assert results[0].keyword_rank == 1
    assert results[0].semantic_rank == 1

    # Remaining two items
    other_types = {results[1].match_type, results[2].match_type}
    assert other_types == {"KEYWORD", "SEMANTIC"}
    expected_single_score = round(1.0 / 62, 6)
    assert results[1].score == expected_single_score
    assert results[2].score == expected_single_score


def test_compute_rrf_empty_lists() -> None:
    assert compute_rrf([], []) == []

    doc = uuid.uuid4()
    kw_only = [RankedItem(item_id=doc, data={"foo": "bar"}, rank=1, score=1.0)]
    res = compute_rrf(kw_only, [])
    assert len(res) == 1
    assert res[0].item_id == doc
    assert res[0].match_type == "KEYWORD"
    assert res[0].score == round(1.0 / 61, 6)

