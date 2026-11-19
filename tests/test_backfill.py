from training.collect import SOURCES, ids_in


def test_backfill_list_ids_map_to_robots_allowed_urls():
    mohw_list = '<a href="/board.es?mid=a10503010100&amp;bid=0027&amp;act=view&amp;list_no=1490221&amp;nPage=50">'
    assert ids_in("mohw", mohw_list) == ["1490221"]
    # 복지부 robots.txt: Disallow /board.es, Allow /board.es?mid=a10503010100&bid=0027
    assert SOURCES["mohw"]["article"].format(id="1").startswith("https://www.mohw.go.kr/board.es?mid=a10503010100&bid=0027")
    mois_list = '<a href="/frt/bbs/type010/commonSelectBoardArticle.do;jsessionid=x.node30?bbsId=BBSMSTR_000000000008&amp;nttId=127629">'
    assert ids_in("mois", mois_list) == ["127629"]
