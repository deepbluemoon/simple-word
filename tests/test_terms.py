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
