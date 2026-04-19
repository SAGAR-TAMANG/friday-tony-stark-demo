"""Result dataclasses — SUPER AGI pattern for structured tool outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Result:
    """Base result with common fields."""
    success: bool
    elapsed_ms: float = 0.0
    error: Optional[str] = None

    @property
    def formatted(self) -> str:
        if self.error:
            return f"[FAILED] {self.error}"
        return "[OK]"


@dataclass
class SuccessResult(Result):
    """Successful result with data."""
    success: bool = True
    data: dict = field(default_factory=dict)
    output: str = ""

    @property
    def formatted(self) -> str:
        if self.output:
            return f"[OK] {self.output}"
        return "[OK]"


@dataclass
class ErrorResult(Result):
    """Error result with details."""
    success: bool = False

    @property
    def formatted(self) -> str:
        return f"[FAILED] {self.error or 'Unknown error'}"
