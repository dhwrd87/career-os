"""Bounded read-only public job-board discovery. No credentials or submissions."""
from __future__ import annotations
import html
import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.request import Request, build_opener, HTTPRedirectHandler
from careeros.workspace import utc_now

MAX_BYTES = 8 * 1024 * 1024

class _Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.blocked=0
    def handle_starttag(self, tag, attrs):
        if tag in {'script','style'}: self.blocked+=1
        if tag in {'p','li','br','h1','h2','h3','h4','div'}: self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in {'script','style'}: self.blocked=max(0,self.blocked-1)
        if tag in {'p','li','h1','h2','h3','h4','div'}: self.parts.append('\n')
    def handle_data(self, data):
        if not self.blocked:self.parts.append(data)

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Discovery redirects are not permitted')


def greenhouse_catalog(payload: dict[str, Any], *, board: str, employer: str, limit=25, query: str | None = None, timestamp=None) -> dict:
    if not 1 <= limit <= 100:raise ValueError('Discovery limit must be between 1 and 100')
    if not isinstance(payload.get('jobs'), list):raise ValueError('Provider response has no job list')
    now=utc_now(timestamp);jobs=[]
    for row in payload['jobs']:
        queries=[query] if isinstance(query,str) else (query or [])
        if queries and not any(term.casefold() in str(row.get('title','')).casefold() for term in queries):continue
        if row.get('internal_job_id') is None:continue # Prospect posts are not a specific job.
        parser=_Text();parser.feed(html.unescape(html.unescape(str(row.get('content') or ''))))
        text='\n'.join(re.sub(r'\s+',' ',line).strip() for line in ''.join(parser.parts).splitlines() if line.strip())
        if not row.get('id') or not row.get('title') or not text:continue
        jobs.append({'opportunity_id':f'greenhouse-{board}-{row["id"]}','source_type':'USER_SUPPLIED','employer_name':employer,'role_title':row['title'],'location':(row.get('location') or {}).get('name'),'source_url':row.get('absolute_url'),'canonical_url':row.get('absolute_url'),'provider_job_id':str(row['id']),'last_verified_at':now,'source_status':'OPEN','job_description':text,'requirements':[]})
        if len(jobs)>=limit:break
    return {'schema':'careeros.discovery-source-proposal.v1','provider':'GREENHOUSE','board':board,'fetched_at':now,'source_endpoint':f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true','provider_posts':len(payload['jobs']),'selected_posts':len(jobs),'requirement_review_status':'PENDING','opportunities':jobs,'boundary':'Read job_description, extract source-grounded required/preferred requirements, then set requirement_review_status to REVIEWED before ingestion. An empty requirement list must not be qualified.','external_writes':0}


def fetch_greenhouse(*, board: str, employer: str, approved: bool, limit=25, query=None, timestamp=None, opener=None) -> dict:
    if approved is not True:raise PermissionError('Explicit read-only network consent is required')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',board):raise ValueError('Invalid board token')
    if not employer.strip():raise ValueError('Supply the verified employer name')
    if not 1 <= limit <= 100:raise ValueError('Discovery limit must be between 1 and 100')
    url=f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true'
    request=Request(url,headers={'Accept':'application/json','User-Agent':'CareerOS/0.4 public-read-only'},method='GET')
    client=opener or build_opener(_NoRedirect())
    with client.open(request,timeout=20) as response:
        if response.geturl()!=url:raise ValueError('Unexpected provider response URL')
        body=response.read(MAX_BYTES+1)
    if len(body)>MAX_BYTES:raise ValueError('Provider response exceeds discovery budget')
    result=greenhouse_catalog(json.loads(body),board=board,employer=employer,limit=limit,query=query,timestamp=timestamp)
    result['network_requests']=1
    return result


def fetch_greenhouse_job(*,board:str,job_id:str,employer:str,approved:bool,timestamp=None,opener=None):
    """Read a specific public job and its actual application-question schema."""
    if approved is not True:raise PermissionError('Read-only public-source permission is required.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',board) or not re.fullmatch(r'[0-9]{1,20}',str(job_id)):raise ValueError('Invalid employer board or job ID.')
    if not employer.strip():raise ValueError('Supply the verified employer name.')
    url=f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}?questions=true'
    client=opener or build_opener(_NoRedirect())
    with client.open(Request(url,headers={'Accept':'application/json','User-Agent':'CareerOS/0.4 public-read-only'},method='GET'),timeout=20) as response:
        if response.geturl()!=url:raise ValueError('Unexpected provider response URL.')
        body=response.read(MAX_BYTES+1)
    if len(body)>MAX_BYTES:raise ValueError('Provider response exceeds discovery budget.')
    row=json.loads(body)
    if str(row.get('id'))!=str(job_id):raise ValueError('The provider returned a different job.')
    proposal=greenhouse_catalog({'jobs':[row]},board=board,employer=employer,limit=1,timestamp=timestamp)
    if not proposal['opportunities']:raise ValueError('This is not a complete, currently available job posting.')
    now=utc_now(timestamp);questions=[]
    groups=[*(row.get('questions') or []),*(row.get('location_questions') or []),*(row.get('compliance') or [])]
    demographic=row.get('demographic_questions') or {}
    if isinstance(demographic,dict):groups+=demographic.get('questions') or []
    for index,q in enumerate(groups):
        fields=q.get('fields') or [{}]
        # Greenhouse may offer a file OR text input for one resume question.
        # Preserve the alternatives rather than inventing two required questions.
        field=next((v for v in fields if 'file' in str(v.get('type',''))),fields[0])
        question={'id':str(field.get('name') or q.get('id') or f'question-{index}')+f'-{index}','text':str(q.get('label') or q.get('text') or field.get('name') or 'Application question'),'required':q.get('required') is True,'field_type':str(field.get('type') or 'text'),'field_name':field.get('name'),'options':field.get('values') or q.get('answer_options') or [],'alternative_fields':fields}
        questions.append(question)
    job=proposal['opportunities'][0];job['application_questions']=questions
    job['application_question_source']={'url':url,'captured_at':now,'method':'PUBLIC_PROVIDER_QUESTION_SCHEMA','complete':isinstance(row.get('questions'),list)}
    from urllib.parse import urlsplit
    source=urlsplit(str(job.get('source_url') or ''))
    if source.hostname in {'job-boards.greenhouse.io','boards.greenhouse.io','job-boards.eu.greenhouse.io'} and source.path.rstrip('/').endswith('/jobs/'+str(job_id)):
        job['application_url']=job['source_url']
        job['application_url_source']={'url':url,'captured_at':now,'method':'PROVIDER_HOSTED_FORM','verified':True}
    proposal.update(source_endpoint=url,network_requests=1)
    return proposal
