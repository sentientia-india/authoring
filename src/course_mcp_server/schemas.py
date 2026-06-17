from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Difficulty(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class CourseOutlineRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    audience: str = Field(min_length=2, max_length=200)
    duration_minutes: int = Field(default=60, ge=10, le=480)
    difficulty: Difficulty = Difficulty.beginner
    source_text: str | None = Field(default=None, max_length=60_000)
    language: str = Field(default="English", max_length=60)


class LessonDraftRequest(BaseModel):
    course_title: str = Field(min_length=3, max_length=300)
    module_title: str = Field(min_length=3, max_length=300)
    lesson_title: str = Field(min_length=3, max_length=300)
    objective: str = Field(min_length=3, max_length=500)
    audience: str = Field(min_length=2, max_length=200)
    tone: str = Field(default="professional and simple", max_length=100)


class QuizBankRequest(BaseModel):
    course_title: str = Field(min_length=3, max_length=300)
    learning_objectives: list[str] = Field(min_length=1, max_length=20)
    question_count: int = Field(default=10, ge=1, le=50)
    difficulty: Difficulty = Difficulty.beginner
    question_types: list[Literal["mcq", "true_false", "scenario"]] = Field(default=["mcq"])


class RoleplayScenarioRequest(BaseModel):
    course_title: str = Field(min_length=3, max_length=300)
    role: str = Field(min_length=2, max_length=120)
    situation: str = Field(min_length=10, max_length=1000)
    objective: str = Field(min_length=3, max_length=500)
    difficulty: Difficulty = Difficulty.beginner


class ValidateCourseSchemaRequest(BaseModel):
    course: dict


class ScormPackageRequest(BaseModel):
    course_title: str = Field(min_length=3, max_length=300)
    course_slug: str = Field(pattern=r"^[a-z0-9-]{3,80}$")
    modules: list[dict] = Field(min_length=1)
    scorm_version: Literal["1.2", "2004"] = "1.2"


class JobStatusRequest(BaseModel):
    job_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{6,80}$")
