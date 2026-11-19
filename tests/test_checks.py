from training.checks import check_pair

PRESERVE = ["과태료", "기초생활수급자"]
NIKL = {"MICE": ["전시 복합 산업"]}


def reasons(src, tgt):
    return check_pair(src, tgt, PRESERVE, NIKL)["reject_reason"]


def test_checks_catch_t2_teacher_errors():
    src = "사전통지서를 받은 날부터 20일 이내에 자진납부 시 과태료의 100분의 20을 감경합니다."
    assert reasons(src, "통지서를 받은 날부터 20일 안에 스스로 내면 과태료의 20%를 줄여 줍니다.") is None  # 100분의 20 = 20%
    assert reasons(src, "통지서를 받고 20일 안에 내면 벌금을 20분의 1 줄여 줍니다.") == "numbers,preserve"
    src2 = "만 65세 이상 기초생활수급자를 대상으로 MICE 행사를 엽니다."
    assert reasons(src2, "65세 이상 어려운 어르신을 위해 MICE 행사를 엽니다.") == "preserve,conditions"
    assert reasons(src2, "65세 이상 기초생활수급자를 위해 전시 복합 산업 행사를 엽니다.") is None  # 사전 대체어 허용
    assert reasons("3억 5,000만 원을 지원한다.", "3억 원을 지원해요.") == "numbers"
