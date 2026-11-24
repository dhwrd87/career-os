from __future__ import annotations

import copy
import unittest

from careeros.production_family import (
    authorize_fallback,
    build_default_family_registry,
    build_fallback_route,
    build_family_registry,
    evaluate_family_delta,
    freeze_family_lineage,
    make_production_family,
    promote_family,
    resolve_family,
)


NOW = "2026-10-11T18:00:00Z"
BASELINE = {
    "global_policy_version": "global-v1",
    "document_standard_version": "document-v1",
    "canonical_schema_version": "canonical-v1",
    "summary_policy_version": "summary-v1",
    "ats_policy_version": "ats-v1",
    "renderer_version": "renderer-v1",
    "role_family_version": "roles-v1",
}


def target_family(parent_id: str, lane: str, suffix: str = "target"):
    records = [
        {"override_id": f"override:{suffix}:summary", "classification": "TARGET_JOB", "policy": "summary_policy", "setting": "mode", "rationale": "Fictional job needs require a job-specific summary."},
        {"override_id": f"override:{suffix}:skills", "classification": "TARGET_JOB", "policy": "skills_policy", "setting": "mode", "rationale": "Fictional job evidence controls skill order."},
        {"override_id": f"override:{suffix}:projects", "classification": "TARGET_JOB", "policy": "project_policy", "setting": "mode", "rationale": "Fictional job needs control project order."},
    ]
    return make_production_family(
        family_id=f"family:targeted:{suffix}", family_type="TARGETED", display_name=f"Fictional {lane} Role",
        parent_family_id=parent_id, role_family_id=lane, candidate_profile_id="profile:fictional",
        status="VALIDATED", version="1.0.0",
        policy_overrides={"summary_policy":{"mode":"JOB_NEED_LED"},"skills_policy":{"mode":"JD_RELEVANT_SUPPORTED"},"project_policy":{"mode":"EMPLOYER_NEED_RELEVANCE"}},
        override_records=records, validation_baseline=BASELINE, created_at=NOW,
    )


def registry_with_target(lane_key: str, suffix: str = "target"):
    base = build_default_family_registry(candidate_profile_id="profile:fictional", timestamp=NOW, version_baseline=BASELINE)
    lane_id = f"family:lane:{lane_key.casefold()}"
    target = target_family(lane_id, lane_key, suffix)
    return build_family_registry([*base["families"], target], global_versions=BASELINE, timestamp=NOW), lane_id, target["family_id"]


def content(summary: str, evidence: list[str], *, skills=None, projects=None, experience=None, facts=None, critical=None):
    return {"summary":summary,"evidence_ids":evidence,"skills":skills or [],"projects":projects or [],"experience":experience or [],"role_fact_ids":facts or [],"critical_role_fact_ids":critical or []}


