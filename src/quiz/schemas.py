from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class QuizGenerateRequest(BaseModel):
    document_id: str
    num_questions: int = Field(default=10, ge=1, le=30)
    difficulty: Literal["easy", "medium", "hard", "mixed"] = "mixed"


class QuizOption(BaseModel):
    label: str
    is_correct: bool


class QuizQuestion(BaseModel):
    question: str
    options: List[QuizOption]
    correct_answer: str

    topic: Optional[str] = None
    difficulty: Optional[str] = None
    bloom_level: Optional[str] = None

    source_page: Optional[int] = None
    source_chunk_id: Optional[str] = None

    grounding_score: float = Field(default=0.0, ge=0.0, le=1.0)
    status: Literal["verified", "rejected", "needs_review"] = "needs_review"

    validation_reasons: List[str] = Field(default_factory=list)


class QuizResponse(BaseModel):
    document_id: str
    questions: List[QuizQuestion]
    generated_count: int
    verified_count: int
    rejected_count: int
