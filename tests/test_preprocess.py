import json

from training.preprocess import preprocess

BODY = """- 겨울철 한파 대비 취약계층 보호 대책 발표 -
□ 신청은 주소지 행정복지센터(전화 044-205-1234, help@korea.kr)에서 받는다. 짧은 문장.
신청은 주소지 행정복지센터(전화 02-123-4567, a@b.kr)에서 받는다!
The AI-based ICT platform supports API, SDK and GPU.
<붙임> 대책 개요
담당자: 복지과 홍길동(044-000-0000)"""


def test_preprocess_cleans_masks_filters_and_records_drops(tmp_path):
    docs = [{"id": "d1", "body": BODY, "license": "KOGL-1"}, {"id": "d2", "body": " ", "license": "KOGL-1"}]
    (tmp_path / "docs.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs), encoding="utf-8")
    stats = preprocess(tmp_path)
    texts = [json.loads(l)["text"] for l in (tmp_path / "sentences.jsonl").open(encoding="utf-8")]
    assert texts == ["겨울철 한파 대비 취약계층 보호 대책 발표", "신청은 주소지 행정복지센터(전화 [전화], [이메일])에서 받는다."]
    assert stats["dropped"] == {"length": 1, "near_duplicate": 1, "hangul_ratio": 1, "doc_no_body": 1}
