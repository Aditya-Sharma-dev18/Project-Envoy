import instructor
from openai import AsyncOpenAI
from app.schemas import ExtractedProfile
from app.config import settings

# Point the OpenAI client to Groq's OpenAI-compatible endpoint
client = instructor.from_openai(
    AsyncOpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    ),
    mode=instructor.Mode.JSON,
)

async def parse_alumni_reply(reply_text: str) -> ExtractedProfile:
    system_prompt = (
        "You are an automated university data extraction agent. "
        "Extract the current job title, company, and location from the alumni's casual chat response. "
        "Do not invent facts. If the information is ambiguous, missing, or implies they are unemployed, "
        "mark the fields as null and lower your confidence score."
    )

    return await client.chat.completions.create(
        model="openai/gpt-oss-120b",
        response_model=ExtractedProfile,
        temperature=0.01,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f'Alumni Message: "{reply_text}"'},
        ],
    )