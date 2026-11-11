import pytest
import asyncio
from app.utils.llm_parser import parse_alumni_reply

# A dataset of tricky, real-world edge cases
EVAL_DATASET = [
    {
        "input": "Hey man, I left Microsoft last month. Taking a break right now, traveling in Bali.",
        "expected_company": None,
        "expected_unemployed": True
    },
    {
        "input": "Still at Google, but they promoted me to Senior Product Manager! Moved to Seattle.",
        "expected_company": "Google",
        "expected_designation": "Senior Product Manager",
        "expected_location": "Seattle"
    },
    {
        "input": "I'm doing my Masters at Stanford right now.",
        "expected_company": "Stanford",  # or None, depending on your business logic
        "expected_designation": "Student/Masters",
        "expected_unemployed": False
    }
]

@pytest.mark.asyncio
async def test_llm_extraction_accuracy():
    """
    Evaluates the LLM's parsing accuracy against known edge cases.
    If the LLM hallucinates, this test fails and blocks deployment.
    """
    for test_case in EVAL_DATASET:
        # Run the LLM parser
        result = await parse_alumni_reply(test_case["input"])
        
        # Verify deterministic extraction
        if test_case.get("expected_company"):
            assert result.current_company and test_case["expected_company"].lower() in result.current_company.lower()
        else:
            assert result.current_company is None
            
        if test_case.get("expected_designation"):
            assert result.current_designation and test_case["expected_designation"].lower() in result.current_designation.lower()

        # Ensure confidence score is behaving logically
        assert 0.0 <= result.confidence_score <= 1.0

        print(f"PASS: {test_case['input'][:30]}... -> Extracted: {result.current_company} | {result.current_designation}")