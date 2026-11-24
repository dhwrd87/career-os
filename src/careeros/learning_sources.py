"""Live learning-source reader behind the existing ProviderAdapter boundary.

Supports public sitemaps and HTML Course/learning-resource metadata. It never
logs into providers, purchases training or transmits candidate profile data.
"""
from __future__ import annotations
import hashlib
import html
import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from careeros.core.io import atomic_write_json,sha256_value
from careeros.workspace import utc_now
from careeros.discovery_sources import _NoRedirect

MAX_BYTES=8*1024*1024


def public_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):raise ValueError('Learning sources require public HTTPS URLs')
    if p.hostname.endswith(('.local','.internal','.invalid')) or p.hostname=='localhost':raise ValueError('Private learning-source host is forbidden')
    for row in socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(row[4][0]).is_global:raise ValueError('Private learning-source address is forbidden')
    return url


def fetch_public(url):
    public_url(url)
    req=urllib.request.Request(url,headers={'User-Agent':'CareerOS-Learning/0.4.1 (read-only)','Accept':'text/html,application/xml,text/xml,application/json'},method='GET')
    with urllib.request.build_opener(_NoRedirect()).open(req,timeout=20) as response:
        data=response.read(MAX_BYTES+1)
        if response.geturl()!=url:raise ValueError('Learning-source redirect is not permitted')
    if len(data)>MAX_BYTES:raise ValueError('Learning source exceeds byte budget')
    return data

class CoursePage(HTMLParser):
    def __init__(self):
        super().__init__();self.jsonld=[];self.links=[];self.title=[];self.description='';self.heading=[];self._ld=False;self._title=False;self._heading=False;self.buffer=[];self.text=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='script' and a.get('type')=='application/ld+json':self._ld=True;self.buffer=[]
        if tag in {'script','style'}:self.hidden+=1
        if tag in {'h1','title'}:self._title=True
        if tag in {'h2','h3','h4'}:self._heading=True
        if tag=='a' and a.get('href'):self.links.append(a['href'])
        if tag=='meta' and a.get('name')=='description':self.description=a.get('content','')
    def handle_data(self,value):
        if self._ld:self.buffer.append(value)
        if self._title:self.title.append(value)
        if self._heading:self.heading.append(value)
        if not self.hidden:self.text.append(value)
    def handle_endtag(self,tag):
        if tag=='script' and self._ld:
            try:self.jsonld.append(json.loads(''.join(self.buffer)))
            except json.JSONDecodeError:pass
            self._ld=False
        if tag in {'script','style'}:self.hidden=max(0,self.hidden-1)
        if tag in {'h1','title'}:self._title=False
        if tag in {'h2','h3','h4'}:self._heading=False


def _items(value):
    if isinstance(value,list):
        for child in value:yield from _items(child)
    elif isinstance(value,dict):
        yield value
        for key in ('@graph','itemListElement','item'):yield from _items(value.get(key))


def normalize_page(url,body,*,timestamp=None):
    parser=CoursePage();parser.feed(body.decode('utf-8',errors='replace'));now=utc_now(timestamp)
    course=next((v for value in parser.jsonld for v in _items(value) if v.get('@type') in ('Course','LearningResource')),None)
    record=course or {};title=record.get('name') or next((v.strip() for v in parser.title if v.strip()),'')
    if not title:raise ValueError('Learning page has no identifiable title')
    provider=record.get('provider') or {};provider=provider.get('name') if isinstance(provider,dict) else str(provider)
    provider=provider or urllib.parse.urlsplit(url).hostname
    topics=record.get('teaches') or record.get('keywords') or []
    if isinstance(topics,str):topics=[p.strip() for p in topics.split(',') if p.strip()]
    topics=[str(v.get('name') or '') if isinstance(v,dict) else str(v) for v in topics]
    description=html.unescape(str(record.get('description') or parser.description))
    offer=record.get('offers') or {};offer=offer[0] if isinstance(offer,list) and offer else offer
    cost='UNKNOWN';amount=None;currency=None
    if record.get('isAccessibleForFree') is True:cost='FREE';amount=0
    if isinstance(offer,dict) and str(offer.get('price','')).replace('.','',1).isdigit():
        amount=float(offer['price']);currency=offer.get('priceCurrency');cost='FREE' if amount==0 else 'ONE_TIME'
    return {'provider':provider,'course_id':sha256_value(url)[:20],'title':html.unescape(title),'url':url,'course_type':'COURSE' if record.get('@type')=='Course' else 'KNOWLEDGE_RESOURCE','skill_topics':topics,'curriculum_topics':[description,*[h.strip() for h in parser.heading if h.strip()]],'credential_type':'NO_CREDENTIAL','certificate_available':False,'cost_state':cost,'cost_amount':amount,'cost_currency':currency,'price_verified_at':now if cost!='UNKNOWN' else None,'estimated_duration':str(record.get('timeRequired') or 'UNKNOWN'),'level':'UNKNOWN','last_verified_at':now,'availability':'AVAILABLE','source_refs':[{'url':url,'sha256':hashlib.sha256(body).hexdigest(),'captured_at':now,'locator':'Course JSON-LD / visible page metadata'}],'affiliate_relationship':False,'discovery_boundary':'Availability observed now; teaching content may be historical. No credential, duration, prerequisite or price is inferred when absent.'}


