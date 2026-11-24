import unittest
from careeros.prioritization import rank_opportunities

class PrioritizationTests(unittest.TestCase):
    def test_observed_fit_and_assumptions_remain_distinct(self):
        opportunities=[{'opportunity_id':'a','role_title':'Coordinator','employer_name':'Example Co'},{'opportunity_id':'b','role_title':'Director','employer_name':'Example Co'}]
        quals=[{'opportunity_id':'a','decision':'QUALIFIED','evidence':[{'match':'SUPPORTED_MATCH'}]},{'opportunity_id':'b','decision':'NOT_QUALIFIED','hard_disqualifiers':['Experience'],'evidence':[]}]
        result=rank_opportunities(opportunities,quals)
        self.assertEqual(result['rankings'][0]['opportunity_id'],'a')
        self.assertIsNone(result['rankings'][0]['assumed_expected_value'])
        assumptions={'b':{'interview_probability':1,'offer_given_interview':1,'career_value_points':1000,'effort_hours':1,'time_cost_points_per_hour':1}}
        result=rank_opportunities(opportunities,quals,assumptions=assumptions)
        self.assertEqual(result['rankings'][0]['opportunity_id'],'a')
        self.assertEqual(result['rankings'][1]['assumed_expected_value'],999)
        with self.assertRaises(ValueError):
            rank_opportunities(opportunities,quals,assumptions={'a':{**assumptions['b'],'interview_probability':2}})
