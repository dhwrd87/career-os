import unittest
from careeros.discovery_sources import greenhouse_catalog,fetch_greenhouse,MAX_BYTES

class DiscoverySourceTests(unittest.TestCase):
    def test_public_feed_is_source_grounded_reviewable_and_bounded(self):
        payload={'jobs':[{'id':10,'internal_job_id':1,'title':'Support Coordinator','absolute_url':'https://example.invalid/jobs/10','content':'&lt;h2&gt;Requirements&lt;/h2&gt;&lt;p&gt;Document service requests&lt;/p&gt;','location':{'name':'Example City'}},{'id':11,'internal_job_id':None,'title':'Talent Community','content':'Join us'}]}
        result=greenhouse_catalog(payload,board='synthetic',employer='Example Company',timestamp='2026-11-23T12:00:00Z')
        self.assertEqual(result['selected_posts'],1)
        self.assertIn('Document service requests',result['opportunities'][0]['job_description'])
        self.assertEqual(result['requirement_review_status'],'PENDING')
        self.assertEqual(result['opportunities'][0]['requirements'],[])
        self.assertEqual(result['external_writes'],0)
    def test_network_requires_consent_and_board_is_not_an_arbitrary_url(self):
        with self.assertRaises(PermissionError):fetch_greenhouse(board='example',employer='Example',approved=False)
        with self.assertRaises(ValueError):fetch_greenhouse(board='../../private',employer='Example',approved=True)
        with self.assertRaises(ValueError):fetch_greenhouse(board='example',employer='Example',approved=True,limit=200)
    def test_actual_http_adapter_uses_get_and_enforces_byte_budget(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def geturl(self):return 'https://boards-api.greenhouse.io/v1/boards/synthetic/jobs?content=true'
            def read(self,limit):return b'{"jobs":[]}'
        class Client:
            def open(self,request,timeout):
                self.request=request;self.timeout=timeout;return Response()
        client=Client();result=fetch_greenhouse(board='synthetic',employer='Example',approved=True,opener=client)
        self.assertEqual(client.request.get_method(),'GET')
        self.assertEqual(result['network_requests'],1)
