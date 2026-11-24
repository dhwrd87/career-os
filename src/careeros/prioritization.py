"""Observable fit ranking and optional explicitly assumed application value."""
from __future__ import annotations
from typing import Any


def rank_opportunities(opportunities: list[dict], qualifications: list[dict], *, assumptions: dict | None = None) -> dict[str, Any]:
    assumptions = assumptions or {}
    index = {q['opportunity_id']: q for q in qualifications}
    rows = []
    for opp in opportunities:
        q = index.get(opp['opportunity_id'], {})
        evidence = q.get('evidence', [])
        supported = sum(e.get('match') in {'SUPPORTED_MATCH','STRONG_SUPPORTED_MATCH','TRANSFERABLE_MATCH'} for e in evidence)
        fit = round(100 * supported / len(evidence), 1) if evidence else 0
        candidate_assumptions = assumptions.get(opp['opportunity_id'])
        expected_value = None
        if candidate_assumptions is not None:
            required = ('interview_probability','offer_given_interview','career_value_points','effort_hours','time_cost_points_per_hour')
            if set(candidate_assumptions) != set(required):
                raise ValueError('Expected-value assumptions require exactly: ' + ', '.join(required))
            if any(isinstance(v, bool) or not isinstance(v, (int,float)) or v < 0 for v in candidate_assumptions.values()):
                raise ValueError('Assumptions must be nonnegative numbers')
            if any(candidate_assumptions[k] > 1 for k in required[:2]):
                raise ValueError('Assumed probabilities must be between zero and one')
            a = candidate_assumptions
            expected_value = round(a['interview_probability'] * a['offer_given_interview'] * a['career_value_points'] - a['effort_hours'] * a['time_cost_points_per_hour'], 2)
        eligible = q.get('decision') == 'QUALIFIED' and not q.get('hard_disqualifiers')
        rows.append({'opportunity_id':opp['opportunity_id'],'role_title':opp['role_title'],'employer_name':opp['employer_name'],'qualification':q.get('decision','NOT_EVALUATED'),'supported_fit_percent':fit,'eligible_for_preparation':eligible,'assumed_expected_value':expected_value,'assumptions':candidate_assumptions,'value_status':'USER_ASSUMPTIONS' if candidate_assumptions is not None else 'UNESTIMATED'})
    rows.sort(key=lambda r:(not r['eligible_for_preparation'], -(r['assumed_expected_value'] if r['assumed_expected_value'] is not None else -100000), -r['supported_fit_percent'], r['opportunity_id']))
    return {'schema':'careeros.opportunity-priorities.v1','rankings':rows,'boundary':'Fit is observed evidence coverage. Expected value is a user-assumed scenario, not a predicted hiring outcome. Freshness and artifact QA remain separate mandatory gates.','canonical_mutations':0}
