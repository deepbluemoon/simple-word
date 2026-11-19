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


def _hwpx(paragraphs):
    import io, zipfile
    ns = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
    body = "".join(f"<hp:p><hp:run><hp:t>{p}</hp:t></hp:run></hp:p>" for p in paragraphs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section0.xml", f"<hs:sec {ns} xmlns:hs=\"h\">{body}</hs:sec>")
    return buf.getvalue()


MOE_LIST = "<a onclick=\"goView('294', '107703', '0', null, 'W', '1', 'N', '')\">x</a>"
MOE_PAGE = ('<section class="news-header"><h3>교육부 제목</h3><span class="reg-date">2026-11-19</span></section>'
            "<img src='img_opentype01.png'><section class=\"attachment\"><ul><li><span>보도자료.hwpx</span>"
            '<a href="/boardCnts/fileDown.do?m=020402&s=moe&fileSeq=abc123">다운로드</a></li></ul></section>')


def test_moe_body_comes_from_hwpx_without_header(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "fetch", lambda url: MOE_LIST if "listRenew" in url else MOE_PAGE)
    hwpx = _hwpx(["보도자료", "배포", "(지  면)2026.11. 20.(금) 조간", "교육부는 11월 19일 계획을 발표했다."])
    monkeypatch.setattr(collect, "fetch_bytes", lambda url, max_bytes=None: hwpx)
    assert collect.collect(tmp_path / "d", tmp_path / "r", sources=["moe"], log=lambda *_: None) == 1
    [doc] = [json.loads(l) for l in (tmp_path / "d/docs.jsonl").open()]
    assert (doc["id"], doc["title"], doc["published_at"], doc["license"]) == ("moe-107703", "교육부 제목", "2026-11-19", "KOGL-1")
    assert doc["body"] == "교육부는 11월 19일 계획을 발표했다."


def test_backfill_stops_at_since(tmp_path, monkeypatch):
    cfg = dict(collect.SOURCES["mois"], rss=None)
    monkeypatch.setattr(collect, "SOURCES", {"mois": cfg})
    page = lambda n: ''.join(f'type010/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000008&nttId={n}{i}"' for i in range(2))
    dates = {"1": "2026.01.05", "2": "2025.06.01", "3": "2024.01.01"}
    seen = []

    def fake(url):
        seen.append(url)
        if "pageIndex=" in url:
            return page(url.rsplit("=", 1)[1])
        n = url.rsplit("=", 1)[1][0]
        return PAGE.replace("2026.11.18", dates[n]).replace("11</span>월", f"{url[-2:]}</span>월")
    monkeypatch.setattr(collect, "fetch", fake)
    collect.collect(tmp_path / "d", tmp_path / "r", backfill_pages=3, since="2025-11-01", log=lambda *_: None)
    assert not any("pageIndex=3" in u for u in seen)  # 2쪽이 모두 since 이전 → 3쪽은 안 받음


def test_datagokr_without_key_does_nothing(tmp_path, monkeypatch):
    from training import datagokr
    monkeypatch.delenv("DATA_GO_KR_KEY", raising=False)
    monkeypatch.setattr(datagokr, "api_key", lambda: None)
    assert datagokr.collect_api("msit", tmp_path, log=lambda *_: None) == 0
    assert not (tmp_path / "docs.jsonl").exists()


def test_datagokr_maps_common_response_shape(tmp_path, monkeypatch):
    from training import datagokr
    payload = {"response": {"body": {"items": {"item": [{"seq": "9", "subject": "제목", "contents": "<p>본문 문장이다.</p>", "regDate": "2026-11-18"}]}}}}
    monkeypatch.setattr(datagokr, "fetch", lambda url: json.dumps(payload) if "pageNo=1" in url else "{}")
    assert datagokr.collect_api("msit", tmp_path, pages=2, key="k", log=lambda *_: None) == 1
    [doc] = [json.loads(l) for l in (tmp_path / "docs.jsonl").open()]
    assert (doc["id"], doc["published_at"], doc["body"], doc["license"]) == ("msit-9", "2026-11-18", "본문 문장이다.", "DATAGOKR-free")
