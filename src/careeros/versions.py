"""Single authority for independently versioned Career OS components."""

from __future__ import annotations

PACKAGE_VERSION = "0.4.2"
WORKSPACE_FORMAT_VERSION = "1.1.0"
SUPPORTED_WORKSPACE_FORMAT_MIN = "1.0.0"
SUPPORTED_WORKSPACE_FORMAT_MAX = WORKSPACE_FORMAT_VERSION
CONFIG_SCHEMA_VERSION = "1.0.0"
SCHEMA_BUNDLE_VERSION = "1.24.0"
COMPILER_VERSION = "0.4.2"
RENDERER_VERSION = "0.3.7"
TEMPLATE_VERSION = "premium-ats-single-column-v1"
FONT_PROFILE_VERSION = "reportlab-helvetica-v1"
ADAPTER_API_VERSION = "1.0.0"
QUALIFICATION_POLICY_VERSION = "evidence-preserving-v2"
TRUTH_POLICY_VERSION = "evidence-bound-v1"
PRIVACY_POLICY_VERSION = "public-projection-v1"
OPPORTUNITY_FRESHNESS_POLICY_VERSION = "opportunity-freshness-v1"
APPLICATION_STATE_POLICY_VERSION = "application-state-v1"
INTERVIEW_PREP_POLICY_VERSION = "interview-evidence-pack-v1"
CONVERSION_LEARNING_POLICY_VERSION = "career-conversion-learning-v1"
PRODUCTION_FAMILY_POLICY_VERSION = "production-family-inheritance-v1"
LEARNING_PATH_POLICY_VERSION = "learning-path-intelligence-v1"
RECRUITER_CONVERSION_POLICY_VERSION = "recruiter-conversion-copy-v2"
OPPORTUNITY_REGISTRY_POLICY_VERSION = "cross-run-opportunity-dedupe-v1"
ACTIVE_POLICY_VERSIONS = {
    "qualification": QUALIFICATION_POLICY_VERSION,
    "truth": TRUTH_POLICY_VERSION,
    "privacy": PRIVACY_POLICY_VERSION,
    "opportunity_freshness": OPPORTUNITY_FRESHNESS_POLICY_VERSION,
    "application_state": APPLICATION_STATE_POLICY_VERSION,
    "interview_prep": INTERVIEW_PREP_POLICY_VERSION,
    "conversion_learning": CONVERSION_LEARNING_POLICY_VERSION,
    "production_family": PRODUCTION_FAMILY_POLICY_VERSION,
    "learning_path": LEARNING_PATH_POLICY_VERSION,
    "recruiter_conversion": RECRUITER_CONVERSION_POLICY_VERSION,
    "opportunity_registry": OPPORTUNITY_REGISTRY_POLICY_VERSION,
}
SKILL_VERSION = None


def version_report() -> dict[str, object]:
    return {
        "schema": "careeros.version-report.v1",
        "package_version": PACKAGE_VERSION,
        "supported_workspace_format": {
            "minimum": SUPPORTED_WORKSPACE_FORMAT_MIN,
            "maximum": SUPPORTED_WORKSPACE_FORMAT_MAX,
            "current": WORKSPACE_FORMAT_VERSION,
        },
        "schema_bundle_version": SCHEMA_BUNDLE_VERSION,
        "config_schema_version": CONFIG_SCHEMA_VERSION,
        "compiler_version": COMPILER_VERSION,
        "renderer_version": RENDERER_VERSION,
        "template_version": TEMPLATE_VERSION,
        "font_profile_version": FONT_PROFILE_VERSION,
        "adapter_api_version": ADAPTER_API_VERSION,
        "skill_version": SKILL_VERSION,
        "active_policy_versions": ACTIVE_POLICY_VERSIONS,
    }
