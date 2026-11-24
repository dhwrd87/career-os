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
        if query and query.casefold() not in str(row.get('title','')).casefold():continue
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
