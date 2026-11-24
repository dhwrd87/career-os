"""Synthetic acceptance for the actual V1 learning-to-career workflow."""
from __future__ import annotations
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from careeros import onboarding, opportunity, profile, workspace, updates
from careeros import learning_workflow as learning, learning_sources, learning_path
from careeros.core.io import read_json, atomic_write_json

FIXTURE=Path(__file__).resolve().parents[2]/'fixtures/synthetic/career-changer'
NOW='2026-10-02T12:00:00Z'


def setup(target):
    workspace.init_workspace(target,fixture_mode=True,timestamp=NOW)
    onboarding.start(target,timestamp=NOW)
    result=onboarding.ingest(target,FIXTURE/'onboarding/input.json',timestamp=NOW)
    if result['state']=='NEEDS_CLARIFICATION':onboarding.resolve(target,FIXTURE/'onboarding/resolutions.json',timestamp=NOW)
    onboarding.commit(target,actor='synthetic-human',timestamp=NOW)
    profile.build_profile(target,timestamp=NOW);profile.build_role_family(target,approve=True,timestamp=NOW)
    job=read_json(FIXTURE/'opportunity/borderline.json');job['opportunity_id']='opp-learning'
    job['requirements']=[{'capability':name,'level':'CORE','requirement_class':'REQUIRED','requirement_subtype':kind,**({'direct_experience':True} if kind=='EXPERIENCE' else {})} for name,kind in [('Python','SKILL'),('Statistics','EDUCATION'),('Cloud Practitioner','CREDENTIAL'),('Professional Implementation','EXPERIENCE')]]
    path=target/'sources/job.json';atomic_write_json(path,job);opportunity.ingest(target,path,timestamp=NOW);opportunity.qualify(target,job['opportunity_id'],timestamp=NOW)


def catalog(target):
    base={'provider':'OTHER','course_type':'COURSE','url':'https://example.invalid/learning','skill_topics':['Python','Statistics'],'curriculum_topics':['Python','Statistics'],'last_verified_at':NOW,'availability':'AVAILABLE','level':'BEGINNER','duration_hours':2,'estimated_duration':'2 hours','cost_state':'FREE','project_work':['Original notebook'],'assessments':['Review notebook']}
    rows=[{**base,'course_id':'foundations','title':'Python and Statistics Foundations'}, {**base,'course_id':'covered','title':'Subscribed practice','cost_state':'ONE_TIME','cost_amount':60,'cost_currency':'USD','price_verified_at':NOW,'subscription_plans':['PRACTICE_PLUS']}, {**base,'course_id':'over-budget','title':'Expensive practice','cost_state':'ONE_TIME','cost_amount':500,'cost_currency':'USD','price_verified_at':NOW}, {**base,'course_id':'stale','title':'Stale course','last_verified_at':'2025-01-01T00:00:00Z'}, {**base,'course_id':'unknown-cost','title':'Unpriced course','cost_state':'UNKNOWN'}, {**base,'course_id':'reference','title':'Statistics reference','course_type':'KNOWLEDGE_RESOURCE','skill_topics':['Statistics'],'curriculum_topics':['Statistics']}, {**base,'course_id':'cert','title':'Cloud Practitioner certification attempt','course_type':'INDUSTRY_CERTIFICATION','skill_topics':['Cloud Practitioner'],'curriculum_topics':['Cloud Practitioner'],'credential_type':'INDUSTRY_CERTIFICATION','certificate_available':True}]
    path=target/'sources/courses.json';atomic_write_json(path,rows);return path


class LearningWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.target=Path(self.temp.name)/'workspace';setup(self.target)
        learning.preferences(self.target,{'budget':10,'currency':'USD','weekly_hours':4,'weeks_available':3,'candidate_level':'BEGINNER','subscriptions_owned':['PRACTICE_PLUS'],'learning_styles':['LAB'],'current_knowledge':[],'project_hours':2})
        self.catalog=catalog(self.target)

    def test_gap_types_constraints_provider_neutrality_and_repeatability(self):
        before=workspace.canonical_state_hash(self.target);result=learning.build(self.target,self.catalog,timestamp=NOW)
        self.assertTrue({'PRACTICAL_SKILL','KNOWLEDGE','CREDENTIAL','EXPERIENCE'} <= {g['gap_type'] for g in result['gap_priorities']})
        self.assertTrue(result['steps']);self.assertTrue(result['evidence_plans']);self.assertTrue(result['learning_roi']);self.assertTrue(result['provider_comparison'])
        self.assertTrue(any(s['step_type']=='PROJECT' for s in result['steps']))
        chosen={s['course_candidate_id'] for s in result['steps']};index={c['course_candidate_id']:c for c in result['course_candidates']}
        self.assertFalse(any(index[c]['title'] in {'Expensive practice','Stale course','Unpriced course'} for c in chosen if c))
        self.assertLessEqual(float(result['path']['estimated_total_time'].split()[0]),12)
        self.assertLessEqual(float(result['path']['estimated_total_cost'].split()[0]),10)
        covered=next(c['course_candidate_id'] for c in result['course_candidates'] if c['title']=='Subscribed practice')
        self.assertTrue(any(e['ranking_eligible'] for e in result['course_evaluations'] if e['course_candidate_id']==covered))
        for evaluation in result['course_evaluations']:self.assertEqual(evaluation['commercial_adjustment'],0)
        self.assertTrue(all(a['requirement_state']=='UNSATISFIED' for a in result['experience_actions']))
        self.assertEqual(result['run_id'],learning.build(self.target,self.catalog,timestamp=NOW)['run_id'])
        self.assertEqual(workspace.canonical_state_hash(self.target),before)
        self.assertTrue((self.target/'outputs/learning/learning-roadmap.pdf').is_file())
        learning.preferences(self.target,{'budget':0,'currency':'USD','max_duration_hours':0})
        restricted=learning.build(self.target,self.catalog,timestamp=NOW)
        self.assertEqual(restricted['steps'],[]);self.assertTrue(restricted['uncovered_gap_ids'])

    def test_verified_evidence_governed_update_and_reassessment(self):
        result=learning.build(self.target,self.catalog,timestamp=NOW);step=next(s for s in result['steps'] if s['step_type']=='PROJECT' and 'Python' in s['title']);sid=step['learning_step_id']
        before=workspace.canonical_state_hash(self.target)
        with self.assertRaises(ValueError):learning.record_progress(self.target,{'step_id':sid,'state':'COMPLETED','actor':'synthetic-human'},timestamp=NOW)
        for state in ('IN_PROGRESS','COMPLETED'):learning.record_progress(self.target,{'step_id':sid,'state':state,'actor':'synthetic-human'},timestamp=NOW)
        artifact=self.target/'sources/python-project.txt';artifact.write_text('Synthetic project: parsed CSV and tested null values. All checks passed.\n')
        with self.assertRaises(PermissionError):learning.record_progress(self.target,{'step_id':sid,'state':'VERIFIED','actor':'synthetic-human'},timestamp=NOW)
        learning.record_progress(self.target,{'step_id':sid,'state':'VERIFIED','actor':'synthetic-human','human_confirmed':True,'artifacts':['sources/python-project.txt']},timestamp=NOW)
        self.assertEqual(workspace.canonical_state_hash(self.target),before)
        # A missing projection is recovered from the append-only journal.
        for projection in (self.target/'state/learning/completions').glob('*.json'):projection.unlink()
        self.assertEqual(learning.status(self.target)['completions'][0]['state'],'VERIFIED')
        proposal={'step_id':sid,'actor':'synthetic-human','summary':'Parsed a synthetic CSV using Python and tested missing values.','actions':['Wrote parser','Tested missing values'],'skill_claims':[{'name':'Python','proficiency':'PRACTICED'}]}
        changeset=learning.propose_profile_update(self.target,proposal,timestamp=NOW)
        self.assertEqual(workspace.canonical_state_hash(self.target),before)
        updates.approve(self.target,changeset['changeset_id'],actor='synthetic-human',timestamp=NOW);updates.commit(self.target,changeset['changeset_id'],actor='synthetic-human',timestamp=NOW)
        self.assertNotEqual(workspace.canonical_state_hash(self.target),before)
        self.assertEqual(learning.status(self.target)['freshness'],'STALE_REBUILD_REQUIRED')
        with self.assertRaises(PermissionError):learning.build(self.target,self.catalog,timestamp=NOW)
        reassessed=learning.reassess(self.target,timestamp=NOW)
        self.assertTrue(reassessed['results'])
        remaining=next(r['remaining_gaps'] for r in reassessed['results'] if r['opportunity_id']=='opp-learning')
        self.assertIn('Professional Implementation',remaining)
        self.assertNotIn('Python',remaining)
        newprofile=read_json(self.target/'state/profile/career-profile.json');self.assertTrue(any(s['name']=='Python' for s in newprofile['skills']))
        self.assertTrue(all(not e.get('employment_ids') for e in newprofile['evidence'] if e['record_id'].startswith('evidence:learning-')))
        self.assertEqual(learning.status(self.target)['freshness'],'STALE_REBUILD_REQUIRED')
        artifact.write_text('Changed after verification')
        with self.assertRaises(PermissionError):learning.propose_profile_update(self.target,proposal,timestamp=NOW)

    def test_award_is_explicit_and_not_inferred_from_preparation(self):
        result=learning.build(self.target,self.catalog,timestamp=NOW);step=next(s for s in result['steps'] if s['step_type']=='CERTIFICATION_ATTEMPT');sid=step['learning_step_id']
        artifact=self.target/'sources/award.txt';artifact.write_text('Synthetic issuer award for Cloud Practitioner, issued 2026-10-02.')
        for state in ('IN_PROGRESS','COMPLETED','VERIFIED'):
            learning.record_progress(self.target,{'step_id':sid,'state':state,'actor':'synthetic-human','human_confirmed':True,'artifacts':['sources/award.txt']},timestamp=NOW)
        payload={'step_id':sid,'actor':'synthetic-human','summary':'Passed the reviewed synthetic certification assessment.','actions':['Completed assessment'],'credential':{'kind':'INDUSTRY_CERTIFICATION','title':'Cloud Practitioner','issuer':'Example Training Authority','issued_date':'2026-10-02','award_confirmed':True}}
        proposal=learning.propose_profile_update(self.target,payload,timestamp=NOW)
        self.assertTrue(any(c['record_type']=='credentials' for c in proposal['proposed_changes']))
        self.assertFalse(any(c['record_type']=='employment' for c in proposal['proposed_changes']))
        # A changed resource classification receives a new step identity. Old
        # verified progress must not transfer to a preparation-only snapshot.
        courses=read_json(self.catalog)
        for course in courses:
            if course['course_id']=='cert':course['course_type']='INDUSTRY_CERTIFICATION_PREP'
        atomic_write_json(self.catalog,courses)
        rebuilt=learning.build(self.target,self.catalog,timestamp=NOW)
        prep=next(s for s in rebuilt['steps'] if s['step_type']=='CERTIFICATION_PREP')
        self.assertNotEqual(sid,prep['learning_step_id'])
        for state in ('IN_PROGRESS','COMPLETED','VERIFIED'):
            learning.record_progress(self.target,{'step_id':prep['learning_step_id'],'state':state,'actor':'synthetic-human','human_confirmed':True,'artifacts':['sources/award.txt']},timestamp=NOW)
        payload['step_id']=prep['learning_step_id']
        with self.assertRaises(ValueError):learning.propose_profile_update(self.target,payload,timestamp=NOW)

    def test_actual_cli_and_initial_workspace_navigation(self):
        import io,json
        from contextlib import redirect_stdout
        from careeros.cli import main
        from careeros import experience
        experience.dashboard(self.target)
        self.assertIn('href="learning/index.html"', (self.target/'outputs/index.html').read_text())
        for command in (['learning','gaps'],['learning','preferences'],['learning','build','--catalog',str(self.catalog)],['learning','status'],['learning','reassess']):
            with self.subTest(command=command),redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(['--workspace',str(self.target),*command]),0)
                self.assertIsInstance(json.loads(output.getvalue()),dict)

    def test_preferences_reject_invalid_inputs(self):
        for payload in ({'budget':-1},{'weekly_hours':False},{'knowledge_levels':{'Python':'EXPERT'}},{'self_paced_preference':'yes'},{'secret':'no'}):
            with self.subTest(payload=payload),self.assertRaises(ValueError):learning.preferences(self.target,payload)

    def test_saved_plan_expires_without_profile_or_preference_changes(self):
        learning.build(self.target,self.catalog,timestamp=NOW)
        self.assertEqual(learning.status(self.target,timestamp=NOW)['freshness'],'CURRENT')
        old=learning.status(self.target,timestamp='2026-11-10T00:00:00Z')
        self.assertEqual(old['freshness'],'STALE_REBUILD_REQUIRED')
        self.assertIn('REVERIFY',old['source_freshness'].values())


