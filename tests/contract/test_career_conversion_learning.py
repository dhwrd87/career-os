from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from careeros.application_state import make_application_event
from careeros.conversion_learning import (
    aggregate_gaps,
    approve_learning_proposal,
    assess_course_credential_roi,
    build_career_conversion_cohort,
    build_causal_safeguard,
    build_conversion_learning_bundle,
    build_conversion_metrics,
    build_development_opportunities,
    build_learning_promotion_proposal,
    calibrate_qualification,
)


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def iso(days: int) -> str:
    return (BASE + timedelta(days=days)).isoformat().replace("+00:00", "Z")


def history(index: int, outcomes: list[str]) -> list[dict]:
    application_id = f"application:fictional-{index}"
    events = []
    previous = None
    prepared = make_application_event(application_id, "PACKET_PREPARED", previous_state=previous, actor="TEST", source="SYNTHETIC_FIXTURE", occurred_at=iso(index), recorded_at=iso(index), human_confirmed=False)
    events.append(prepared); previous = prepared["resulting_state"]
    submitted = make_application_event(
        application_id, "SUBMITTED", previous_state=previous, actor="FICTIONAL_CANDIDATE", source="HUMAN_CONFIRMED_EXTERNAL_SUBMISSION",
        occurred_at=iso(index + 1), recorded_at=iso(index + 1), human_confirmed=True,
        submission_lineage={"resume_artifact_id":f"resume:fictional-{index}","resume_sha256":f"{index + 1:064x}"[-64:],"cover_letter_hash":None,"application_answer_hashes":[],"job_snapshot_hash":f"{index + 101:064x}"[-64:],"submitted_artifact_hashes":[f"{index + 1:064x}"[-64:]],"submission_timestamp":iso(index + 1),"external_reference":None},
    )
    events.append(submitted); previous = submitted["resulting_state"]
    for offset, event_type in enumerate(outcomes, 2):
        refs = ["interview-stage:FINAL"] if event_type == "INTERVIEW_COMPLETED" and "FINAL" in outcomes else []
        event = make_application_event(application_id, event_type, previous_state=previous, actor="FICTIONAL_CANDIDATE", source="OBSERVED_EMPLOYER_EVENT", occurred_at=iso(index + offset), recorded_at=iso(index + offset), evidence_refs=refs, human_confirmed=True)
        events.append(event); previous = event["resulting_state"]
    return events


def dataset(count: int, *, role_families: list[str] | None = None, qualification_decisions: list[str] | None = None, with_outcomes: bool = True):
    opportunities=[]; applications=[]; qualifications=[]; variants=[]; logs={}; traces=[]
    role_families = role_families or ["role-family:operations"] * count
    qualification_decisions = qualification_decisions or ["QUALIFIED"] * count
    for index in range(count):
        opportunity_id=f"opportunity:fictional-{index}"; application_id=f"application:fictional-{index}"; qualification_id=f"qualification:fictional-{index}"; resume_id=f"resume:fictional-{index}"
        opportunities.append({"opportunity_id":opportunity_id,"seniority":"ENTRY","work_mode":"REMOTE","location":"Example State","industry":"Fictional Services","source_type":"SYNTHETIC","freshness_state":"FRESH"})
        applications.append({"application_id":application_id,"opportunity_id":opportunity_id,"qualification_id":qualification_id,"resume_artifact_id":resume_id})
        qualifications.append({"qualification_id":qualification_id,"role_family_id":role_families[index],"policy_version":"evidence-preserving-v2","decision":qualification_decisions[index],"gaps":[]})
        variants.append({"resume_artifact_id":resume_id,"role_family_id":role_families[index],"policy_version":"resume-policy-v1","resume_family":"OPERATIONS","resume_variant":"TARGETED" if index%2 else "LANE","summary_strategy":"NEED_LED","evidence_emphasis":["DOCUMENTATION"],"project_ordering":[],"template_version":"single-column-v1","ats_status":"PASS","employer_need_coverage":1.0,"material_evidence_loss":"PASS"})
        if with_outcomes:
            if index % 6 == 0: outcomes=["EMPLOYER_RESPONSE","INTERVIEW_SCHEDULED","INTERVIEW_COMPLETED","OFFER_RECEIVED"]
            elif index % 4 == 0: outcomes=["EMPLOYER_RESPONSE","INTERVIEW_SCHEDULED","REJECTED"]
            elif index % 3 == 0: outcomes=["REJECTED"]
            else: outcomes=["NO_RESPONSE_CLOSED"]
        else: outcomes=[]
        logs[application_id]=history(index,outcomes)
        traces.append({"trace_id":f"trace:{index}","needs":[{"need_id":f"need:{index}","need_statement":"Document operational handoffs","need_type":"OPERATIONS"}]})
    return opportunities, applications, logs, qualifications, variants, traces


