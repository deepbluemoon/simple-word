import re

from simple_word.terms import found
from training.terms import coverage, merge_dicts, parse_law_xml, parse_nikl


def test_found_matches_original_regex_results():
    terms = ["법률", "기관", "governance", "수", "", "가-나", "A.B"]
    texts = ["법률에 따라", "대한법률", "X기관", "(기관)", "governance와", "governance2", "수", "가-나", "A.B"]
    for term in terms:
        pattern = re.compile(r"(?<![가-힣A-Za-z])" + re.escape(term))
        for text in texts:
            assert found(term, text) == (pattern.search(text) is not None)


def test_nikl_normalizes_aliases_and_filters_generic_short_terms():
    rows = "연번,단어_용어,이표기_오표기,대안어(안)\n1, 거버넌스 ,governance,\"협치, 관리(쉽게 씀)\"\n2,수,,물\n3,내용,,설명\n"
    terms = parse_nikl(rows)
    assert terms["거버넌스"] == {"alternatives": ["협치", "관리"], "sources": ["국립국어원_15130006"]}
    assert terms["governance"]["alternatives"] == ["협치", "관리"]
    assert "수" not in terms and "내용" not in terms


def test_law_terms_merge_alternatives_and_keep_source_provenance():
    xml = """<root><item><법령용어명>귀책사유</법령용어명><일상용어명>책임이 있는 까닭</일상용어명></item>
    <item><법령용어명>귀책사유</법령용어명><일상용어명>잘못한 이유</일상용어명></item></root>"""
    law = parse_law_xml(xml)
    merged = merge_dicts({"귀책사유": {"alternatives": ["책임이 있는 까닭"], "sources": ["국립국어원"]}}, law)
    assert merged["귀책사유"] == {"alternatives": ["책임이 있는 까닭", "잘못한 이유"],
                                  "sources": ["국립국어원", "법제처_법령정보지식베이스"]}
    assert coverage([{"src": "귀책사유를 확인한다."}, {"src": "다른 문장"}], merged) == {
        "sentences": 2, "with_terms": 1, "rate": 0.5,
        "term_hits_by_source": {"국립국어원": 1, "법제처_법령정보지식베이스": 1}}


from pathlib import Path

import pytest

from training import terms as T

FIX = Path(__file__).parent / "fixtures"


def test_law_service_xml_keeps_only_synonyms():
    # 실제 응답(키는 ***로 가림): 청원 → 하위어·연관어만 → 넣지 않음, 민원 → 민원업무(동의어)
    assert T.parse_law_xml((FIX / "law_lstrmRlt.xml").read_text(encoding="utf-8")) == {}
    assert T.parse_law_xml((FIX / "law_dlytrmRlt.xml").read_text(encoding="utf-8")) == {
        "민원업무": {"alternatives": ["민원"], "sources": [T.LAW_SOURCE]}}


LSTRM = """<?xml version="1.0" encoding="UTF-8"?><lstrmRltService><키워드>{q}</키워드><법령용어 id="1"><법령용어명>{q}</법령용어명>
<연계용어 id="1"><일상용어명><![CDATA[{easy}]]></일상용어명><용어관계코드>140301</용어관계코드>
<일상용어조회링크><![CDATA[/DRF/lawSearch.do?OC=SECRET&query={easy}]]></일상용어조회링크></연계용어></법령용어></lstrmRltService>"""


def test_fetch_law_terms_caches_masks_key_and_skips_done(tmp_path):
    calls = []

    def get(target, q, key):
        calls.append((target, q))
        return LSTRM.format(q=q, easy="쉬운말") if target == "lstrmRlt" else "<dlytrmRltService></dlytrmRltService>"

    assert T.fetch_law_terms(["귀책사유"], tmp_path, key="SECRET", get=get, delay=0, log=lambda *_: None) == 2
    assert T.fetch_law_terms(["귀책사유", "해태"], tmp_path, key="SECRET", get=get, delay=0, log=lambda *_: None) == 2
    assert calls == [("lstrmRlt", "귀책사유"), ("dlytrmRlt", "귀책사유"), ("lstrmRlt", "해태"), ("dlytrmRlt", "해태")]
    cache = (tmp_path / "law_cache.jsonl").read_text(encoding="utf-8")
    assert "SECRET" not in cache and "OC=***" in cache
    assert T.law_dict(tmp_path)["귀책사유"]["alternatives"] == ["쉬운말"]


