"""Resolve and enforce immutable package and separated runtime roots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .errors import MutationBoundaryError, PathBoundaryError


WriteIntent = Literal["state", "output", "cache", "user_data_commit"]


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class RootLayout:
    """Resolved root ownership for one Career OS workspace."""

    package_root: Path
    user_data_root: Path
    state_root: Path
    output_root: Path
    cache_root: Path

    @classmethod
    def from_relative_paths(cls, config_path: Path, workspace: dict[str, str]) -> "RootLayout":
        base = config_path.resolve().parent
        values: dict[str, Path] = {}
        for key in ("package_root", "user_data_root", "state_root", "output_root", "cache_root"):
            raw = workspace.get(key)
            if not isinstance(raw, str) or not raw.strip():
                raise PathBoundaryError(f"{key} must be a non-empty relative path", details={"field": key})
            path = Path(raw)
            if path.is_absolute():
                raise PathBoundaryError(f"{key} must be relative to the config file", details={"field": key})
            values[key] = (base / path).resolve()
        layout = cls(**values)
        layout.validate_separation()
        return layout

    def validate_separation(self) -> None:
        runtime_roots = {
            "user_data_root": self.user_data_root,
            "state_root": self.state_root,
            "output_root": self.output_root,
            "cache_root": self.cache_root,
        }
        for name, path in runtime_roots.items():
            if path == self.package_root or _contains(self.package_root, path):
                raise PathBoundaryError(
                    f"{name} may not be inside package_root",
                    details={"field": name},
                )
        names = list(runtime_roots)
        for index, left_name in enumerate(names):
            for right_name in names[index + 1 :]:
                left = runtime_roots[left_name]
                right = runtime_roots[right_name]
                if left == right or _contains(left, right) or _contains(right, left):
                    raise PathBoundaryError(
                        f"{left_name} and {right_name} must be separable",
                        details={"left": left_name, "right": right_name},
                    )

    def assert_write_allowed(self, target: Path, intent: WriteIntent) -> Path:
        resolved = target.resolve()
        if resolved == self.package_root or _contains(self.package_root, resolved):
            raise MutationBoundaryError("normal runtime may not write into package_root")
        allowed = {
            "state": self.state_root,
            "output": self.output_root,
            "cache": self.cache_root,
            "user_data_commit": self.user_data_root,
        }[intent]
        if not (resolved == allowed or _contains(allowed, resolved)):
            raise MutationBoundaryError(
                "write target is outside the root owned by the declared intent",
                details={"intent": intent},
            )
        return resolved

    def assert_user_data_read_only(self, target: Path) -> Path:
        resolved = target.resolve()
        if not (resolved == self.user_data_root or _contains(self.user_data_root, resolved)):
            raise MutationBoundaryError("candidate data must be loaded through user_data_root")
        return resolved

