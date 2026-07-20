import math

from disambiguation_engine.paper_graph_rescue import (
    HistoricalCoauthorGraph,
    predict_graph_by_paper,
    predict_paper_graph,
)


def test_graph_rescues_candidate_supported_by_fixed_coauthor():
    graph = HistoricalCoauthorGraph.from_mentions([
        {"article_id": "h1", "gold_author_id": "A"},
        {"article_id": "h1", "gold_author_id": "B"},
    ])
    records = [
        {
            "decision": "new",
            "topk": [{"author_id": "A"}, {"author_id": "C"}],
        },
        {"decision": "merge", "author_id": "B", "topk": []},
    ]
    prediction = predict_paper_graph(records, graph)[0]
    assert prediction.author_id == "A"
    assert prediction.support == math.log(2.0)


def test_graph_does_not_assign_one_identity_twice_on_a_paper():
    graph = HistoricalCoauthorGraph.from_mentions([
        {"article_id": "h1", "gold_author_id": "A"},
        {"article_id": "h1", "gold_author_id": "B"},
    ])
    records = [
        {"decision": "new", "topk": [{"author_id": "A"}]},
        {"decision": "new", "topk": [{"author_id": "A"}, {"author_id": "B"}]},
    ]
    predictions = predict_paper_graph(records, graph)
    assert len({item.author_id for item in predictions.values()}) == 2


def test_global_predictions_preserve_record_positions():
    history = [
        {"article_id": "h", "gold_author_id": "A"},
        {"article_id": "h", "gold_author_id": "B"},
    ]
    records = [
        {"article_id": "p", "decision": "new", "topk": [{"author_id": "A"}]},
        {"article_id": "p", "decision": "merge", "author_id": "B", "topk": []},
    ]
    assert predict_graph_by_paper(history, records)[0].author_id == "A"


def test_relation_filter_excludes_weak_name_candidates():
    graph = HistoricalCoauthorGraph.from_mentions([
        {"article_id": "h", "gold_author_id": "A"},
        {"article_id": "h", "gold_author_id": "B"},
    ])
    records = [
        {
            "decision": "new",
            "topk": [
                {"author_id": "A", "comparisons": {"name_sim": 0.4}},
                {"author_id": "B", "comparisons": {"name_sim": 0.9}},
            ],
        }
    ]
    prediction = predict_paper_graph(
        records, graph, min_name_similarity=0.7
    )[0]
    assert prediction.author_id == "B"
