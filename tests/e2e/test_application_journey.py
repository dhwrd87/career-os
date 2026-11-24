"""Real document/package journeys, factual boundaries and recoverable preparation."""
import copy,json,re,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote
from docx import Document
from careeros import application,application_answers,experience,journey,lane_base,onboarding,opportunity,profile,resume,workspace,workflows
from careeros.core.io import read_json,sha256_file,atomic_write_json
from careeros.application_documents import verify_packet,validate_application_details
from careeros.discovery_sources import fetch_greenhouse_job

FIXTURE=Path(__file__).resolve().parents[2]/'fixtures/synthetic'
NOW='2026-11-24T12:00:00Z'


def fresh(target,persona='career-changer',multiple=False):
    f=FIXTURE/persona;workspace.init_workspace(target,fixture_mode=True,timestamp=NOW);onboarding.start(target,timestamp=NOW)
    payload=read_json(f/'onboarding/input.json')
    if multiple:
        other=copy.deepcopy(payload['role_intents'][0]);other.update(local_id='second-intent',display_name='Training Coordination',target_titles=['Training Coordinator'],core_capabilities=['Training','Documentation'])
        payload['role_intents'].append(other)
    source=target/'sources/intake.json';atomic_write_json(source,payload);result=onboarding.ingest(target,source,timestamp=NOW)
    if result['state']=='NEEDS_CLARIFICATION':onboarding.resolve(target,f/'onboarding/resolutions.json',timestamp=NOW)
    output=workflows.setup_approve(target,actor='synthetic-human',approved=True,timestamp=NOW)
    return f,output


def job(target,f,*,key=None,letter='REQUIRED',questions=True):
    payload=read_json(f/'opportunity/strong.json')
    if key:payload['opportunity_id']=key
    payload.update(source_url='https://example.org/jobs/123',application_url='https://example.org/apply/123',application_url_source={'url':'https://example.org/jobs/123','captured_at':NOW,'verified':True,'method':'SYNTHETIC_TEST_FORM'},cover_letter_requirement=letter)
    if questions:payload.update(application_questions=[{'id':'work','text':'Describe relevant work experience.','required':True,'field_type':'textarea'},{'id':'salary','text':'What salary do you expect?','required':True,'field_type':'text'},{'id':'auth','text':'Are you authorized to work in this country?','required':True,'field_type':'boolean'}],application_question_source={'url':'https://example.org/apply/123','captured_at':NOW})
    path=target/'sources/job.json';atomic_write_json(path,payload);opportunity.ingest(target,path,timestamp=NOW);opportunity.qualify(target,payload['opportunity_id'],timestamp=NOW);return payload


