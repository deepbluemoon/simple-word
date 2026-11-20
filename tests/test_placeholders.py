from simple_word.numbers import numbers
from simple_word.placeholders import mask, mask_pair, unmask


def test_mask_and_unmask_round_trip_numbers_terms_and_names():
    src = "지원금 3억 5,000만 원을 기초연금 수급자에게 ‘26.6.25까지 20% 올려 「건강보험 수가 구조 혁신방안」에 따라 준다."
    masked, slots = mask(src)
    assert masked == "지원금 <N0> 원을 <T0> 수급자에게 <N1>까지 <N2> 올려 <T1>에 따라 준다."
    assert slots == {"<N0>": "3억 5,000만", "<T0>": "기초연금", "<N1>": "‘26.6.25", "<N2>": "20%", "<T1>": "「건강보험 수가 구조 혁신방안」"}
    out = unmask("<T1>에 따라 <T0> 받는 분께 <N1>까지 <N0> 원을 <N2> 더 줍니다.", slots)
    assert numbers(out) == numbers(src) and "기초연금" in out and "「건강보험 수가 구조 혁신방안」" in out


def test_same_fragment_gets_same_slot():
    masked, slots = mask("3명 중 3명이 왔다")
    assert masked == "<N0>명 중 <N0>명이 왔다" and slots == {"<N0>": "3"}


def test_unmask_rejects_missing_or_unknown_slots():
    _, slots = mask("1,000원과 2,000원")
    assert unmask("<N0>원", slots) is None
    assert unmask("<N0>원과 <N1>원 <N5>", slots) is None
    assert unmask("<N1>원, <N0>원", slots) == "2,000원, 1,000원"


def test_mask_pair_uses_single_pass_and_drops_reformatted_numbers():
    src = "인명피해는 1명이며 최근 30년 중 두 번째로 적었다."
    assert mask_pair(src, "다친 사람은 1명이고 지난 30년 동안 두 번째로 적어요.") == (
        "인명피해는 <N0>명이며 최근 <N1>년 중 두 번째로 적었다.", "다친 사람은 <N0>명이고 지난 <N1>년 동안 두 번째로 적어요.")
    assert mask_pair("상금 3백만 원", "상금 300만 원") is None  # 교사가 숫자 모양을 바꿈
    assert mask_pair("2026년 13일", "13일 2026년") is not None
    assert mask_pair("1과 13", "13과 1")[1] == "<N1>과 <N0>"  # 13 안의 1을 바꾸지 않음
