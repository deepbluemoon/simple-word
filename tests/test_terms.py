from training.terms import coverage, merge_dicts, parse_law_xml, parse_nikl


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