def test_fetch_law_terms_without_key_or_with_auth_error(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "law_key", lambda: None)
    msgs = []
    assert T.fetch_law_terms(["귀책사유"], tmp_path, log=msgs.append) == 0 and "LAW_OC 없음" in msgs[0]
    bad = lambda t, q, k: "<?xml version='1.0'?><Response><result>사용자 정보 검증에 실패하였습니다.</result></Response>"
    with pytest.raises(T.LawAuthError, match="인증 오류"):
        T.fetch_law_terms(["귀책사유"], tmp_path, key="K", get=bad, delay=0)
    assert not (tmp_path / "law_cache.jsonl").read_text()


def test_candidate_words_strip_josa_and_count():
    words = T.candidate_words(["귀책사유가 있는 경우 귀책사유를 확인", "해태하면 해태하는 자"], min_count=2)
    assert words[:1] == ["귀책사유"] and "해태" in words


def test_fetch_law_terms_skips_network_errors(tmp_path, monkeypatch):
    from training import terms

    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = []

    def get(target, word, key):
        calls.append((target, word))
        if word == "나쁨":
            raise TimeoutError("timed out")
        return "<lstrmRltService></lstrmRltService>"

    n = terms.fetch_law_terms(["나쁨", "좋음"], tmp_path, key="k", targets=("lstrmRlt",), get=get, delay=0, log=lambda m: None)
    assert n == 1 and calls.count(("lstrmRlt", "나쁨")) == 3


def test_law_terms_are_opt_in_and_strict_drops_daily_words(tmp_path):
    import json
    from training import terms as T

    (tmp_path / "nikl_terms.csv").write_text("연번,단어_용어,이표기_오표기,대안어(안)\n1,거버넌스,,협치\n", encoding="utf-8")
    lst = ('<lstrmRltService><법령용어><법령용어명>{h}</법령용어명><연계용어><일상용어명>{e}</일상용어명>'
           '<용어관계코드>140301</용어관계코드></연계용어></법령용어></lstrmRltService>')
    dly = '<dlytrmRltService><일상용어><일상용어명>지원</일상용어명></일상용어></dlytrmRltService>'
    rows = [{"target": "lstrmRlt", "query": "제고", "xml": lst.format(h="제고", e="높임")},
            {"target": "lstrmRlt", "query": "지원", "xml": lst.format(h="지원", e="뒷바라지")},
            {"target": "dlytrmRlt", "query": "지원", "xml": dly}]
    (tmp_path / "law_cache.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert not any(T.LAW_SOURCE in e["sources"] for e in T.nikl_dict(tmp_path).values())
    assert {"제고", "지원"} <= set(T.law_dict(tmp_path))
    assert set(T.law_dict(tmp_path, strict=True)) == {"제고"}


def test_fetch_law_terms_refuses_concurrent_run(tmp_path, monkeypatch):
    import fcntl
    import pytest
    from training import terms
    monkeypatch.setattr("time.sleep", lambda s: None)
    cache = tmp_path / "law_cache.jsonl"
    with cache.open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        with pytest.raises(terms.LawFetchBusy):
            terms.fetch_law_terms(["제고"], tmp_path, key="k", targets=("lstrmRlt",), get=lambda *a: "<x/>", delay=0, log=lambda m: None)
    assert terms.fetch_law_terms(["제고"], tmp_path, key="k", targets=("lstrmRlt",), get=lambda *a: "<x/>", delay=0, log=lambda m: None) == 1


def test_law_cache_skips_broken_last_line(tmp_path):
    import json
    import pytest
    from training import terms
    good = json.dumps({"target": "lstrmRlt", "query": "제고", "xml": "<x/>"}, ensure_ascii=False)
    (tmp_path / "law_cache.jsonl").write_text(good + "\n" + '{"target": "lstrmRlt", "que', encoding="utf-8")
    assert [r["query"] for r in terms.read_cache(tmp_path / "law_cache.jsonl")] == ["제고"]
    assert terms.fetch_law_terms(["제고"], tmp_path, key="k", targets=("lstrmRlt",), get=lambda *a: "<x/>", delay=0, log=lambda m: None) == 0
    (tmp_path / "mid.jsonl").write_text('{"broken\n' + good + "\n", encoding="utf-8")
    with pytest.warns(UserWarning, match="깨진 줄 1개"):
        assert [r["query"] for r in terms.read_cache(tmp_path / "mid.jsonl")] == ["제고"]


def test_fetch_after_broken_last_line_starts_new_line(tmp_path):
    from training import terms
    (tmp_path / "law_cache.jsonl").write_text('{"target": "lstrmRlt", "que', encoding="utf-8")
    assert terms.fetch_law_terms(["제고"], tmp_path, key="k", targets=("lstrmRlt",), get=lambda *a: "<x/>", delay=0, log=lambda m: None) == 1
    assert [r["query"] for r in terms.read_cache(tmp_path / "law_cache.jsonl")] == ["제고"]