def cohort_from(count: int, **kwargs):
    opportunities, applications, logs, qualifications, variants, traces = dataset(count, **kwargs)
    cohort, rows = build_career_conversion_cohort(candidate_profile_id="profile:fictional",opportunities=opportunities,applications=applications,event_logs=logs,qualifications=qualifications,resume_variants=variants,window_start=iso(0),window_end=iso(120),timestamp=iso(121))
    return cohort, rows, (opportunities, applications, logs, qualifications, variants, traces)


class CareerConversionLearningTests(unittest.TestCase):
    def test_01_tiny_cohort_blocks_strong_recommendation(self):
        cohort, _, _ = cohort_from(2)
        safeguard = build_causal_safeguard(cohort, comparison_name="tiny", observed_association="Variant A showed more interviews")
        gaps = {"gaps": [{"capability": "Fictional Platform", "job_count": 3}]}
        development = build_development_opportunities(cohort, gaps, [{"opportunity_id": "development:fictional", "action_type": "PROJECT", "capabilities": ["Fictional Platform"], "role_family_ids": ["role-family:operations"], "importance": "HIGH", "candidate_proximity": 0.8, "cost_score": 0.1, "time_score": 0.2, "evidence_generation_value": 0.9}])
        self.assertEqual(cohort["maturity_state"], "INSUFFICIENT")
        self.assertFalse(safeguard["strong_recommendation_allowed"])
        self.assertFalse(development[0]["recommendation_allowed"])
        self.assertEqual(development[0]["priority"], "OPTIONAL")

    def test_02_mature_cohort_produces_descriptive_conversion(self):
        cohort, rows, _ = cohort_from(30)
        metrics = build_conversion_metrics(cohort, rows)
        self.assertEqual(cohort["maturity_state"], "MATURE")
        self.assertIsNotNone(metrics["rates"]["APPLICATION_TO_INTERVIEW"]["rate"])
        self.assertTrue(metrics["descriptive_only"])

    def test_03_confounding_blocks_resume_causal_claim(self):
        cohort, _, _ = cohort_from(30)
        safeguard = build_causal_safeguard(cohort, comparison_name="resume", observed_association="Variant A showed higher interview conversion", confounders=["role family", "time period"])
        self.assertEqual(safeguard["classification"], "OBSERVED_ASSOCIATION")
        self.assertIn("does not establish causation", safeguard["approved_language"])

    def test_04_repeated_gap_is_classified(self):
        qualifications=[{"qualification_id":f"q:{i}","gaps":[{"capability":"Fictional Platform","match":"HARD_GAP"}]} for i in range(3)]
        result=aggregate_gaps(qualifications)
        self.assertEqual(result["gaps"][0]["classification"], "RECURRING_HARD_GAP")

    def test_05_one_off_credential_requirement_does_not_drive_high_roi(self):
        gaps=aggregate_gaps([{"qualification_id":"q:one","gaps":[{"capability":"Fictional Credential","match":"PREFERRED_AND_MISSING"}]}])
        result=assess_course_credential_roi(gaps,[{"option_id":"credential:fictional","capabilities":["Fictional Credential"],"employer_recognized":False,"creates_verifiable_evidence":True,"portfolio_alternative_exists":False}])
        self.assertEqual(result[0]["classification"], "LOW_ROI")
        self.assertFalse(result[0]["recommendation_allowed"])

    def test_06_qualification_overstrict_signal_requires_developing_sample(self):
        decisions=["NOT_QUALIFIED" if i in {0,4} else "QUALIFIED" for i in range(15)]
        cohort, rows, _ = cohort_from(15, qualification_decisions=decisions)
        self.assertEqual(cohort["maturity_state"], "DEVELOPING")
        self.assertEqual(calibrate_qualification(cohort,rows)["classification"], "POSSIBLE_OVERSTRICT")

    def test_07_unknown_outcomes_remain_unknown(self):
        cohort, rows, _ = cohort_from(5,with_outcomes=False)
        self.assertEqual(cohort["outcome_count"],0)
        self.assertEqual(cohort["unknown_outcome_count"],5)
        self.assertTrue(all(row["terminal_outcome"] is None for row in rows))

    def test_08_old_cohort_becomes_stale(self):
        opportunities, applications, logs, qualifications, variants, _ = dataset(10)
        cohort,_=build_career_conversion_cohort(candidate_profile_id="profile:fictional",opportunities=opportunities,applications=applications,event_logs=logs,qualifications=qualifications,resume_variants=variants,window_start=iso(0),window_end=iso(30),timestamp="2028-01-01T00:00:00Z")
        self.assertEqual(cohort["maturity_state"],"STALE")

    def test_09_mixed_role_families_require_stratification(self):
        families=[f"role-family:{i%4}" for i in range(20)]
        cohort,_,_=cohort_from(20,role_families=families)
        self.assertEqual(cohort["cohort_filters"]["comparability"]["status"],"STRATIFICATION_REQUIRED")

    def test_10_promotion_proposal_requires_human_approval(self):
        proposal=build_learning_promotion_proposal(source_cohorts=["cohort:fictional"],observation="Observed pattern",recommendation="Review policy",sample_maturity="MATURE",confidence="MEDIUM",affected_policy="qualification",expected_effect="Review calibration",risk="Overfitting",timestamp=iso(1))
        self.assertEqual(proposal["human_review_state"],"PENDING")
        with self.assertRaises(PermissionError): approve_learning_proposal(proposal,human_approved=False,approved_at=iso(2))
        self.assertEqual(approve_learning_proposal(proposal,human_approved=True,approved_at=iso(2))["human_review_state"],"APPROVED")

    def test_11_no_fabricated_history_enters_cohort(self):
        opportunities, applications, logs, qualifications, variants, _ = dataset(2)
        applications.append({"application_id":"application:guessed","opportunity_id":"opportunity:fictional-0","qualification_id":"qualification:fictional-0","resume_artifact_id":"resume:fictional-0"})
        logs["application:packet-only"]=[make_application_event("application:packet-only","PACKET_PREPARED",previous_state=None,actor="TEST",source="SYNTHETIC_FIXTURE",occurred_at=iso(1),recorded_at=iso(1))]
        cohort,rows=build_career_conversion_cohort(candidate_profile_id="profile:fictional",opportunities=opportunities,applications=applications,event_logs=logs,qualifications=qualifications,resume_variants=variants,window_start=iso(0),window_end=iso(120),timestamp=iso(121))
        self.assertEqual(cohort["sample_count"],2)
        self.assertNotIn("application:guessed",cohort["application_ids"])
        self.assertNotIn("application:packet-only",cohort["application_ids"])

    def test_12_bundle_never_mutates_policy_without_approval(self):
        opportunities,applications,logs,qualifications,variants,traces=dataset(15)
        bundle=build_conversion_learning_bundle(candidate_profile_id="profile:fictional",opportunities=opportunities,applications=applications,event_logs=logs,qualifications=qualifications,resume_variants=variants,employer_need_traces=traces,development_actions=[],course_options=[],window_start=iso(0),window_end=iso(120),timestamp=iso(121))
        self.assertEqual(bundle["policy_mutations"],[])
        self.assertEqual(bundle["fabricated_historical_events"],[])
        self.assertTrue(all(item["human_review_state"]=="PENDING" for item in bundle["promotion_proposals"]))
        self.assertEqual(bundle["qa"]["status"],"PASS")


if __name__ == "__main__":
    unittest.main()
