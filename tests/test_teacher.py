import json

from training import teacher

NIKL = "﻿연번,단어_용어,이표기_오표기,대안어(안)\n10,거버넌스,,\"협치, 관리\"\n283,마이스,MICE,전시 복합 산업\n"


def test_teacher_prompt_has_terms_and_rerun_skips_done(tmp_path):
    (tmp_path / "nikl_terms.csv").write_text(NIKL, encoding="utf-8")
    src = "기초생활수급자 과태료 거버넌스 체계를 AI로 개선한다."
    (tmp_path / "sentences.jsonl").write_text(json.dumps({"doc_id": "d", "idx": 0, "text": src}, ensure_ascii=False) + "\n")
    prompts = []
    gen = lambda p: prompts.append(p) or "기초생활수급자 과태료 협치 방식을 AI로 고쳐요."
    assert teacher.run(tmp_path, gen=gen, log=lambda *_: None) == 1
    assert teacher.run(tmp_path, gen=gen, log=lambda *_: None) == 0
    assert "그대로 씁니다(필요하면 뒤에 괄호로 쉽게 풀이): 과태료, 기초생활수급자" in prompts[0]
    assert "거버넌스 → 협치/관리" in prompts[0] and "영어 단어·약어는 그대로 씁니다: AI" in prompts[0]
    [pair] = [json.loads(l) for l in (tmp_path / "pairs.jsonl").open(encoding="utf-8")]
    assert pair["teacher"] == "ollama:gemma3:27b" and pair["passed"] is True
