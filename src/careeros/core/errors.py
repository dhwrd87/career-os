"""Typed, serializable Career OS error contract."""

from __future__ import annotations

from typing import Any


class CareerOSError(Exception):
    code = "CAREER_OS_ERROR"
    retryable = False
    remediation = "Inspect the error context and correct the input or environment."

    def __init__(self, message: str, *, details: dict[str, object] | None = None,
                 context: dict[str, object] | None = None, cause: Exception | str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or details or {}
        self.safe_cause = cause.__class__.__name__ if isinstance(cause, Exception) else cause

    @property
    def details(self) -> dict[str, object]:
        return self.context

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message,
                                  "retryable": self.retryable, "remediation": self.remediation,
                                  "context": self.context}
        if self.safe_cause:
            payload["cause"] = self.safe_cause
        return payload


class ConfigValidationError(CareerOSError):
    code = "CONFIG_INVALID"
    remediation = "Correct careeros.yaml using CareerOSConfigV1, then rerun doctor."


class UnsupportedConfigVersionError(ConfigValidationError):
    remediation = "Use a configuration schema version supported by this package."


class SchemaInvalidError(CareerOSError):
    code = "SCHEMA_INVALID"
    remediation = "Correct every field reported by the registered schema."


class ContractValidationError(SchemaInvalidError):
    pass


class WorkspaceNotInitializedError(CareerOSError):
    code = "WORKSPACE_NOT_INITIALIZED"
    remediation = "Run `careeros init` in an empty directory."


class WorkspaceAlreadyInitializedError(CareerOSError, FileExistsError):
    code = "WORKSPACE_ALREADY_INITIALIZED"
    remediation = "Choose an empty directory or use the existing workspace."


class WorkspaceFormatUnsupportedError(CareerOSError):
    code = "WORKSPACE_FORMAT_UNSUPPORTED"
    remediation = "Install a compatible package or migrate through a supported intermediate version."


class MigrationRequiredError(CareerOSError):
    code = "MIGRATION_REQUIRED"
    remediation = "Run `careeros migrate --plan`, review it, then explicitly run `careeros migrate --apply`."


class MigrationFailedError(CareerOSError):
    code = "MIGRATION_FAILED"
    retryable = True
    remediation = "Inspect the backup and migration event, correct the blocker, and retry."


class DependencyMissingError(CareerOSError):
    code = "DEPENDENCY_MISSING"
    remediation = "Install the documented optional dependency group or system dependency."


class DependencyIncompatibleError(CareerOSError):
    code = "DEPENDENCY_INCOMPATIBLE"
    remediation = "Use a version within the range reported by doctor."


class PathBoundaryError(ConfigValidationError):
    code = "PATH_INVALID"
    remediation = "Use relative, separated package/data/state/output/cache paths."


class PermissionDeniedError(CareerOSError):
    code = "PERMISSION_DENIED"
    remediation = "Grant the workspace owner read/write access to runtime roots."


class PrivacyBoundaryViolationError(CareerOSError):
    code = "PRIVACY_BOUNDARY_VIOLATION"
    remediation = "Move runtime or candidate data outside package source."


class MutationBoundaryError(PrivacyBoundaryViolationError):
    pass


class RendererUnavailableError(CareerOSError):
    code = "RENDERER_UNAVAILABLE"
    remediation = "Install the resume extra and select a supported renderer."


class ValidationFailedError(CareerOSError):
    code = "VALIDATION_FAILED"
    remediation = "Resolve the failed validation gates before continuing."


class RecordConflictError(CareerOSError):
    code = "RECORD_CONFLICT"
    remediation = "Resolve the conflict explicitly; canonical facts are never silently overwritten."


class ChangesetConflictError(RecordConflictError):
    code = "CHANGESET_CONFLICT"
    remediation = "Regenerate the changeset from current canonical records, review it, and approve it again."


class ChangesetTransactionFailedError(CareerOSError):
    code = "CHANGESET_TRANSACTION_FAILED"
    retryable = True
    remediation = "Inspect the transaction journal and failure event; the previous canonical state was restored when rollback was required."


class ExternalActionNotAllowedError(CareerOSError):
    code = "EXTERNAL_ACTION_NOT_ALLOWED"
    remediation = "Keep the action local; Phase 3 has no external-action authority."


class ExternalActionPolicyError(ExternalActionNotAllowedError, ConfigValidationError):
    pass


class SourceEnrichmentApprovalRequiredError(CareerOSError):
    code = "SOURCE_ENRICHMENT_APPROVAL_REQUIRED"
    remediation = "Review the detected LinkedIn, GitHub, and portfolio URLs, then explicitly approve or decline one read-only enrichment pass."


class SecretInConfigError(ConfigValidationError):
    remediation = "Replace inline secrets with environment or keyring references."
