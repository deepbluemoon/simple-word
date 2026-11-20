from training.judge_gold import content_words, coverage, stratified


def test_content_words_and_coverage():
    assert content_words("행정안전부는 지원금을 지급했다") == ["행정안전부", "지원금", "지급했다"]
    assert coverage("플랫폼을 구축한다", "장치 틀을 만든다", {"플랫폼": ["장치 틀"]}) == 0.5
    assert coverage("", "무엇이든", {}) == 1.0


def test_stratified_is_deterministic_and_spreads_strata():
    rows = [{"doc_id": f"{m}-{i}", "src": "가" * (10 + i)} for m in ("mois", "mohw") for i in range(30)]
    pub = {r["doc_id"]: f"2026-01-{int(r['doc_id'].split('-')[1]) % 28 + 1:02d}" for r in rows}
    a, b = stratified(rows, 12, pub), stratified(rows, 12, pub)
    assert a == b and len(a) == 12
    assert {r["doc_id"].split("-")[0] for r in a} == {"mois", "mohw"}