class LiveLearningReaderTests(unittest.TestCase):
    def test_live_reader_parses_source_facts_and_never_invents_missing_fields(self):
        page=b'<html><title>Python practice</title><script type="application/ld+json">{"@type":"Course","name":"Python practice","teaches":["Python"],"provider":{"name":"Example Academy"},"timeRequired":"PT2H","offers":{"price":0,"priceCurrency":"USD"}}</script></html>'
        record=learning_sources.normalize_page('https://example.org/python',page,timestamp=NOW)
        self.assertEqual(record['cost_state'],'FREE');self.assertFalse(record['certificate_available']);self.assertEqual(record['level'],'UNKNOWN')
        self.assertEqual(learning_path.learning_hours(record),2)
        candidate=learning_path.build_course_candidate(record,timestamp=NOW);self.assertEqual(candidate['freshness_state'],'CURRENT')
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'workspace';workspace.init_workspace(target,timestamp=NOW)
            calls=[]
            def fetch(url):
                calls.append(url)
                return b'<urlset><url><loc>https://example.org/python</loc></url></urlset>' if url.endswith('sitemap.xml') else page
            result=learning_sources.discover(target,sources=['https://example.org/sitemap.xml'],query='Python',approved=True,fetcher=fetch,timestamp=NOW)
            self.assertEqual(result['status'],'PASS');self.assertEqual(len(calls),2);self.assertFalse(result['candidate_data_transmitted'])
            with self.assertRaises(PermissionError):learning_sources.discover(target,sources=['https://example.org'],query='candidate@example.org',approved=True,fetcher=fetch)
            with self.assertRaises(PermissionError):learning_sources.discover(target,sources=['https://example.org'],query='Python',approved=False,fetcher=fetch)
            failed=learning_sources.discover(target,sources=['https://example.org'],query='Python',approved=True,fetcher=lambda u: (_ for _ in ()).throw(OSError('offline')))
            self.assertEqual(failed['status'],'NO_VERIFIED_RESOURCES');self.assertTrue(failed['failures'])

    def test_private_addresses_and_stale_prices_rejected(self):
        for url in ('http://example.org','https://localhost/','https://127.0.0.1/','https://example.invalid/'):
            with self.subTest(url=url),self.assertRaises(ValueError):learning_sources.public_url(url)
        self.assertIsNone(learning_path.learning_cost({'provider':'OTHER','cost_state':'ONE_TIME','cost_amount':5,'cost_currency':'USD','price_verified_at':'2025-01-01T00:00:00Z'},{'currency':'USD','as_of':NOW}))

if __name__=='__main__':unittest.main()
