from pydantic import BaseModel, Field

# Schema for the nested token breakdown
class TokenUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)

# Schema for the POST /generate request body
class GenerateRequest(BaseModel):
    prompt: str
    simulated_usage: TokenUsage