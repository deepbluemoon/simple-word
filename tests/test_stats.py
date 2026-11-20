import json

from training.stats import table


def test_table_groups_documents_sentences_and_passed_pairs_by_period(tmp_path):
    (tmp_path / "docs.jsonl").write_text("".join(json.dumps(row) + "\n" for row in [
        {"id": "d1", "source": "mois", "published_at": "2026-01-02"},
        {"id": "d2", "source": "mois", "published_at": "2026-02-03"},
        {"id": "d3", "source": "mohw", "published_at": "2026-07-04"},
    ]))
    (tmp_path / "sentences.jsonl").write_text("".join(json.dumps(row) + "\n" for row in [
        {"doc_id": "d1"}, {"doc_id": "d2"}, {"doc_id": "d3"},
    ]))
    (tmp_path / "pairs.jsonl").write_text("".join(json.dumps(row) + "\n" for row in [
        {"doc_id": "d1", "passed": True}, {"doc_id": "d1", "passed": False},
        {"doc_id": "d3", "passed": True}, {"doc_id": "unknown", "passed": True},
    ]))

    result = table(tmp_path)

    assert "행정안전부 | 2026 H1 | 2 | 2 | 2 | 1" in result
    assert "보건복지부 | 2026 H2 | 1 | 1 | 1 | 1" in result
    assert "**합계** | | **3** | **3** | **3** | **2**" in result
