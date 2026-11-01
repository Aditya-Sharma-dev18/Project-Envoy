import instructor
from openai import AsyncOpenAI
from app.schemas import ExtractedProfile
from app.config import settings

# Initialize the Instructor-patched Async OpenAI client
# We use AsyncOpenAI so it doesn't block the FastAPI event loop
client = instructor.from_openai(AsyncOpenAI(api_key=settings.OPENAI_API_KEY))

async def parse_alumni_reply(reply_text: str) -> ExtractedProfile:
    """
    Takes raw chat text from LinkedIn and extracts structured company/role data.
    """
    system_prompt = (
        "You are an automated university data extraction agent. "
        "Extract the current job title, company, and location from the alumni's casual chat response. "
        "Do not invent facts. If the information is ambiguous, missing, or implies they are unemployed, "
        "mark the fields as null and lower your confidence score."
    )
    
    # The response_model argument forces the output to match our Pydantic schema
    extracted_data = await client.chat.completions.create(
        model="gpt-4o-mini",
        response_model=ExtractedProfile,
        temperature=0.0, # Zero temperature for maximum deterministic extraction
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Alumni Message: \"{reply_text}\""}
        ]
    )
    
    return extracted_data