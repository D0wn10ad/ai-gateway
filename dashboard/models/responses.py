"""Pydantic response models for usage and feedback APIs."""
from pydantic import BaseModel, Field


class ModelSpend(BaseModel):
    """Spend data for a single AI model."""
    model: str
    spend: float = Field(ge=0, description="Cost in USD (not displayed to users)")
    tokens: int = Field(ge=0, description="Total tokens used")
    percentage: float = Field(ge=0, le=100, description="Percentage of weekly limit")


class FeedbackRequest(BaseModel):
    """User feedback submission."""
    message: str = Field(min_length=10, max_length=5000)


class FeedbackResponse(BaseModel):
    """Feedback submission result."""
    success: bool
    detail: str


class UsageResponse(BaseModel):
    """Weekly usage data response."""
    period_start: str = Field(description="Start of billing period (e.g., 'Jan 17')")
    period_end: str = Field(description="End of billing period (e.g., 'Jan 24, 2025')")
    total_spend: float = Field(ge=0, description="Total spend in USD")
    percentage_used: float = Field(ge=0, le=100, description="Percentage of weekly limit used")
    models: list[ModelSpend] = Field(description="Breakdown by model")


class CoachingTip(BaseModel):
    """A single coaching tip from the AI analysis."""
    title: str
    detail: str
    category: str  # FILES, CONTEXT, MODEL, GENERAL
    estimated_savings: str | None = None


class CoachingStats(BaseModel):
    """Summary statistics shown alongside coaching tips."""
    total_requests: int = 0
    total_chats: int = 0
    avg_messages_per_chat: float = 0.0
    longest_chat_messages: int = 0
    total_file_uploads: int = 0
    unique_files: int = 0


class CoachingResponse(BaseModel):
    """AI coaching response with tips and stats."""
    period_start: str
    period_end: str
    summary: str | None = None
    tips: list[CoachingTip] = []
    stats: CoachingStats
    status: str  # "ready", "unavailable"
    cached: bool = False
    generated_at: str | None = None