def discover(workspace:Path,*,sources:list[str],query:str,approved:bool,limit=3,timestamp=None,fetcher=None):
    from careeros.learning_workflow import roots_for,_save
    if approved is not True:raise PermissionError('Read-only learning discovery requires consent')
    if not 1<=limit<=5 or not 1<=len(sources)<=3:raise ValueError('Use 1–3 indexes and 1–5 result pages')
    if re.search(r'@|\b(?:email|phone|candidate_profile_id)\b',query,re.I):raise PermissionError('Discovery query must contain generic capability language only')
    get=fetcher or fetch_public;terms={t for t in re.findall(r'[a-z0-9]+',query.casefold()) if len(t)>2};urls=[];attempts=0;failures=[];courses=[];cached={}
    for source in sources:
        try:
            attempts+=1;body=get(source)
            if len(body)>MAX_BYTES:raise ValueError('Index exceeds byte budget')
            if body.lstrip().startswith(b'<?xml') or b'<urlset' in body[:500] or b'<sitemapindex' in body[:500]:
                root=ET.fromstring(body);links=[e.text for e in root.iter() if e.tag.endswith('loc') and e.text]
            else:
                p=CoursePage();p.feed(body.decode('utf-8',errors='replace'));links=[urllib.parse.urljoin(source,u) for u in p.links]
                # A supplied course page is also a live discovery source.
                if any(v.get('@type') in ('Course','LearningResource') for x in p.jsonld for v in _items(x)) or (p.title and p.description and not source.endswith(('sitemap.xml','index.html','/'))):
                    links.insert(0,source);cached[source]=body
            for url in links:
                if '/courses/' in url and url.endswith('/sitemap.xml'):
                    url=url[:-len('sitemap.xml')]
                parsed=urllib.parse.urlsplit(url)
                if parsed.scheme!='https' or parsed.hostname!=urllib.parse.urlsplit(source).hostname:continue
                words=set(re.findall(r'[a-z0-9]+',urllib.parse.unquote(url).casefold()))
                if url!=source and terms and not terms&words:continue
                if parsed.hostname=='ocw.mit.edu' and not re.fullmatch(r'/courses/[^/]+/?',parsed.path):continue
                if url not in urls:urls.append(url)
        except Exception as exc:failures.append({'source':source,'error':type(exc).__name__,'message':str(exc)})
    for url in urls[:limit]:
        try:
            if url in cached:body=cached[url]
            else:attempts+=1;body=get(url)
            if len(body)>MAX_BYTES:raise ValueError('Course page exceeds byte budget')
            courses.append(normalize_page(url,body,timestamp=timestamp))
        except Exception as exc:failures.append({'source':url,'error':type(exc).__name__,'message':str(exc)})
    roots=roots_for(workspace);payload={'schema':'careeros.learning-discovery.v1','query':query,'sources':sources,'captured_at':utc_now(timestamp),'courses':courses,'failures':failures,'network_requests':attempts,'status':'PASS' if courses else 'NO_VERIFIED_RESOURCES','affiliate_influence':0,'candidate_data_transmitted':False}
    path=_save(roots,'discovered-catalog.json',payload)
    return {**payload,'catalog_path':str(path),'boundary':'Fresh retrieval is not proof of current curriculum, price, competence, certification or professional experience.'}
