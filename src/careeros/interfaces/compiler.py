"""Candidate-neutral compiler seam.

Implementations receive a validated CareerProfileV1 aggregate. Candidate facts are
never supplied by package defaults or module constants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class CareerProfileProvider(Protocol):
    def load_profile(self) -> Mapping[str, Any]:
        """Return one validated CareerProfileV1 aggregate without mutating its source."""


@dataclass(frozen=True)
class CompilerInputV1:
    profile: Mapping[str, Any]
    role_family: Mapping[str, Any]
    target_context: Mapping[str, Any]
    presentation_policy: Mapping[str, Any]


@dataclass(frozen=True)
class CompilerResult:
    build_id: str
    status: str
    artifacts: tuple[Mapping[str, Any], ...]
    validation: Mapping[str, Any]


@runtime_checkable
class CandidateNeutralCompiler(Protocol):
    def compile(self, request: CompilerInputV1) -> CompilerResult:
        """Compile solely from typed input, policy, and runtime services."""

