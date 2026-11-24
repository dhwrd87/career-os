from __future__ import annotations

import unittest

from careeros.learning_path import (
    assess_course_freshness,
    assess_redundancy,
    build_course_candidate,
    build_evidence_creation_plan,
    build_learning_objective,
    build_learning_path_impact,
    build_learning_roi,
    compare_provider_options,
    default_provider_adapters,
    evaluate_course,
    learning_path_qa,
    optimize_minimal_path,
    prioritize_career_gaps,
    propose_completion_evidence,
    qualification_impact,
)


NOW = "2026-10-11T12:00:00Z"


def gap(**overrides):
    source = {
        "gap_id": "gap:network-investigation", "source_gap_ids": ["observed-gap:1"],
        "gap_type": "PRACTICAL_SKILL", "gap_statement": "Applied packet analysis and network troubleshooting depth",
        "recurrence_count": 6, "job_frequency": 4.5, "requirement_importance": 5,
        "hard_gap_frequency": 3, "preferred_gap_frequency": 2, "current_evidence_strength": 2,
        "candidate_proximity": 4, "career_breadth": 4.5, "market_relevance": 4.5,
        "urgency": 4, "estimated_learning_effort": 2, "evidence_creation_potential": 5,
        "provenance": [{"type": "OBSERVED_JOB_REQUIREMENT", "ref": "synthetic-jd:1"}],
    }
    source.update(overrides)
    return prioritize_career_gaps(
        candidate_profile_id="synthetic-candidate", role_family_id="network-operations",
        gaps=[source], timestamp=NOW,
    )[0]


def objective(item):
    return build_learning_objective(
        item, objective_statement="Develop applied packet analysis and network troubleshooting evidence for monitored operations.",
        target_competency="packet analysis network troubleshooting Wireshark TCP IP DNS DHCP",
        starting_state="Foundational network evidence", desired_state="Applied investigation with inspectable artifacts",
        completion_evidence=["packet capture", "troubleshooting record", "technical write-up"],
        lane_impact=["NETWORK_OPERATIONS"], job_impact=["MONITORING", "ESCALATION"], timestamp=NOW,
    )


def course(provider="COURSERA", course_id="packet-lab", **overrides):
    source = {
        "provider": provider, "course_id": course_id, "title": "Applied Packet Analysis Lab",
        "url": f"https://example.invalid/{provider.casefold()}/{course_id}", "course_type": "COURSE",
        "skill_topics": ["Wireshark", "packet analysis", "network troubleshooting"],
        "curriculum_topics": ["TCP IP", "DNS", "DHCP", "traffic baselining", "incident documentation"],
        "credential_type": "COMPLETION_CERTIFICATE", "certificate_available": True,
        "estimated_duration": "8 hours", "cost_state": "FREE", "prerequisites": [],
        "project_work": ["investigation write-up"], "labs": ["packet capture analysis"],
        "assessments": ["scenario assessment"], "level": "INTERMEDIATE",
        "availability": "AVAILABLE", "last_verified_at": NOW, "source_refs": ["provider-page:synthetic"],
    }
    source.update(overrides)
    return build_course_candidate(source, timestamp=NOW)