class ApplicationJourneyTests(unittest.TestCase):
    def test_fresh_master_multiple_bases_batch_and_tracking(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'workspace';f,setup=fresh(target,multiple=True)
            self.assertTrue((target/setup['outputs']['master_recruiter_resume']).is_file())
            self.assertTrue((target/'outputs'/setup['outputs']['strategic_job_search_plan']).is_file())
            before=workspace.canonical_state_hash(target)
            directions=journey.career_directions(target,[0,1],approved=True,actor='synthetic-human',timestamp=NOW)
            self.assertEqual(len(directions['bases']),2)
            self.assertTrue(all(v['validation']=='PASS' for v in directions['bases']),directions)
            contents=[read_json(target/'state/lane-bases'/v['lane_base_id']/'content.json') for v in directions['bases']]
            self.assertNotEqual(contents[0]['target_role'],contents[1]['target_role'])
            self.assertNotEqual(contents[0]['summary'],contents[1]['summary'])
            for base in directions['bases']:
                profile.activate_role_family(target,base['role_family_id'],timestamp=NOW)
                lane_base.accept_lane_base(target,base['lane_base_id'],actor='synthetic-human',timestamp=NOW)
            first=job(target,f,key='journey-first');second=job(target,f,key='journey-second',letter='NOT_ACCEPTED');second['role_title']='Training Coordinator'
            atomic_write_json(target/'sources/job.json',second);opportunity.ingest(target,target/'sources/job.json',timestamp=NOW)
            result=journey.prepare(target,top=5,timestamp=NOW)
            self.assertEqual(result['packages_prepared'],2,result)
            for row in result['results']:
                self.assertTrue((target/'outputs'/row['start_here']).is_file())
                build_record=read_json(target/'state/resume-builds'/row['build_id']/'build.json')
                self.assertIn(build_record['lane_base_id'],[v['lane_base_id'] for v in directions['bases']])
                self.assertEqual(len(row['unanswered_questions']),2)
                manifest=read_json(target/'outputs'/row['document_manifest']);folder=(target/'outputs'/row['start_here']).parent
                names={v['filename'] for v in manifest['documents']}
                self.assertTrue({'Resume.pdf','Resume.docx','Job Description.md','Qualification.json','Employer Needs.json','Application Answers.md','Validation.json'}<=names)
                for link in re.findall(r'href="([^"]+)"',(folder/'Start Here.html').read_text()):
                    if not link.startswith('https:'):self.assertTrue((folder/unquote(link)).is_file(),link)
                self.assertIn('REVIEW_REQUIRED',manifest['review_state'])
                self.assertTrue(Document(folder/'Resume.docx').paragraphs)
            letter_file=(target/'outputs'/result['results'][0]['start_here']).parent/'Cover Letter.docx'
            self.assertTrue(letter_file.is_file())
            letter_text=' '.join(p.text for p in Document(letter_file).paragraphs)
            self.assertNotIn(' I I ',letter_text)
            self.assertNotRegex(letter_text,r'\. (?:Mapped|Created|Reviewed|Supported) ')
            self.assertFalse((target/'outputs'/result['results'][1]['start_here']).parent.joinpath('Cover Letter.docx').exists())
            repeated=journey.prepare(target,top=5,timestamp=NOW);self.assertEqual([v['packet_id'] for v in result['results']],[v['packet_id'] for v in repeated['results']])
            self.assertEqual(len(experience.records(target/'state/applications')),2)
            pack=experience.interview(target,result['results'][0]['opportunity_id'],timestamp=NOW);self.assertTrue(all(pack['qa'].values()))
            self.assertEqual(before,workspace.canonical_state_hash(target))

    def test_answer_bank_explicit_scope_and_missing_declarations(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'workspace';f,_=fresh(target);profile.build_role_family(target,approve=True,timestamp=NOW);opp=job(target,f)
            build,content,artifact=resume.build(target,opp['opportunity_id'],timestamp=NOW);self.assertEqual(resume.validate(target,build['build_id'])[0]['status'],'PASS')
            payload={'entries':[{'question':'What salary do you expect?','answer':'USD 70,000 per year','employer_name':opp['employer_name'],'role_title':opp['role_title'],'location':opp['location']}]}
            with self.assertRaises(PermissionError):application_answers.save_bank(target,payload)
            application_answers.save_bank(target,payload,approved=True,actor='synthetic-human',timestamp=NOW)
            packet=application.prepare(target,opp['opportunity_id'],build['build_id'],timestamp=NOW)
            rows={v['id']:v for v in packet['application_answers']['questions']};self.assertIn('70,000',rows['salary']['answer']);self.assertIsNone(rows['auth']['answer']);self.assertTrue(rows['work']['source_record_ids']);self.assertEqual(rows['anticipated-background']['kind'],'ANTICIPATED_PREPARATION');self.assertTrue(rows['anticipated-background']['answer'])
            roots=experience.context(target);other={**opp,'employer_name':'Another employer'};drafts=application_answers.prepare_answers(roots,other,read_json(target/'state/profile/career-profile.json'),content,timestamp=NOW)
            self.assertIsNone(next(v for v in drafts['questions'] if v['id']=='salary')['answer'])
            old_folder=(target/'outputs'/packet['start_here']).parent
            old_hashes={p.name:sha256_file(p) for p in old_folder.iterdir() if p.is_file()}
            application_answers.save_bank(target,{'entries':[{'question':'Are you authorized to work in this country?','answer':'Yes','employer_name':opp['employer_name'],'role_title':opp['role_title'],'location':opp['location']}]},approved=True,actor='synthetic-human',timestamp=NOW)
            revision=application.prepare(target,opp['opportunity_id'],build['build_id'],timestamp=NOW)
            self.assertEqual(revision['application_id'],packet['application_id']);self.assertNotEqual(revision['packet_id'],packet['packet_id'])
            self.assertEqual(len(experience.records(target/'state/applications')),1)
            self.assertEqual(old_hashes,{p.name:sha256_file(p) for p in old_folder.iterdir() if p.is_file()})
            experience.record_event(target,revision['application_id'],{'event_type':'SUBMITTED','actor':'synthetic-human','occurred_at':NOW,'human_confirmed':True},timestamp=NOW)
            self.assertEqual(application.prepare(target,opp['opportunity_id'],build['build_id'],timestamp=NOW)['packet_id'],revision['packet_id'])
            application_answers.save_bank(target,payload,approved=True,actor='synthetic-human',timestamp='2026-11-24T12:01:00Z')
            with self.assertRaises(PermissionError):application.prepare(target,opp['opportunity_id'],build['build_id'],timestamp=NOW)
            self.assertEqual(journey.prepare(target,top=5,timestamp=NOW)['packages_prepared'],0)
            packet=revision
            folder=(target/'outputs'/packet['start_here']).parent;original=(folder/'Resume.docx').read_bytes();(folder/'Resume.docx').write_bytes(original+b'changed')
            with self.assertRaises(PermissionError):application.prepare(target,opp['opportunity_id'],build['build_id'],timestamp=NOW)

    def test_missing_link_is_visible_and_export_failure_is_retryable(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'workspace';f,_=fresh(target);profile.build_role_family(target,approve=True,timestamp=NOW)
            opp=read_json(f/'opportunity/strong.json');atomic_write_json(target/'sources/job.json',opp);opportunity.ingest(target,target/'sources/job.json',timestamp=NOW);opportunity.qualify(target,opp['opportunity_id'],timestamp=NOW)
            build,_,_=resume.build(target,opp['opportunity_id'],timestamp=NOW);resume.validate(target,build['build_id'])
            with patch('careeros.experience.export_resume',side_effect=OSError('Export unavailable')):
                with self.assertRaises(OSError):application.prepare(target,opp['opportunity_id'],build['build_id'],timestamp=NOW)
            self.assertFalse(list((target/'state/applications').glob('*.json')))
            packet=application.prepare(target,opp['opportunity_id'],build['build_id'],timestamp=NOW);text=(target/'outputs'/packet['start_here']).read_text()
            self.assertIn('Direct application link not verified',text);self.assertIn('actual screening questions still need checking',text);self.assertEqual(packet['completion_state'],'DRAFT_NEEDS_ANSWERS')
            with self.assertRaises(ValueError):validate_application_details({**opp,'application_url':'javascript:alert(1)'})

    def test_city_area_preference_and_unknown_arrangement_remain_distinct(self):
        notes,mismatch=journey._preference_check({'location':'Sacramento, CA (Hybrid)'},{'locations':['Sacramento area'],'work_modes':['HYBRID','ONSITE']})
        self.assertFalse(mismatch);self.assertFalse(notes)
        notes,mismatch=journey._preference_check({'location':'Sacramento, CA'},{'locations':['Sacramento area'],'work_modes':['HYBRID','ONSITE']})
        self.assertFalse(mismatch);self.assertTrue(notes)

    def test_provider_questions_are_actual_and_listing_is_not_invented_form(self):
        payload={'compliance':None,'location_questions':None,'id':123,'internal_job_id':1,'title':'Coordinator','content':'<p>Required: coordination.</p>','absolute_url':'https://job-boards.greenhouse.io/test/jobs/123','questions':[{'label':'Work authorization','required':True,'fields':[{'name':'authorization','type':'multi_value_single_select','values':[{'label':'Yes','value':1},{'label':'No','value':0}]}]}]}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def geturl(self):return 'https://boards-api.greenhouse.io/v1/boards/test/jobs/123?questions=true'
            def read(self,n):return json.dumps(payload).encode()
        class Opener:
            def open(self,*args,**kwargs):return Response()
        result=fetch_greenhouse_job(board='test',job_id='123',employer='Example',approved=True,timestamp=NOW,opener=Opener());row=result['opportunities'][0]
        self.assertEqual(row['application_url'],payload['absolute_url']);self.assertEqual(row['application_questions'][0]['text'],'Work authorization');self.assertEqual(result['requirement_review_status'],'PENDING')
        payload['absolute_url']='https://example.org/careers';row=fetch_greenhouse_job(board='test',job_id='123',employer='Example',approved=True,timestamp=NOW,opener=Opener())['opportunities'][0];self.assertNotIn('application_url',row)
        payload['questions']=None;row=fetch_greenhouse_job(board='test',job_id='123',employer='Example',approved=True,timestamp=NOW,opener=Opener())['opportunities'][0];self.assertFalse(row['application_question_source']['complete'])
