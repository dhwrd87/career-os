"""Protect demonstrated copy defects without grading prose by a house score."""
import copy
import unittest
from careeros import editorial
from careeros.career_outputs import master_resume_content
from careeros.recruiter_conversion import build_recruiter_summary_v2, public_copy_boundary, recruiter_copy_quality_v2
from careeros.resume_ats import validate_recruiter_summary
from careeros.resume_premium import summary_naturalness


def profile():
    return {'profile_id':'profile:copy-review','candidate':{'public_name':'Casey Rowan'},'preferences':{},'employment':[{'record_id':'employment:store','actual_title':'Store Associate','employer':'Example Market','start_year':2024,'visibility':'PUBLIC','evidence_ids':['evidence:service']}], 'projects':[], 'education':[], 'credentials':[], 'skills':[{'record_id':'skill:service','name':'Customer Support','visibility':'PUBLIC','evidence_ids':['evidence:service']}], 'evidence':[{'record_id':'evidence:service','visibility':'PUBLIC','verification_state':'VERIFIED','status':'ACTIVE','summary':'Supported customers and recorded daily requests.','actions':['Supported'],'outcomes':['Produced a documented, reviewable deliverable'],'employment_ids':['employment:store'],'project_ids':[]}]}


class RecruiterCopyExcellenceTests(unittest.TestCase):
    def test_intake_verb_recovers_its_source_object_without_a_generic_result(self):
        p=profile();before=copy.deepcopy(p);story=editorial.plan_storyline(p,{'display_name':'Customer Support','core_capabilities':['Customer Support']})
        bullets=editorial.build_bullet_candidates(p,story)
        self.assertEqual(bullets[0]['text'],'Supported customers and recorded daily requests.')
        self.assertEqual(bullets[0]['evidence_ids'],['evidence:service'])
        self.assertEqual(p,before)

    def test_master_uses_real_identity_and_the_same_complete_evidence(self):
        content=master_resume_content(profile())
        self.assertIn('Store Associate',content['summary'])
        self.assertNotIn('Technical Projects & Operations roles',content['summary'])
        self.assertEqual(content['employment'][0]['bullets'][0]['text'],'Supported customers and recorded daily requests.')

    def test_short_factual_summary_does_not_need_padding(self):
        p=profile();s=build_recruiter_summary_v2(p,{}, {'role_family_id':'support','display_name':'Customer Support'},selected_evidence_ids={'evidence:service'})
        self.assertLess(len(s['text'].split()),25)
        self.assertEqual(validate_recruiter_summary(s)['status'],'PASS')
        self.assertEqual(summary_naturalness(s)['status'],'PASS')
        self.assertNotIn('reviewable deliverable',s['text'])
        self.assertEqual(validate_recruiter_summary({'text':'Generic filler without any useful work history or specific results that a person could explain.', 'clauses':[{'summary_clause':'Generic claim','source_evidence_ids':[]}]})['status'],'FAIL')

    def test_project_caution_is_checked_on_the_rendered_subline(self):
        bad={'summary':'A factual summary.','projects':[{'contribution':'Reviewed requests; did not configure the production system.','bullets':[]}]}
        self.assertEqual(public_copy_boundary(bad)['status'],'FAIL')

    def test_missing_action_object_cannot_earn_a_passing_copy_check(self):
        content={'target_role':'Service Associate','summary':'Store Associate with customer service work and clear examples of daily support. Recorded requests, handled questions and kept the next shift informed about open work.', 'recruiter_summary':{'clauses':[{'source_evidence_ids':['evidence:service']}]},'employment':[{'bullets':[{'text':'Supported; produced a log.','evidence_ids':['evidence:service']}]}]}
        result=recruiter_copy_quality_v2(content,strategy={'key_differentiator':'Service work'})
        self.assertEqual(result['status'],'FAIL')
        self.assertIn('INCOMPLETE_ACTION',[f['code'] for f in result['findings']])

    def test_project_is_not_presented_as_target_role_employment(self):
        p=profile();p['projects']=[{'record_id':'project:practice','name':'Request Review Lab'}]
        p['evidence'].append({'record_id':'evidence:lab','visibility':'PUBLIC','summary':'Reviewed fictional requests and prepared a findings log without claiming production experience.','actions':['Reviewed'],'employment_ids':[],'project_ids':['project:practice']})
        s=build_recruiter_summary_v2(p,{}, {'role_family_id':'analysis','display_name':'Service Analyst'},selected_evidence_ids={'evidence:service','evidence:lab'})
        self.assertIn('fictional requests',s['text'])
        self.assertNotIn('claiming',s['text'])
        self.assertNotIn('Service Analyst experience',s['text'])
        self.assertIn('Store Associate',s['text'])

    def test_unapproved_metric_cannot_enter_a_restored_source_sentence(self):
        p=profile();p['evidence'][0].update(summary='Reduced wait time by 38%.',actions=['Reduced'],outcomes=[])
        story=editorial.plan_storyline(p,{'display_name':'Customer Support','core_capabilities':['Customer Support']})
        # Internal source/metric diagnostics retain the number; public text does not.
        self.assertFalse(any('38%' in b['text'] for b in editorial.build_bullet_candidates(p,story)))

    def test_writer_upgrade_preserves_the_accepted_career_specific_pdf(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from careeros import onboarding,workspace,profile as profile_api,lane_base
        from careeros.core.io import sha256_file,read_json
        fixture=Path(__file__).resolve().parents[2]/'fixtures/synthetic/early-career/onboarding'
        with tempfile.TemporaryDirectory() as folder:
            w=Path(folder)/'workspace';workspace.init_workspace(w,fixture_mode=True)
            onboarding.start(w);r=onboarding.ingest(w,fixture/'input.json')
            if r['state']=='NEEDS_CLARIFICATION':onboarding.resolve(w,fixture/'resolutions.json')
            onboarding.commit(w,actor='synthetic-human');profile_api.build_profile(w);profile_api.build_role_family(w,approve=True)
            first=lane_base.build_lane_base(w,accept=True,actor='synthetic-human')
            old=w/'outputs'/first['artifact']['path'];digest=sha256_file(old)
            active=read_json(w/'state/lane-bases/active.json')
            with patch.object(lane_base,'COMPILER_VERSION','0.4.3'):
                second=lane_base.build_lane_base(w)
            self.assertNotEqual(second['artifact']['path'],first['artifact']['path'])
            self.assertEqual(sha256_file(old),digest)
            self.assertEqual(read_json(w/'state/lane-bases/active.json'),active)
            lane_base.accept_lane_base(w,second['lane_base']['lane_base_id'],actor='synthetic-human')
            self.assertEqual(read_json(w/'state/lane-bases/active.json')['entries'][0]['lane_base_id'],second['lane_base']['lane_base_id'])
            self.assertEqual(sha256_file(old),digest)
