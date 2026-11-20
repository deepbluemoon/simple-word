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


def test_unmask_fixes_josa_after_restored_word():
    from simple_word.placeholders import fix_josa
    slots = {"<T0>": "건강보험", "<T1>": "장기요양", "<T2>": "기초연금"}
    assert unmask("<T0>를 포함한 <T1>와 <T2>를 받습니다.", slots) == "건강보험을 포함한 장기요양과 기초연금을 받습니다."
    assert unmask("<T0>가 있고 <T1>는 <T2>로 갑니다.", slots) == "건강보험이 있고 장기요양은 기초연금으로 갑니다."
    assert unmask("<N0>명이 왔고 <N0>이 넘습니다.", {"<N0>": "3"}) == "3명이 왔고 3이 넘습니다."  # 명은 조사가 아님
    assert unmask("<N0>를 더하고 <N1>을 뺍니다.", {"<N0>": "1", "<N1>": "2"}) == "1을 더하고 2를 뺍니다."
    assert unmask("<N0>으로 나눕니다.", {"<N0>": "7"}) == "7로 나눕니다."  # 칠: ㄹ 받침 + 로
    assert unmask("<T0>으로부터", {"<T0>": "서울"}) == "서울로부터"
    assert unmask("<T0>로는 부족", {"<T0>": "지원금"}) == "지원금으로는 부족"
    assert unmask("<N0>가 늘었다", {"<N0>": "10%"}) == "10%가 늘었다"
    assert unmask("<N0>가 늘었다", {"<N0>": "100"}) == "100이 늘었다"
    assert unmask("<T0>이다", {"<T0>": "보험"}) == "보험이다"  # 이어지는 한글은 손대지 않음
    assert fix_josa("「민법」", "를") == "을" and fix_josa("ABC", "를") == "를"
