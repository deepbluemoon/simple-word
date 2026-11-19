from training.evaluate import sari, text_metrics


def test_sari_rewards_reference_like_edits_and_metrics_use_gate_keys():
    src = "구비서류를 지참하여 행정복지센터에 방문 접수하여야 합니다."
    ref = "필요한 서류를 가지고 행정복지센터에 가서 신청해야 합니다."
    assert sari(src, ref, ref) > sari(src, src, ref) > 0  # 원문 그대로 베끼면 SARI가 낮다
    m = text_metrics([src, "과태료의 100분의 20을 감경한다."], [ref, "벌금을 20% 줄여 준다."], [ref, ref],
                     ["과태료", "행정복지센터"], {"구비서류": {"alternatives": ["필요한 서류"], "sources": ["NIKL"]}})
    assert m["number_date_amount_match_rate"] == 1.0  # 100분의 20 = 20%
    assert m["preserved_terms_retention_rate"] == 0.5  # 행정복지센터 유지, 과태료 사라짐
    assert m["difficult_term_retention_rate"] == 0.0  # 구비서류가 풀렸음
    assert m["counts"]["difficult_terms_by_source"] == {"NIKL": 1}
