import json
from datetime import date

import pytest

from repolens import discover as d
from repolens.llm.router import AllProvidersFailed
from tests.test_v1 import FakeRouter  # noqa: F401

TODAY = date(2026, 10, 21)


def cand(name, stars=500, pushed="2026-09-01", size_kb=3000, desc="", topics=(), archived=False, queries=("q",), language="Python"):
    return {"full_name": name, "stars": stars, "pushed_at": pushed, "size_kb": size_kb, "description": desc,
            "topics": list(topics), "archived": archived, "matched_queries": list(queries), "language": language}


class FakeExt:
    """Stands in for External: canned search results per query and canned manifests."""

    def __init__(self, results=None, manifests=None):
        self.results, self.manifests, self.queries = results or {}, manifests or {}, []

    def search_repos(self, query, sort="stars", per_page=10):
        self.queries.append(query)
        return [dict(r) for r in next((v for k, v in self.results.items() if k in query), [])]

    def manifest_dependencies(self, owner, name):
        return self.manifests.get(f"{owner}/{name}")


def test_goal_terms_drop_filler_words_and_duplicates():
    assert d.goal_terms("I want to build a RAG chatbot using Python and RAG") == ["rag", "chatbot", "python"]
    assert d.goal_terms("") == [] and d.goal_terms("the and of") == []


def test_clean_query_blocks_search_operators():
    """A model, or a goal with injected text, must not steer the GitHub search with user:/org:/repo: qualifiers."""
    for bad in ("user:torvalds linux", "org:google", "repo:a/b", "language:python rag", "stars:>1000000", None, 5, "", "   ", "!!!"):
        assert d.clean_query(bad) is None
    assert d.clean_query("  RAG   Chatbot!! ") == "rag chatbot"
    assert d.clean_query("one two three four five six seven") == "one two three four five"         # trimmed to 5 words


def test_heuristic_queries_include_topics_and_pairs():
    qs = d.heuristic_queries("build a RAG chatbot with vector search")
    assert qs[0] == "rag chatbot vector search" and "topic:rag" in qs and "rag chatbot" in qs
    assert d.heuristic_queries("the and") == []


def test_queries_from_a_model_are_sanitized_and_keep_the_goals_own_words():
    r = FakeRouter(json.dumps({"queries": ["retrieval augmented generation", "user:evil secret", "rag chatbot", 7, "vector search"]}))
    qs, how = d.queries_for_goal("build a RAG chatbot", r)
    assert how == "model" and "user:evil secret" not in qs and not any(":" in q for q in qs)
    assert "retrieval augmented generation" in qs and "rag chatbot" in qs


def test_model_trouble_falls_back_to_the_goals_words():
    for router in (FakeRouter(AllProvidersFailed({"x": "down"})), FakeRouter("not json"), FakeRouter(json.dumps({"queries": ["a:b"]})), None):
        qs, how = d.queries_for_goal("build a RAG chatbot", router)
        assert how == "keywords" and qs[0] == "rag chatbot"


def test_search_query_has_filters_and_topic_queries_are_not_wrapped():
    q = d.build_search_query("rag chatbot", "python", TODAY)
    assert q == "rag chatbot in:name,description,readme stars:>50 pushed:>2024-10-21 fork:false language:python"
    assert d.build_search_query("topic:rag", None, TODAY) == "topic:rag stars:>50 pushed:>2024-10-21 fork:false"


def test_gather_merges_duplicates_and_remembers_which_queries_found_them():
    ext = FakeExt({"rag chatbot": [cand("a/one"), cand("b/two")], "vector search": [cand("a/one"), cand("c/three")]})
    got = {c["full_name"]: c for c in d.gather(ext, ["rag chatbot", "vector search"], TODAY)}
    assert set(got) == {"a/one", "b/two", "c/three"}
    assert got["a/one"]["matched_queries"] == ["rag chatbot", "vector search"] and got["b/two"]["matched_queries"] == ["rag chatbot"]


def test_expected_libraries_come_from_the_taxonomy():
    libs = d.expected_libs(["rag", "chatbot"])
    assert {"chromadb", "faiss-cpu", "sentence-transformers"} <= libs and "pandas" not in libs
    assert d.expected_libs(["xx"]) == set()                                                         # too-short words are ignored


