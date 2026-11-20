from training.checks import check_pair

PRESERVE = ["과태료", "기초생활수급자"]
NIKL = {"MICE": {"alternatives": ["전시 복합 산업"], "sources": ["test"]}}


def reasons(src, tgt):
    return check_pair(src, tgt, PRESERVE, NIKL)["reject_reason"]


def test_checks_catch_t2_teacher_errors():
    src = "사전통지서를 받은 날부터 20일 이내에 자진납부 시 과태료의 100분의 20을 감경합니다."
    assert reasons(src, "통지서를 받은 날부터 20일 안에 스스로 내면 과태료의 20%를 줄여 줍니다.") is None  # 100분의 20 = 20%
    assert reasons(src, "통지서를 받고 20일 안에 내면 벌금을 20분의 1 줄여 줍니다.") == "numbers,preserve"
    src2 = "만 65세 이상 기초생활수급자를 대상으로 MICE 행사를 엽니다."
    assert reasons(src2, "65세 이상 어려운 어르신을 위해 MICE 행사를 엽니다.") == "preserve,conditions"
    assert reasons(src2, "65세 이상 기초생활수급자를 위해 전시 복합 산업 행사를 엽니다.") is None  # 사전 대체어 허용
    assert reasons("한국전력공사, 국립공원공단, 한국공항공사", "한국전력공사, 국립공원공단, 한국공항공사") is None
    assert reasons("’26/’27년 동절기", "2026년, 2027년 겨울") is None
    assert reasons("「약사법 시행령 의견, 「고시」 의견", "약사법 시행령 의견, 「고시」 의견") is None  # 안 닫힌 괄호
    assert reasons("3억 5,000만 원을 지원한다.", "3억 원을 지원해요.") == "numbers"


def test_checks_reject_long_or_multiline_teacher_output():
    src = "과태료를 감경합니다."  # 10자
    assert reasons(src, "과태료를 줄여 줍니다.") is None  # 11자, 1.1배
    assert reasons(src, "과태료를 줄여 드려요. 꼭 확인하세요.") == "length"  # 1.3배 초과
    assert reasons(src, "과태료를\n줄여요.") == "multiline"


def test_numbers_keep_their_dates_when_clauses_are_reordered():
    src = "1월에는 30명이 지원금을 신청했고, 2월에는 50명이 같은 지원금을 신청했습니다."
    reordered = "2월에는 50명이 같은 지원금을 신청했고, 1월에는 30명이 지원금을 신청했습니다."
    swapped = "1월에는 50명이 지원금을 신청했고, 2월에는 30명이 같은 지원금을 신청했습니다."

    assert reasons(src, reordered) is None
    assert reasons(src, swapped) == "numbers"


def test_repeated_equal_number_is_counted():
    src = "지원금 10만 원을 신청한 사람에게 한 차례 지급합니다."
    duplicated = "지원금 10만 원을 신청한 사람에게 10만 원을 한 차례 지급합니다."

    assert reasons(src, duplicated) == "numbers"
