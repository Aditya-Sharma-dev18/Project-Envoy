from pydantic import BaseModel, Field
from typing import Optional


class ExtractedProfile(BaseModel):
    """LLM output schema: structured data extracted from an alumni's casual reply."""

    current_company: Optional[str] = Field(
        default=None,
        description="The alum's current company or employer name. Null if not mentioned.",
    )
    current_designation: Optional[str] = Field(
        default=None,
        description="The alum's current professional title or role. Null if not mentioned.",
    )
    current_location: Optional[str] = Field(
        default=None,
        description="Current city and country/state of residence. Null if not mentioned.",
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Confidence level of the extracted facts based on message explicitness. "
            "Must be between 0.0 and 1.0"
        ),
    )
