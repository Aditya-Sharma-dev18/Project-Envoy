import pytest
from app.utils.llm_parser import parse_alumni_reply

# A dataset of tricky, real-world edge cases
EVAL_DATASET = [
    {
        "input": "Hey man, I left Microsoft last month. Taking a break right now, traveling in Bali.",
        "expected_company": None,
        "expected_unemployed": True,
    },
    {
        "input": "Still at Google, but they promoted me to Senior Product Manager! Moved to Seattle.",
        "expected_company": "Google",
        "expected_designation": "Senior Product Manager",
        "expected_location": "Seattle",
    },
    {
        "input": "I'm doing my Masters at Stanford right now.",
        "expected_company": "Stanford",
        "expected_designation": None,
        "expected_unemployed": False,
    },
]


def test_llm_extraction_accuracy():
    """
    Evaluates the LLM's parsing accuracy against known edge cases.
    If the LLM hallucinates, this test fails and blocks deployment.
    """
    for test_case in EVAL_DATASET:
        result = parse_alumni_reply(test_case["input"])

        if test_case.get("expected_company"):
            assert (
                result.current_company
                and test_case["expected_company"].lower() in result.current_company.lower()
            ), f"Expected company '{test_case['expected_company']}' in '{result.current_company}'"
        else:
            assert result.current_company is None, (
                f"Expected no company but got '{result.current_company}'"
            )

        if test_case.get("expected_designation"):
            assert (
                result.current_designation
                and test_case["expected_designation"].lower()
                in result.current_designation.lower()
            ), (
                f"Expected designation '{test_case['expected_designation']}' "
                f"in '{result.current_designation}'"
            )

        assert 0.0 <= result.confidence_score <= 1.0, (
            f"Confidence score {result.confidence_score} out of range"
        )

        print(
            f"PASS: {test_case['input'][:40]}... -> "
            f"{result.current_company} | {result.current_designation}"
        )
