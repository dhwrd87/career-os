"""Plain-language labels at the display boundary; stored contracts stay exact."""
from __future__ import annotations

LABELS = {
    'QUALIFIED': 'Your background fits', 'BORDERLINE': 'Some points need work or review',
    'NOT_QUALIFIED': 'Required qualifications are missing', 'NOT_EVALUATED': 'Not yet reviewed',
    'NOT_PREPARED': 'No application draft yet', 'REVIEW_REQUIRED': 'Ready for your review',
    'READY_FOR_REVIEW': 'Ready for your review', 'PROPOSED_FOR_REVIEW': 'Ready for your review',
    'STALE_REBUILD_REQUIRED': 'Time to update this plan', 'CURRENT': 'Up to date',
    'HARD_GAP': 'A required qualification is missing', 'BRIDGEABLE_GAP': 'A gap you could work on',
    'UNKNOWN_DECISION': 'A detail needs checking', 'UNKNOWN_EVIDENCE': 'An example of your work is needed',
    'UNKNOWN': 'Not yet known', 'PARTIALLY_SUPPORTED': 'You have part of what is needed',
    'PREFERRED_AND_MISSING': 'An employer preference you do not yet meet',
    'PRACTICAL_SKILL': 'Practical skill', 'EVIDENCE': 'Examples of your work',
    'CREDENTIAL': 'Credential', 'EXPERIENCE': 'Professional experience',
    'KNOWLEDGE': 'Knowledge', 'KNOWLEDGE_RESOURCE':'Reading or another learning resource',
    'INDUSTRY_CERTIFICATION_PREP':'Exam preparation', 'LAB_PLATFORM':'Hands-on practice',
    'PROFESSIONAL_CERTIFICATE':'Certificate program', 'DEGREE_COURSEWORK':'College coursework', 'CERTIFICATION_PREP': 'Exam preparation',
    'CERTIFICATION_ATTEMPT': 'Certification exam', 'NOT_STARTED': 'Not started',
    'IN_PROGRESS': 'In progress', 'COMPLETED': 'Completed', 'VERIFIED': 'Checked with supporting work',
    'INSUFFICIENT': 'Too few applications to see a useful pattern',
    'DEVELOPING': 'An early pattern; more results will help', 'MATURE': 'Enough results for a useful comparison',
    'HIGHLY_REDUNDANT': 'Covers much of what you already know', 'PARTIALLY_REDUNDANT': 'Some familiar material',
    'MOSTLY_NEW': 'Mostly new to you', 'NOVEL_HIGH_VALUE': 'New material that may help',
    'PREREQUISITE_MISSING': 'Some starting skills are missing', 'TOO_ADVANCED': 'Too advanced for now',
    'APPROPRIATE': 'A suitable starting level', 'STRETCH': 'A step up from your current level',
    'NO_OBSERVED_GAP_COVERAGE': 'Does not address this job requirement',
    'BUDGET_EXCEEDED': 'Above your budget', 'TIME_BUDGET_UNVERIFIED_OR_EXCEEDED': 'Too long, or the time needed is not confirmed',
    'COST_UNVERIFIED_FOR_BUDGET': 'The price needs checking', 'LEVEL_UNVERIFIED': 'The starting level needs checking',
    'CATALOG_REVERIFY': 'The course details need checking again', 'CATALOG_UNKNOWN': 'Current course details are missing',
    'SUBSCRIPTION_OWNED': 'Covered by a subscription you already have',
    'SELF_PACED_MATCH': 'Fits your wish to study at your own pace',
    'LEARNING_STYLE_MATCH': 'Fits how you prefer to learn', 'PREFERRED_PROVIDER': 'One of your preferred providers',
    'CREDENTIAL_PREFERENCE_MATCH': 'Offers the kind of credential you prefer',
}


def label(value) -> str:
    if value is None:return 'Not yet known'
    return LABELS.get(str(value), str(value).replace('_', ' ').capitalize())


def gap_advice(gap: dict) -> str:
    kind=gap.get('requirement_subtype') or gap.get('gap_type')
    if gap.get('match') in {'UNKNOWN_DECISION','UNKNOWN_EVIDENCE','UNKNOWN'}:
        return 'Check the posting or add a clear example of your work before deciding.'
    if kind=='EXPERIENCE':return 'Look for supervised work that builds this experience. A course or project does not replace required employment experience.'
    if kind in {'CREDENTIAL','CERTIFICATION'}:return 'Check which award the employer accepts, its entry rules, exam cost and renewal dates.'
    if kind=='EDUCATION':return 'Check the exact education requirement. Short courses do not replace a required degree.'
    if kind in {'LOCATION','LOGISTICS','SCHEDULE','TRAVEL','WORK_AUTHORIZATION'}:return 'Confirm this detail with the employer. Training will not resolve it.'
    return 'Choose a focused learning step and a small project that lets you show what you can do.'
