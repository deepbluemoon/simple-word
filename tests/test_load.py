from scripts.load import percentile_ms, threshold_failures


def test_load_percentiles_and_limits_use_inclusive_thresholds():
    assert percentile_ms([0.4, 0.1, 0.3, 0.2], .95) == 400
    assert threshold_failures(500, .2, 500, .2) == []
    assert threshold_failures(501, .21, 500, .2) == [
        "p95 501.0 ms exceeds 500.0 ms",
        "429 rate 21.0% exceeds 20.0%",
    ]
