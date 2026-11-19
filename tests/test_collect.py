import json

from training import collect

RSS = '<rss><item><link><![CDATA[https://www.mois.go.kr/frt/bbs/type010/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000008&nttId=7]]></link></item></rss>'
PAGE = ('<html><head><meta property="og:title" content="제목 | 행정안전부"></head><body>등록일 : 2026.11.18.'
        '<div id="desc_pc" class="desc"><p><span>행정안전부</span><span>(</span>장관)는 <span>11</span>월 대책을 발표했다.</p></div>'
        '<div id="desc_mo"></div>공공누리 1유형(출처표시)</body></html>')


def test_collect_twice_gives_same_docs(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "SOURCES", {"mois": collect.SOURCES["mois"]})
    monkeypatch.setattr(collect, "fetch", lambda url: RSS if "rss" in url else PAGE)
    assert collect.collect(tmp_path / "d", tmp_path / "r", log=lambda *_: None) == 1
    assert collect.collect(tmp_path / "d", tmp_path / "r", log=lambda *_: None) == 0
    [doc] = [json.loads(l) for l in (tmp_path / "d/docs.jsonl").open()]
    assert doc["body"] == "행정안전부(장관)는 11월 대책을 발표했다."  # 인라인 태그 사이에 공백이 끼지 않음
    assert (doc["id"], doc["title"], doc["published_at"], doc["license"]) == ("mois-7", "제목", "2026-11-18", "KOGL-1")
