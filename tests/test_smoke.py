import pytest

from scripts.smoke import SAMPLE_SENTENCES, validate


def responses():
    return (
        {"model_versions": [{"version": "v2", "roles": ["champion"]}]},
        {
            "model_version": "v2",
            "sentences": [
                {"original": sentence, "simple": sentence, "fallback": False}
                for sentence in SAMPLE_SENTENCES
            ],
        },
    )


def test_smoke_accepts_model_version_numeric_text_and_fallback_flags():
    validate(*responses())
    validate(*responses(), expected_model_version="v2")

    health, result = responses()
    result["model_version"] = "v1"
    with pytest.raises(ValueError, match="expected model v2"):
        validate(health, result, expected_model_version="v2")


def test_smoke_rejects_missing_fallback_or_changed_numbers():
    health, result = responses()
    result["sentences"][0].pop("fallback")
    with pytest.raises(ValueError, match="fallback"):
        validate(health, result)

    health, result = responses()
    result["sentences"][1]["simple"] = "지원 금액은 34,000원입니다."
    with pytest.raises(ValueError, match="numeric values"):
        validate(health, result)