class ProductionFamilyInheritanceTests(unittest.TestCase):
    def test_01_master_soc_lane_targeted_soc(self):
        registry, lane_id, target_id = registry_with_target("SECURITY_OPERATIONS", "soc")
        master = resolve_family("family:master-recruiter", registry, timestamp=NOW)
        lane = resolve_family(lane_id, registry, timestamp=NOW)
        target = resolve_family(target_id, registry, job_adaptations=[{"policy":"summary_policy","setting":"employer_need_focus","value":["alert monitoring","handoff"],"rationale":"Top fictional JD needs.","source_refs":["need:fictional-soc"]}], timestamp=NOW)
        self.assertEqual(master["resolution_path"], ["GLOBAL_PRODUCTION_STANDARD","family:master-recruiter"])
        self.assertEqual(lane["effective_configuration"]["summary_policy"]["mode"], "LANE_POSITIONING")
        self.assertEqual(target["setting_sources"]["summary_policy.employer_need_focus"]["origin"], "JOB_ADAPTATION")

    def test_02_master_noc_lane_targeted_noc(self):
        registry, lane_id, target_id = registry_with_target("NETWORK_OPERATIONS", "noc")
        trace = resolve_family(target_id, registry, job_adaptations=[{"policy":"project_policy","setting":"priority","value":["network monitoring","packet analysis"],"rationale":"Fictional NOC needs.","source_refs":["need:fictional-noc"]}], timestamp=NOW)
        self.assertEqual(trace["resolution_path"][-2:], [lane_id,target_id])
        self.assertTrue(trace["effective_configuration"]["ats_policy"]["ats_required"])

    def test_03_master_business_analysis_lane(self):
        registry = build_default_family_registry(candidate_profile_id="profile:fictional", timestamp=NOW, version_baseline=BASELINE)
        trace = resolve_family("family:lane:business_analysis_process", registry, timestamp=NOW)
        self.assertEqual(trace["effective_configuration"]["skills_policy"]["mode"], "ROLE_FAMILY_PRIORITY")
        self.assertIn("family:master-recruiter", trace["resolution_path"])

    def test_04_child_override_is_traced_and_parent_inherited(self):
        registry, lane_id, target_id = registry_with_target("VULNERABILITY_OPERATIONS", "vuln")
        trace = resolve_family(target_id, registry, timestamp=NOW)
        self.assertEqual(trace["setting_sources"]["summary_policy.mode"]["origin"], "LOCAL_OVERRIDE")
        self.assertEqual(trace["setting_sources"]["experience_policy.mode"]["origin"], "PARENT_INHERITED")
        self.assertTrue(any(item["source_family_id"] == lane_id for item in trace["inherited_policies"]))

    def test_05_unsafe_child_override_is_rejected(self):
        with self.assertRaises(PermissionError):
            make_production_family(
                family_id="family:targeted:unsafe", family_type="TARGETED", display_name="Unsafe Fictional",
                parent_family_id="family:lane:security_operations", status="DRAFT", version="1.0.0",
                policy_overrides={"ats_policy":{"ats_required":False}},
                override_records=[{"override_id":"override:unsafe","classification":"TARGET_JOB","policy":"ats_policy","setting":"ats_required","rationale":"Unsafe test."}],
                validation_baseline=BASELINE, created_at=NOW,
            )

    def test_06_missing_family_config_invokes_governed_fallback(self):
        registry = build_default_family_registry(timestamp=NOW, version_baseline=BASELINE)
        route = build_fallback_route(source_family_id="family:missing",failure_reason="FAMILY_CONFIG_MISSING",registry=registry,artifact_impact="Use global ATS-safe rendering.",qa_status="PASS",timestamp=NOW)
        self.assertEqual(route["fallback_family_id"], "ATS_STANDARD_SAFE_FALLBACK")
        self.assertFalse(route["authorized"])
        self.assertTrue(authorize_fallback(route,human_approved=True,actor="FICTIONAL_REVIEWER",approved_at=NOW)["authorized"])

    def test_07_ats_failure_uses_safe_terminal_fallback(self):
        registry, _, target_id = registry_with_target("SECURITY_OPERATIONS", "ats")
        route = build_fallback_route(source_family_id=target_id,failure_reason="ATS_FAILURE",registry=registry,artifact_impact="Recompose with ATS standard.",qa_status="PASS",timestamp=NOW)
        self.assertEqual(route["fallback_family_id"], "ATS_STANDARD_SAFE_FALLBACK")
        self.assertTrue(route["safety_preserved"])

    def test_08_stale_parent_invalidates_child(self):
        registry, _, target_id = registry_with_target("NETWORK_OPERATIONS", "stale")
        registry = copy.deepcopy(registry)
        registry["global_versions"]["document_standard_version"] = "document-v2"
        trace = resolve_family(target_id, registry, timestamp=NOW)
        self.assertEqual(trace["freshness"]["status"], "STALE")
        self.assertIn("parent_family", trace["freshness"]["stale_reasons"])

    def test_09_new_family_requires_ordered_promotion(self):
        family = make_production_family(family_id="family:specialized:fictional",family_type="SPECIALIZED",display_name="Fictional Specialty",parent_family_id="family:master-recruiter",status="DRAFT",version="1.0.0",validation_baseline=BASELINE,created_at=NOW)
        with self.assertRaises(ValueError): promote_family(family,target_status="PRODUCTION",gate_results={},actor="FICTIONAL_REVIEWER",timestamp=NOW)
        shadow,_=promote_family(family,target_status="SHADOW",gate_results={},actor="FICTIONAL_REVIEWER",timestamp=NOW)
        gates={key:True for key in ["SYNTHETIC_TESTS","ATS","VISUAL_QA","TRUTH_PROVENANCE","PRIVATE_ACCEPTANCE"]}
        validated,_=promote_family(shadow,target_status="VALIDATED",gate_results=gates,actor="FICTIONAL_REVIEWER",timestamp=NOW)
        production,promotion=promote_family(validated,target_status="PRODUCTION",gate_results=gates,actor="FICTIONAL_REVIEWER",timestamp=NOW)
        self.assertEqual(production["status"],"PRODUCTION")
        self.assertEqual(promotion["to_status"],"PRODUCTION")

    def test_10_submitted_lineage_keeps_historical_family_version(self):
        registry, _, target_id = registry_with_target("SECURITY_OPERATIONS", "history")
        trace=resolve_family(target_id,registry,timestamp=NOW)
        frozen=freeze_family_lineage(trace,artifact_id="resume:fictional",artifact_sha256="a"*64)
        updated=copy.deepcopy(registry)
        for family in updated["families"]:
            if family["family_id"]==target_id: family["version"]="1.1.0"
        self.assertEqual(frozen["family_version"],"1.0.0")
        self.assertEqual(frozen["family_trace_hash"],trace["trace_hash"])

    def test_11_targeted_delta_too_small_fails(self):
        registry,lane_id,target_id=registry_with_target("NETWORK_OPERATIONS","small")
        lane=resolve_family(lane_id,registry,timestamp=NOW); target=resolve_family(target_id,registry,timestamp=NOW)
        same=content("Same summary",["evidence:one"],skills=["Skill"],projects=["Project"],experience=["Role"])
        delta=evaluate_family_delta(parent_trace=lane,child_trace=target,parent_content=same,child_content=copy.deepcopy(same),relation="LANE_TO_TARGETED")
        self.assertIn("NO_MEANINGFUL_DELTA",delta["findings"])

    def test_12_material_role_fact_removal_fails(self):
        registry,lane_id,target_id=registry_with_target("SECURITY_OPERATIONS","loss")
        lane=resolve_family(lane_id,registry,timestamp=NOW); target=resolve_family(target_id,registry,timestamp=NOW)
        parent=content("Lane",["evidence:role","evidence:project"],skills=["Skill"],projects=["Project"],experience=["Role"],facts=["fact:leadership"],critical=["fact:leadership"])
        child=content("Target",["evidence:project"],skills=["Skill 2"],projects=["Project"],experience=[],facts=[])
        loss={"losses":[{"evidence_id":"evidence:role","classification":"CRITICAL_LOSS"}]}
        delta=evaluate_family_delta(parent_trace=lane,child_trace=target,parent_content=parent,child_content=child,relation="LANE_TO_TARGETED",material_loss=loss)
        self.assertIn("MATERIAL_EVIDENCE_LOSS",delta["findings"])
        self.assertIn("ROLE_IDENTITY_DRIFT",delta["findings"])


if __name__ == "__main__":
    unittest.main()
