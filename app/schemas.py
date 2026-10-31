from pydantic import BaseModel, Field
from typing import Optional

# -----------------------------------------
# 1. Inbound Webhook Schema (From Unipile)
# -----------------------------------------
class UnipileWebhookPayload(BaseModel):
    account_id: str = Field(description="Your LinkedIn account ID on Unipile")
    message_id: str = Field(description="Unique ID of the message")
    sender_id: str = Field(description="The LinkedIn ID of the alumni sending the reply")
    text: str = Field(description="The actual text content of the alumni's reply")

# -----------------------------------------
# 2. LLM Output Schema (Instructor)
# -----------------------------------------
class ExtractedProfile(BaseModel):
    current_company: Optional[str] = Field(
        default=None, 
        description="The alum's current company or employer name. Null if not mentioned."
    )
    current_designation: Optional[str] = Field(
        default=None, 
        description="The alum's current professional title or role. Null if not mentioned."
    )
    current_location: Optional[str] = Field(
        default=None, 
        description="Current city and country/state of residence. Null if not mentioned."
    )
    confidence_score: float = Field(
        ge=0.0, 
        le=1.0, 
        description="Confidence level of the extracted facts based on message explicitness. Must be between 0.0 and 1.0"
    )