class LearningPathSyntheticRegressionTests(unittest.TestCase):
    def setUp(self):
        self.gap = gap()
        self.objective = objective(self.gap)

    def evaluate(self, item, **kwargs):
        return evaluate_course(
            item, objective=self.objective, gap=self.gap,
            employer_terms=["packet analysis", "network troubleshooting", "DNS", "Wireshark"],
            **kwargs,
        )

    def test_01_beginner_foundation_is_ranked_from_observed_gap(self):
        item = gap(current_evidence_strength=0, candidate_proximity=2, estimated_learning_effort=4)
        self.assertIn(item["priority_class"], {"HIGH", "CRITICAL"})
        self.assertEqual(item["source_gap_ids"], ["observed-gap:1"])

    def test_02_career_changer_transferable_evidence_does_not_become_professional_technical_experience(self):
        impact = qualification_impact(gap(gap_type="EXPERIENCE", hard_gap_frequency=4), employer_allows_equivalence=False)
        self.assertEqual(impact["requirement_state_after_learning"], "UNSATISFIED")
        self.assertEqual(impact["state"], "READINESS_ONLY")

    def test_03_redundant_introductory_course_is_penalized(self):
        item = course(level="BEGINNER", skill_topics=["cybersecurity", "networking"], curriculum_topics=["cybersecurity", "networking"])
        evaluation, redundancy = self.evaluate(
            item, candidate_level="INTERMEDIATE",
            existing_evidence={"canonical_skills": ["cybersecurity", "networking"]},
        )
        self.assertEqual(redundancy["classification"], "HIGHLY_REDUNDANT")
        self.assertEqual(evaluation["candidate_level_match"], "TOO_BASIC")

    def test_04_narrow_tool_gap_supports_bounded_objective(self):
        narrow = gap(gap_type="TOOL", gap_statement="Packet-filter fluency", recurrence_count=4)
        built = build_learning_objective(
            narrow, objective_statement="Use packet filters to isolate DNS failures in supplied captures.",
            target_competency="Wireshark display filters", starting_state="Basic capture review",
            desired_state="Repeatable filtered investigation", completion_evidence=["annotated pcap"],
            lane_impact=["NETWORK_OPERATIONS"], job_impact=["TROUBLESHOOTING"], timestamp=NOW,
        )
        self.assertNotIn("Learn networking", built["objective_statement"])

    def test_05_learning_value_is_independent_from_credential_signal(self):
        item = course(certificate_available=False, credential_type="NO_CREDENTIAL", project_work=["capstone"], labs=["lab one", "lab two"])
        evaluation, _ = self.evaluate(item)
        self.assertGreater(evaluation["four_value_model"]["LearningValue"], evaluation["four_value_model"]["CredentialSignal"])

    def test_06_high_signal_credential_can_have_weak_practical_evidence(self):
        item = course(
            course_type="INDUSTRY_CERTIFICATION", credential_type="INDUSTRY_CERTIFICATION",
            certificate_available=True, project_work=[], labs=[], assessments=["exam"],
        )
        evaluation, _ = self.evaluate(item, market_required_credential=True, issuer_recognition=5)
        self.assertEqual(evaluation["credential_signal"], "REQUIRED_BY_MARKET")
        self.assertLess(evaluation["four_value_model"]["EvidenceCreationValue"], 3)

    def test_07_expensive_low_value_course_has_lower_roi(self):
        strong = course(course_id="strong", cost_state="FREE")
        weak = course(course_id="weak", cost_state="ONE_TIME", cost_amount=4000, curriculum_topics=["overview"], skill_topics=["overview"], labs=[], project_work=[])
        strong_eval, _ = self.evaluate(strong)
        weak_eval, _ = self.evaluate(weak)
        self.assertGreater(build_learning_roi(strong_eval, self.gap)["roi_score"], build_learning_roi(weak_eval, self.gap)["roi_score"])

    def test_08_free_high_value_provider_training_is_eligible(self):
        item = course(provider="MICROSOFT_LEARN", course_id="free-path")
        evaluation, _ = self.evaluate(item)
        self.assertTrue(evaluation["ranking_eligible"])
        self.assertEqual(evaluation["dimensions"]["COST_EFFICIENCY"], 5)

    def test_09_cross_lane_course_is_reused_in_minimal_path(self):
        second = build_learning_objective(
            gap(gap_id="gap:security-network"), objective_statement="Correlate network evidence with security events.",
            target_competency="packet analysis network troubleshooting incident documentation",
            starting_state="Foundational", desired_state="Applied", completion_evidence=["report"],
            lane_impact=["SOC", "NOC"], job_impact=["MONITORING"], timestamp=NOW,
        )
        item = course()
        first_eval, _ = self.evaluate(item)
        second_eval, _ = evaluate_course(item, objective=second, gap=gap(gap_id="gap:security-network"))
        path, steps, _ = optimize_minimal_path(
            candidate_profile_id="synthetic-candidate", role_family_id="cross-lane",
            target_role_ids=["soc", "noc"], objectives=[self.objective, second], candidates=[item],
            evaluations=[first_eval, second_eval], timestamp=NOW,
        )
        self.assertEqual(path["optimization"]["course_count"], 1)
        self.assertEqual(len(steps[0]["objective_ids"]), 2)

    def test_10_stale_or_removed_course_cannot_rank(self):
        stale = course(last_verified_at="2025-01-01T00:00:00Z")
        removed = course(course_id="removed", availability="REMOVED")
        stale_eval, _ = self.evaluate(stale)
        removed_eval, _ = self.evaluate(removed)
        self.assertFalse(stale_eval["ranking_eligible"])
        self.assertFalse(removed_eval["ranking_eligible"])

    def test_11_completion_creates_review_proposal_without_canonical_mutation(self):
        item = course()
        evaluation, _ = self.evaluate(item)
        path, _, _ = optimize_minimal_path(
            candidate_profile_id="synthetic-candidate", role_family_id="noc", target_role_ids=["noc"],
            objectives=[self.objective], candidates=[item], evaluations=[evaluation], timestamp=NOW,
        )
        proposal = propose_completion_evidence(
            learning_path=path, course=item, completion_artifacts=[{"type": "LAB_REPORT", "hash": "abc"}],
            candidate_self_report="Completed course", timestamp=NOW,
        )
        self.assertEqual(proposal["canonical_promotion_state"], "REVIEW_REQUIRED")
        self.assertEqual(proposal["canonical_mutations"], [])

    def test_12_affiliate_relationship_never_changes_ranking(self):
        plain = course(course_id="plain")
        affiliate = course(course_id="affiliate", affiliate_relationship=True)
        plain_eval, _ = self.evaluate(plain)
        affiliate_eval, _ = self.evaluate(affiliate)
        self.assertEqual(plain_eval["overall_routing_score"], affiliate_eval["overall_routing_score"])
        self.assertEqual(affiliate_eval["commercial_adjustment"], 0.0)

    def test_13_provider_unavailable_returns_no_results_without_failure(self):
        adapters = default_provider_adapters({})
        self.assertEqual(adapters["COURSERA"].search("packet analysis"), [])
        self.assertEqual(adapters["LINKEDIN_LEARNING"].search("packet analysis"), [])
        self.assertEqual(adapters["UDEMY"].search("packet analysis"), [])
        self.assertTrue(all(not adapter.descriptor()["requires_candidate_pii"] for adapter in adapters.values()))

    def test_14_prerequisite_mismatch_fails_closed(self):
        item = course(prerequisites=["advanced Python"], level="ADVANCED")
        evaluation, _ = self.evaluate(item, candidate_level="BEGINNER", satisfied_prerequisites=[])
        self.assertEqual(evaluation["candidate_level_match"], "PREREQUISITE_MISSING")
        self.assertFalse(evaluation["ranking_eligible"])

    def test_15_education_cannot_substitute_for_mandatory_experience(self):
        experience_gap = gap(gap_type="EXPERIENCE", hard_gap_frequency=5)
        impact = qualification_impact(experience_gap, employer_allows_equivalence=False)
        self.assertEqual(impact["requirement_state_after_learning"], "UNSATISFIED")
        self.assertTrue(impact["mandatory_professional_experience"])

    def test_user_preferences_adjust_ranking_without_overriding_prerequisites(self):
        preferred = course(
            provider="LINKEDIN_LEARNING", course_id="preferred", cost_state="ONE_TIME", cost_amount=80,
            delivery_modes=["HANDS_ON"], self_paced=True,
        )
        evaluation, _ = self.evaluate(
            preferred,
            preferences={
                "preferred_providers": ["LinkedIn Learning"],
                "subscriptions_owned": ["LinkedIn Learning"],
                "budget": 100,
                "learning_styles": ["HANDS_ON"],
                "self_paced_preference": True,
                "credential_preference": "PREFERRED",
            },
        )
        self.assertGreater(evaluation["preference_alignment"]["adjustment"], 0)
        self.assertFalse(evaluation["preference_alignment"]["hard_prerequisites_overridden"])

        blocked = course(course_id="blocked-by-prerequisite", prerequisites=["advanced Python"], level="ADVANCED")
        blocked_evaluation, _ = self.evaluate(
            blocked,
            candidate_level="BEGINNER",
            preferences={"preferred_providers": ["Coursera"], "budget": 10000},
        )
        self.assertFalse(blocked_evaluation["ranking_eligible"])
        self.assertEqual(blocked_evaluation["candidate_level_match"], "PREREQUISITE_MISSING")

    def test_end_to_end_minimal_path_and_qa(self):
        candidates = [course("COURSERA", "one"), course("LINKEDIN_LEARNING", "two"), course("UDEMY", "three")]
        evaluations = [self.evaluate(item)[0] for item in candidates]

        def plan_factory(step, selected_objective):
            return build_evidence_creation_plan(
                learning_step_id=step["learning_step_id"], target_evidence="Network troubleshooting case",
                project_type="TECHNICAL_WRITE_UP", objective=selected_objective["objective_statement"],
                required_tools=["Wireshark"], expected_actions=["capture", "filter", "analyze", "document"],
                expected_artifacts=["pcap", "report"], verification_method=["artifact hash", "human review"],
            )

        path, steps, plans = optimize_minimal_path(
            candidate_profile_id="synthetic-candidate", role_family_id="network-operations",
            target_role_ids=["noc-technician"], objectives=[self.objective], candidates=candidates,
            evaluations=evaluations, evidence_plan_factory=plan_factory, timestamp=NOW,
        )
        impact = qualification_impact(self.gap)
        result = learning_path_qa(
            gaps=[self.gap], objectives=[self.objective], candidates=candidates,
            evaluations=evaluations, path=path, evidence_plans=plans,
            qualification_impacts=[impact], privacy_findings=0,
        )
        path_impact = build_learning_path_impact(
            learning_path_id=path["learning_path_id"], lanes={"NOC": ["MATERIAL_LANE_IMPROVEMENT"]},
            qualification_impacts=[impact],
        )
        comparison = compare_provider_options(evaluations, candidates)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(steps), 1)
        self.assertTrue(path_impact["requires_evidence_review"])
        self.assertEqual(comparison["affiliate_influence"], 0)
        self.assertEqual(comparison["providers_considered"], ["COURSERA", "LINKEDIN_LEARNING", "UDEMY"])

    def test_course_freshness_unknown_without_verification(self):
        record = assess_course_freshness(
            course_candidate_id="course:unknown", last_verified_at=None,
            availability="AVAILABLE", as_of=NOW,
        )
        self.assertEqual(record["freshness_state"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()

class CourseVerificationBoundaryTests(unittest.TestCase):
    def test_import_time_does_not_fabricate_provider_verification(self):
        item = build_course_candidate({'title':'Synthetic Course','url':'https://example.invalid/course'},timestamp=NOW)
        self.assertEqual(item['freshness_state'],'UNKNOWN')
        self.assertEqual(item['last_verified_at'],'')
