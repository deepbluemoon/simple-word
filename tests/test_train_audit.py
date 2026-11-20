from training.train import audit


def test_audit_counts_pii_and_teacher_filter():
    ok = {"doc_id": "d", "src": "지원금 3만 원을 드린다.", "tgt": "3만 원을 드립니다."}
    bad = [{"doc_id": "d", "src": "문의 010-1234-5678", "tgt": "전화 010-1234-5678"},
           {"doc_id": "d", "src": "짧다.", "tgt": "아주 아주 길게 풀어 쓴 문장입니다."},
           {"doc_id": "d", "src": "한 줄", "tgt": "두\n줄"},
           {"doc_id": "d", "src": "5명이 왔다.", "tgt": "6명이 왔습니다."}]
    assert not any(audit({"train": [ok], "valid": [], "test": []}).values())
    a = audit({"train": bad, "valid": [], "test": []})
    assert a["pii_unmasked"] == 1 and a["length_over"] >= 1 and a["multiline"] == 1 and a["numbers_mismatch"] >= 1
