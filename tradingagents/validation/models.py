from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

IssueSeverity = Literal["warning", "blocking"]


class ValidationIssue(BaseModel):
    code: str
    severity: IssueSeverity
    message: str
    location: str | None = None


class ValidationResult(BaseModel):
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["verified", "verified_with_warnings", "research_only", "blocked"]
    strict_mode: bool = False
    issues: list[ValidationIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def blocking_issues(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "blocking"]

    @property
    def has_blocking_issues(self) -> bool:
        return bool(self.blocking_issues)

    @property
    def status_label(self) -> str:
        if self.status == "blocked":
            return "REPORT_BLOCKED"
        if self.status == "verified":
            return "ANALYST_VERIFIED"
        if self.status == "verified_with_warnings":
            return "VERIFIED_WITH_WARNINGS"
        return "RESEARCH_OUTPUT"
