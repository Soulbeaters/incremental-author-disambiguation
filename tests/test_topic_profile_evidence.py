from disambiguation_engine.topic_profile_evidence import TopicProfileIndex


def test_topic_profile_uses_history_only_and_prefers_related_paper():
    metadata = {
        "p1": {
            "title": ["Graph databases for scholarly records"],
            "abstract": "Entity resolution in digital libraries",
            "container-title": ["Data Journal"],
        },
        "p2": {
            "title": ["Clinical outcomes in oncology"],
            "abstract": "A randomized medical trial",
            "container-title": ["Medical Journal"],
        },
    }
    index = TopicProfileIndex.from_history(
        [{"article_id": "P1", "gold_author_id": "A"}], metadata
    )
    related = index.evidence("A", {
        "title": ["Entity resolution for scholarly databases"],
        "abstract": "Digital library records",
        "container-title": ["Data Journal"],
    })
    unrelated = index.evidence("A", metadata["p2"])
    assert related.profile_cosine > unrelated.profile_cosine
    assert related.venue_match == 1.0
    assert unrelated.venue_match == 0.0


def test_query_terms_do_not_enter_history_idf_or_profile():
    index = TopicProfileIndex.from_history(
        [{"article_id": "p", "gold_author_id": "A"}],
        {"p": {"title": "historical database systems"}},
    )
    before = dict(index.idf)
    evidence = index.evidence("A", {"title": "novel unseen vocabulary"})
    assert index.idf == before
    assert "novel" not in index.idf
    assert evidence.profile_cosine == 0.0
