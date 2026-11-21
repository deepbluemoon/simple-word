from scripts.review_feedback import latest_feedback


def test_review_feedback_keeps_last_vote_per_request_result_sentence():
    records = [
        {"request_id": "r1", "result_id": "d1", "sentence_index": 0, "vote": "up"},
        {"request_id": "r1", "result_id": "d1", "sentence_index": 1, "vote": "up"},
        {"request_id": "r1", "result_id": "d1", "sentence_index": 0, "vote": "down"},
        {"request_id": "r2", "result_id": "d1", "sentence_index": 0, "vote": "up"},
        {"vote": "legacy"},
    ]
    assert latest_feedback(records) == [records[1], records[2], records[3], records[4]]
