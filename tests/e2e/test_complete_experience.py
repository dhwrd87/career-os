from __future__ import annotations
import copy
import json
import tempfile
import unittest
from pathlib import Path
from careeros import application, onboarding, opportunity, profile, resume, workspace, experience
from careeros.core.io import read_json, sha256_file
from careeros.document_quality import inspect_pdf, compare_geometry
from careeros.cli import main

FIXTURES = Path(__file__).resolve().parents[2] / 'fixtures/synthetic'
NOW = '2026-10-02T12:00:00Z'

class CompleteExperienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.target = Path(cls.temp.name) / 'workspace'
        f = FIXTURES / 'career-changer'
        workspace.init_workspace(cls.target, fixture_mode=True, timestamp=NOW)
        onboarding.start(cls.target, timestamp=NOW)
        result = onboarding.ingest(cls.target, f / 'onboarding/input.json', timestamp=NOW)
        if result['state'] == 'NEEDS_CLARIFICATION':
            onboarding.resolve(cls.target, f / 'onboarding/resolutions.json', timestamp=NOW)
        onboarding.commit(cls.target, actor='synthetic-human', timestamp=NOW)
        profile.build_profile(cls.target, timestamp=NOW)
        profile.build_role_family(cls.target, approve=True, timestamp=NOW)
        opp, _ = opportunity.ingest(cls.target, f / 'opportunity/strong.json', timestamp=NOW)
        cls.opp_id = opp['opportunity_id']
        opportunity.qualify(cls.target, cls.opp_id, timestamp=NOW)
        cls.build, cls.content, cls.artifact = resume.build(cls.target, cls.opp_id, timestamp=NOW)
        cls.validation, _ = resume.validate(cls.target, cls.build['build_id'])
        if cls.validation['status'] != 'PASS':
            raise AssertionError(cls.validation)
        cls.packet = application.prepare(cls.target, cls.opp_id, cls.build['build_id'], timestamp=NOW)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_complete_local_experience_and_outcomes(self):
        before = workspace.canonical_state_hash(self.target)
        exported = experience.export_resume(self.target, self.build['build_id'])
        self.assertEqual(exported['semantic_round_trip'], 'PASS')
        letter = experience.cover_letter(self.target, self.opp_id, self.build['build_id'])
        self.assertTrue(letter['evidence_ids'])
        self.assertEqual(letter['status'], 'REVIEW_REQUIRED')
        pack = experience.interview(self.target, self.opp_id, timestamp=NOW)
        self.assertTrue(all(pack['qa'].values()))
        app_id = self.packet['application_id']
        with self.assertRaises(PermissionError):
            experience.record_event(self.target, app_id, {'event_type': 'SUBMITTED'})
        experience.record_event(self.target, app_id, {'event_type': 'SUBMITTED', 'actor': 'synthetic-human', 'occurred_at': NOW, 'human_confirmed': True})
        experience.follow_up(self.target, app_id, due_at='2026-10-09T12:00:00Z', channel='EMAIL')
        report = experience.analytics(self.target, window_end='2026-10-12T00:00:00Z', timestamp='2026-10-12T00:00:00Z')
        self.assertEqual(report['cohort']['sample_count'], 1)
        self.assertEqual(report['cohort']['maturity_state'], 'INSUFFICIENT')
        result = experience.dashboard(self.target)
        self.assertGreater(result['documents'], 5)
        self.assertTrue((self.target / 'outputs/packets' / self.packet['packet_id'].split(':')[-1] / 'manifest.json').is_file())
        self.assertEqual(experience.queue_audit(self.target)['status'], 'PASS')
        self.assertEqual(before, workspace.canonical_state_hash(self.target))
        self.assertEqual(main(['--workspace', str(self.target), 'application', 'list']), 0)
        self.assertEqual(main(['--workspace', str(self.target), 'workspace', 'dashboard']), 0)

    def test_packet_repeatability_and_mutation_detection(self):
        before_artifact = read_json(self.target / 'state/resume-builds' / self.build['build_id'] / 'artifact.json')
        repeated, _, repeated_artifact = resume.build(self.target, self.opp_id, timestamp=NOW)
        self.assertEqual(repeated['build_id'], self.build['build_id'])
        self.assertEqual(repeated_artifact, before_artifact)
        self.assertEqual(application.prepare(self.target, self.opp_id, self.build['build_id'], timestamp=NOW), self.packet)
        pdf = self.target / 'outputs' / self.artifact['path']
        original = pdf.read_bytes()
        try:
            pdf.write_bytes(original + b'\nchanged')
            with self.assertRaises(PermissionError):
                application.prepare(self.target, self.opp_id, self.build['build_id'], timestamp=NOW)
            self.assertEqual(experience.queue_audit(self.target)['status'], 'FAIL')
        finally:
            pdf.write_bytes(original)

    def test_catalog_repeat_deduplicates_and_learning_runs(self):
        catalog = self.target / 'sources/catalog.json'
        job = read_json(FIXTURES / 'career-changer/opportunity/borderline.json')
        catalog.write_text(json.dumps([job]))
        first = experience.discovery(self.target, catalog, timestamp=NOW)
        second = experience.discovery(self.target, catalog, timestamp=NOW)
        self.assertEqual(first['counts']['NEW'], 1)
        self.assertEqual(second['counts']['NEW'], 0)
        self.assertEqual(second['imported'], [])
        course = self.target / 'sources/courses.json'
        course.write_text(json.dumps([{'provider':'OTHER','title':'Implementation Practice','course_id':'implementation-lab','url':'https://example.invalid/course','skill_topics':['Implementation Delivery'],'project_work':['Documented implementation project'],'last_verified_at':NOW,'availability':'AVAILABLE','level':'BEGINNER','cost_state':'FREE'}]))
        result = experience.learning(self.target, course, timestamp=NOW)
        self.assertEqual(result['canonical_mutations'], 0)
        self.assertIn('path_status', result['path'])

    def test_object_preflight_and_geometry_detect_drift(self):
        result = inspect_pdf(self.target / 'outputs' / self.artifact['path'])
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(compare_geometry(result, result)['status'], 'PASS')
        drift = copy.deepcopy(result)
        drift['geometry'][0]['words'][0]['x0'] += 10
        self.assertEqual(compare_geometry(drift, result)['status'], 'FAIL')

    def test_empty_job_requirements_cannot_establish_fit(self):
        job = read_json(FIXTURES / 'career-changer/opportunity/strong.json')
        job['opportunity_id'] = 'opp-unreviewed'
        job['requirements'] = []
        path = self.target / 'sources/unreviewed.json'
        path.write_text(json.dumps(job))
        opportunity.ingest(self.target, path, timestamp=NOW)
        decision = opportunity.qualify(self.target, job['opportunity_id'], timestamp=NOW)
        self.assertEqual(decision['decision'], 'BORDERLINE')

if __name__ == '__main__':
    unittest.main()
