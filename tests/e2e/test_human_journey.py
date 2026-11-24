"""The five user journeys exercise the existing engines with real artifacts."""
import copy,json,tempfile,unittest,io
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from careeros import journey,onboarding,opportunity,profile,workspace,learning_workflow
from careeros.core.io import read_json,atomic_write_json,sha256_file
from careeros.cli import main
FIXTURE=Path(__file__).resolve().parents[2]/'fixtures/synthetic'
NOW='2026-11-24T12:00:00Z'


def create(target,persona='career-changer'):
    source=FIXTURE/persona;workspace.init_workspace(target,fixture_mode=True,timestamp=NOW);onboarding.start(target,timestamp=NOW)
    result=onboarding.ingest(target,source/'onboarding/input.json',timestamp=NOW)
    if result['state']=='NEEDS_CLARIFICATION':onboarding.resolve(target,source/'onboarding/resolutions.json',timestamp=NOW)
    onboarding.commit(target,actor='synthetic-human',timestamp=NOW);profile.build_profile(target,timestamp=NOW);profile.build_role_family(target,approve=True,timestamp=NOW)
    return source


def jobs(target,source):
    strong=read_json(source/'opportunity/strong.json');other=copy.deepcopy(strong);other.update(opportunity_id='second-ready',employer_name='Example Learning Services',role_title='Training Coordinator',job_description='Example Learning Services seeks a Training Coordinator. Required: Process Mapping, Training and Data Cleanup.')
    same=copy.deepcopy(strong);same.update(opportunity_id='same-title-ready',employer_name='Example Coordination Group',job_description=strong['job_description'].replace(strong['employer_name'],'Example Coordination Group'))
    stretch=read_json(source/'opportunity/borderline.json')
    dream=read_json(FIXTURE/'learning/job.json');dream.update(role_title='Data Operations Lead',opportunity_id='dream-role',job_description=dream['job_description'].replace('Implementation Analyst','Data Operations Lead'))
    path=target/'sources/jobs.json';atomic_write_json(path,[strong,other,same,stretch,dream]);return path


class HumanJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.target=Path(self.temp.name)/'workspace';self.source=create(self.target);self.catalog=jobs(self.target,self.source)
        self.request={'catalog':str(self.catalog),'locations':['Remote US'],'dream_roles':['Data Operations Lead'],'prepare_top':2}

    def test_find_titles_batch_resumes_and_targeted_dream_plan(self):
        before=workspace.canonical_state_hash(self.target)
        result=journey.find_jobs(self.target,self.request,timestamp=NOW)
        self.assertEqual(result['categories'],{'Ready Now':3,'Stretch Roles':1,'Dream Roles':1})
        self.assertEqual(result['resume_batch']['prepared'],2)
        report=(self.target/'outputs/job-search/index.html').read_text()
        for draft in result['resume_batch']['results']:self.assertIn('../'+draft['path'],report)
        roles=journey.suggest_roles(self.target,timestamp=NOW)
        self.assertTrue(any('Training Coordinator' in row['example_titles'] for row in roles['lanes']))
        self.assertFalse(any('Implementation Delivery' in row['why'] for row in roles['lanes'] if row['display_name']=='Software Implementation Specialist'))
        self.assertFalse(any('LANGUAGES Associate' in row['example_titles'] for row in roles['lanes']))
        catalog=read_json(FIXTURE/'learning/courses.json')
        for course in catalog:
            if course['last_verified_at'].startswith('2026'):course['last_verified_at']=NOW;course['price_verified_at']=NOW
        courses=self.target/'sources/courses.json';atomic_write_json(courses,catalog)
        learning_workflow.preferences(self.target,{'budget':40,'currency':'USD','weekly_hours':4,'weeks_available':4,'candidate_level':'BEGINNER','project_hours':2})
        plan=journey.plan(self.target,'dream-role',catalog=courses,timestamp=NOW)
        self.assertEqual(plan['category'],'Dream Roles');self.assertTrue(plan['actions'])
        learning=read_json(self.target/'state/learning/latest.json')
        self.assertEqual({q for g in learning['gap_priorities'] for q in g['source_gap_ids']},{next(j['qualification_id'] for j in result['jobs'] if j['opportunity_id']=='dream-role')})
        self.assertTrue(learning['steps']);self.assertTrue(learning['experience_actions'])
        self.assertEqual(learning['path']['target_role_ids'],['Data Operations Lead'])
        self.assertTrue((self.target/'outputs'/plan['path']).is_file())
        learning_workflow.reassess(self.target,timestamp=NOW)
        journey.plan(self.target,'dream-role',catalog=courses,timestamp=NOW)
        report=(self.target/'outputs/learning/learning-roadmap.md').read_text()
        self.assertIn('Data Operations Lead:',report)
        self.assertNotIn('Software Implementation Specialist:',report)
        self.assertEqual(workspace.canonical_state_hash(self.target),before)
        self.assertEqual(result['external_actions'],0)

    def test_same_title_jobs_keep_distinct_validated_resumes_and_repeat_safely(self):
        request={**self.request,'prepare_top':0};journey.find_jobs(self.target,request,timestamp=NOW)
        ids=[read_json(self.source/'opportunity/strong.json')['opportunity_id'],'same-title-ready']
        batch=journey.prepare(self.target,selected_ids=ids,timestamp=NOW);self.assertEqual(batch['prepared'],2)
        self.assertEqual(len({r['path'] for r in batch['results']}),2)
        for r in batch['results']:self.assertEqual(sha256_file(self.target/'outputs'/r['path']),r['sha256'])
        again=journey.prepare(self.target,selected_ids=ids,timestamp=NOW)
        self.assertEqual([(r['build_id'],r['sha256']) for r in batch['results']],[(r['build_id'],r['sha256']) for r in again['results']])

    def test_mandatory_gaps_unknown_and_stale_sources_do_not_auto_prepare(self):
        payload=read_json(self.catalog);unknown=copy.deepcopy(payload[0]);unknown.update(opportunity_id='unknown',employer_name='Example Unreviewed Jobs',requirements=[])
        stale=copy.deepcopy(payload[0]);stale.update(opportunity_id='stale',employer_name='Example Earlier Jobs',source_type='USER_SUPPLIED',source_url='https://example.org/jobs/stale',source_status='OPEN',last_verified_at='2025-01-01T00:00:00Z')
        payload.extend([unknown,stale]);atomic_write_json(self.catalog,payload)
        result=journey.find_jobs(self.target,{**self.request,'prepare_top':0},timestamp=NOW)
        self.assertFalse(next(j for j in result['jobs'] if j['opportunity_id']=='unknown')['eligible_for_preparation'])
        self.assertFalse(next(j for j in result['jobs'] if j['opportunity_id']=='stale')['eligible_for_preparation'])
        batch=journey.prepare(self.target,selected_ids=['dream-role','unknown','stale'],timestamp=NOW)
        self.assertEqual(batch['prepared'],0)
        self.assertTrue(all(r['status']=='NEEDS_REVIEW' for r in batch['results']))

    def test_live_reader_handoff_preserves_required_review_and_recovers_from_offline(self):
        from careeros.discovery_sources import greenhouse_catalog
        payload={'jobs':[{'id':100,'internal_job_id':1,'title':'Implementation Coordinator','content':'<h2>Requirements</h2><p>Process Mapping and Training are required.</p>','absolute_url':'https://example.org/jobs/100','location':{'name':'Remote US'}}]}
        def fetch(**kwargs):return greenhouse_catalog(payload,board=kwargs['board'],employer=kwargs['employer'],query=kwargs['query'],timestamp=NOW)
        request={'boards':[{'board':'example','employer':'Example Company'}],'prepare_top':0}
        with self.assertRaises(PermissionError):journey.find_jobs(self.target,request,timestamp=NOW)
        found=journey.find_jobs(self.target,request,approved=True,fetcher=fetch,timestamp=NOW)
        self.assertEqual(found['status'],'REQUIREMENT_REVIEW_REQUIRED');self.assertEqual(found['source_proposals'][0]['jobs'],1)
        path=Path(found['source_proposals'][0]['path'])
        with self.assertRaises(PermissionError):journey.find_jobs(self.target,{'catalog':str(path)},timestamp=NOW)
        reviewed=read_json(path);reviewed['requirement_review_status']='REVIEWED';reviewed['opportunities'][0]['requirements']=[{'capability':'Process Mapping','requirement_class':'REQUIRED','requirement_subtype':'SKILL','level':'CORE'},{'capability':'Training','requirement_class':'REQUIRED','requirement_subtype':'SKILL','level':'CORE'}];atomic_write_json(path,reviewed)
        ready=journey.find_jobs(self.target,{'catalog':str(path),'prepare_top':0},timestamp=NOW)
        self.assertEqual(ready['categories']['Ready Now'],1)
        failed=journey.find_jobs(self.target,request,approved=True,fetcher=lambda **kwargs:(_ for _ in ()).throw(OSError('offline')),timestamp=NOW)
        self.assertTrue(failed['source_failures'])

    def test_location_word_order_does_not_hide_a_suitable_opening(self):
        payload=read_json(self.catalog)
        payload[0]['location']='Chicago, US Remote'
        atomic_write_json(self.catalog,payload)
        result=journey.find_jobs(self.target,{**self.request,'prepare_top':0},timestamp=NOW)
        self.assertTrue(any(j['opportunity_id']==payload[0]['opportunity_id'] for j in result['jobs']))

    def test_location_preferences_and_invalid_selection_are_not_ignored(self):
        result=journey.find_jobs(self.target,{**self.request,'locations':['London'],'prepare_top':0},timestamp=NOW)
        self.assertEqual(result['jobs'],[]);self.assertEqual(len(result['excluded']),5)
        with self.assertRaises(ValueError):journey.prepare(self.target,selected_ids=['not-a-job'],timestamp=NOW)
        bad=read_json(self.catalog)[0];bad.update(source_type='USER_SUPPLIED',source_url='javascript:alert(1)',last_verified_at=NOW)
        atomic_write_json(self.catalog,[bad])
        with self.assertRaises(ValueError):journey.find_jobs(self.target,{**self.request,'prepare_top':0},timestamp=NOW)

    def test_public_cli_executes_connected_workflows(self):
        request=self.target/'sources/search-request.json';atomic_write_json(request,{**self.request,'prepare_top':0})
        for command in (['workflow','jobs','--request',str(request)],['workflow','roles'],['workflow','opportunities'],['workflow','prepare','--top','1'],['workflow','plan','--opportunity-id','dream-role']):
            with self.subTest(command=command),redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(['--workspace',str(self.target),'--timestamp',NOW,*command]),0)
                self.assertIsInstance(json.loads(output.getvalue()),dict)

    def test_experienced_profile_has_real_role_ideas_without_new_claims(self):
        target=Path(self.temp.name)/'experienced';source=create(target,'experienced-multi-role');jobs(target,source)
        before=workspace.canonical_state_hash(target)
        journey.find_jobs(target,{'catalog':str(target/'sources/jobs.json'),'prepare_top':0},timestamp=NOW)
        roles=journey.suggest_roles(target,timestamp=NOW)
        self.assertTrue(roles['lanes']);self.assertEqual(workspace.canonical_state_hash(target),before)

if __name__=='__main__':unittest.main()