def test_score_parts_sum_to_total_and_each_signal_moves_the_right_way():
    terms = ["rag", "chatbot"]
    base = d.score(cand("o/rag-chatbot", desc="A RAG chatbot"), terms, TODAY)
    assert base["total"] == round(sum(base["parts"].values()), 3) and base["matched_terms"] == ["rag", "chatbot"]
    assert d.score(cand("o/other", desc="a web framework"), terms, TODAY)["total"] < base["total"]               # relevance
    assert d.score(cand("o/rag-chatbot", desc="A RAG chatbot", pushed="2021-01-01"), terms, TODAY)["total"] < base["total"]   # freshness
    assert d.score(cand("o/rag-chatbot", desc="A RAG chatbot", stars=60), terms, TODAY)["total"] < base["total"]            # popularity
    assert d.score(cand("o/rag-chatbot", desc="A RAG chatbot", size_kb=900_000), terms, TODAY)["total"] < base["total"]     # learnability
    arch = d.score(cand("o/rag-chatbot", desc="A RAG chatbot", archived=True), terms, TODAY)
    assert arch["parts"]["archived penalty"] == -0.10 and arch["total"] < base["total"]                           # penalized, not hidden
    partial_one = d.score(cand("o/rag-demo", desc="A RAG demo", queries=("a",)), terms, TODAY)                   # matches 1 of 2 words
    partial_many = d.score(cand("o/rag-demo", desc="A RAG demo", queries=("a", "b", "c")), terms, TODAY)
    assert partial_many["total"] > partial_one["total"]                                                           # found by several queries
    assert d.score(cand("o/rag-chatbot", desc="A RAG chatbot", queries=("a", "b", "c")), terms, TODAY)["parts"]["relevance"] == 0.45   # capped


def test_rank_uses_declared_dependencies_and_respects_top():
    cands = [cand("o/plain-rag", desc="rag chatbot demo", stars=900), cand("o/uses-libs", desc="rag chatbot demo", stars=900),
             cand("o/unrelated", desc="image tools", stars=5000)]
    ext = FakeExt(manifests={"o/uses-libs": {"chromadb", "fastapi"}, "o/plain-rag": {"flask"}})
    ranked = d.rank(cands, "rag chatbot", TODAY, ext=ext, top=2)
    assert [c["full_name"] for c in ranked] == ["o/uses-libs", "o/plain-rag"]                                    # stack match breaks the tie
    assert ranked[0]["dep_hits"] == ["chromadb"] and ranked[1]["dep_hits"] == []
    assert "stack match" in ranked[0]["parts"] and len(ranked) == 2
    assert [c["full_name"] for c in d.rank(cands, "rag chatbot", TODAY, ext=None, top=5)][-1] == "o/unrelated"   # works without API checks


def test_learning_order_puts_smaller_repos_first():
    ranked = [{"full_name": "big", "size_kb": 400_000, "score": 0.9}, {"full_name": "small", "size_kb": 800, "score": 0.5},
              {"full_name": "mid", "size_kb": 20_000, "score": 0.7}]
    assert [c["full_name"] for c in d.learning_order(ranked)] == ["small", "mid", "big"]


def test_guide_is_honest_about_stage_a_and_handles_no_results():
    ranked = d.rank([cand("o/rag-chatbot", desc="A RAG chatbot", topics=["rag"])], "rag chatbot", TODAY, ext=None)
    md = d.render_guide("rag chatbot", ranked, "keywords", ["rag chatbot"], "python")
    assert "# Repos to study for: rag chatbot" in md and "NOT assessed" in md and "Nothing was cloned" in md
    assert "[o/rag-chatbot](https://github.com/o/rag-chatbot)" in md and "why: relevance" in md and "language: python" in md
    assert "Suggested reading order" in md and "ask first" in md
    empty = d.render_guide("zzz", [], "keywords", ["zzz"])
    assert "No repositories found" in empty


def test_cli_rejects_an_empty_goal(capsys):
    from repolens import find
    assert find.main(["   "]) == 2 and "empty goal" in capsys.readouterr().err
    assert find.main(["the and of", "--no-llm"]) == 2                                                          # nothing searchable
