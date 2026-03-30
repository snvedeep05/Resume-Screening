from pydantic import BaseModel, Field
from typing import Optional

class JobCreateRequest(BaseModel):
    job_title: str
    job_config: dict = Field(default_factory=dict)

class JobUpdateRequest(BaseModel):
    job_title: Optional[str] = None
    job_config: Optional[dict] = None

class AIGenerateRequest(BaseModel):
    job_description: str

class DecisionUpdateRequest(BaseModel):
    decision: str = Field(pattern="^(shortlisted|rejected)$")
    reason: Optional[str] = None


class BulkDecisionRequest(BaseModel):
    result_ids: list[int]
    decision: str = Field(pattern="^(shortlisted|rejected)$")
    reason: Optional[str] = None
