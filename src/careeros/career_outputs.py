"""Immediate post-onboarding value generated from an approved CareerProfileV1."""

from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from careeros.config.loader import load_config
from careeros.career_conversion import build_career_conversion_trace
from careeros.core.io import atomic_write_json, read_json, sha256_file, sha256_value
from careeros.editorial import default_public_display_policy, evaluate_editorial_quality, public_credentials, public_education
from careeros.evidence_expansion import evaluate_profile_readiness
from careeros.resume import render_pdf
from careeros.resume_ats import (
    ats_resume_round_trip,
    build_recruiter_summary,
    build_resume_header,
    recruiter_safe_filename,
    validate_recruiter_summary,
)
from careeros.recruiter_conversion import (
    build_recruiter_conversion_strategy, _evidence_phrase, public_fact_text,
    public_copy_boundary,
    recruiter_copy_quality_v2,
)
from careeros.schemas.validation import SchemaRegistry
from careeros.resume_governance import (
    build_freshness_contract,
    credential_opportunities,
    professional_history_sufficiency,
    public_artifact_title,
    recruiter_copy_specificity,
)
from careeros.versions import COMPILER_VERSION
from careeros.workspace import require_current_workspace, schema_dir, utc_now


EMPLOYER_SAFE = {"PUBLIC", "EMPLOYER_SAFE", "INTERNAL"}


def _clean_sentence(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" -•\t")
    return text if not text or text.endswith((".", "!", "?")) else text + "."


def _evidence_text(item: dict[str, Any]) -> str:
    return _clean_sentence(_evidence_phrase(item))


def _skill_groups(profile: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in profile.get("skills", []):
        if item.get("visibility") not in EMPLOYER_SAFE:
            continue
        grouped[item.get("category") or "CAPABILITIES"].append({
            "name": item["name"], "record_id": item["record_id"], "evidence_ids": item.get("evidence_ids", []),
        })
    return [{"group": group.upper(), "skills": values} for group, values in sorted(grouped.items()) if values]


def master_resume_content(profile: dict[str, Any]) -> dict[str, Any]:
    policy = default_public_display_policy()
    evidence = {item["record_id"]: item for item in profile.get("evidence", []) if item.get("visibility") in EMPLOYER_SAFE}
    employment = []
    for role in sorted(profile.get("employment", []), key=lambda item: int(item.get("start_year") or 0), reverse=True):
        bullets = []
        for evidence_id in role.get("evidence_ids", []):
            item = evidence.get(evidence_id)
            if item and _evidence_text(item):
                bullets.append({"text": _evidence_text(item), "evidence_ids": [evidence_id]})
        if not bullets:
            continue
        employment.append({
            "employer": role["employer"], "actual_title": role["actual_title"],
            "display_title": role["actual_title"], "public_title_alias": role.get("public_title"),
            "start_year": role.get("start_year"), "end_year": role.get("end_year"),
            "record_id": role["record_id"], "bullets": bullets[:4],
            "display_mode": "FULL" if len(bullets) >= 2 else "COMPACT",
        })
    projects = []
    for project in profile.get("projects", []):
        if project.get("visibility") not in EMPLOYER_SAFE:
            continue
        bullets = [
            {"text": _evidence_text(evidence[evidence_id]), "evidence_ids": [evidence_id]}
            for evidence_id in project.get("evidence_ids", []) if evidence_id in evidence and _evidence_text(evidence[evidence_id])
        ]
        if bullets:
            projects.append({
                "name": project["name"], "date_range": project.get("date_range"),
                "contribution": public_fact_text(project.get("contribution")) or "Project contributor",
                "record_id": project["record_id"], "bullets": bullets[:3], "selection_tier": "PRIMARY",
            })
    groups = _skill_groups(profile)
    skill_names = [item["name"] for group in groups for item in group["skills"]][:5]
    role_names = list(dict.fromkeys(item["actual_title"] for item in employment))[:3]
    foundation = ", ".join(role_names) if role_names else "documented professional and project experience"
    preparation = ", ".join(skill_names) if skill_names else "documented career capabilities"
    target = role_names[0] if role_names else "Career Profile"
    content = {
        "schema": "careeros.resume-content.v1", "candidate": profile["candidate"],
        "target_role": target, "role_family_id": "role-family:master-recruiter",
        "summary": "", "storyline": {}, "public_display_policy": policy,
        "skills": [item for group in groups for item in group["skills"]], "skill_groups": groups,
        "employment": employment, "projects": projects,
        "education": profile.get("education", []), "display_education": public_education(profile, policy),
        "credentials": profile.get("credentials", []), "display_credentials": public_credentials(profile, policy),
        "section_order": ["SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION", "CREDENTIALS"],
    }
    selected = {evidence_id for section in [*employment, *projects] for bullet in section.get("bullets", []) for evidence_id in bullet.get("evidence_ids", [])}
    master_family = {"role_family_id": "role-family:master-recruiter", "display_name": target}
    conversion_strategy = build_recruiter_conversion_strategy(
        profile, master_family, selected_evidence_ids=selected,
    )
    summary_contract = build_recruiter_summary(
        profile, {}, master_family,
        selected_evidence_ids=selected,
    )
    summary_contract["summary_type"] = "MASTER"
    content["recruiter_summary"] = summary_contract
    content["summary"] = summary_contract["text"]
    content["recruiter_conversion_strategy_v2"] = conversion_strategy
    content["resume_header"] = build_resume_header(profile["candidate"], target)
    conversion_trace = build_career_conversion_trace(profile, content, build_scope="MASTER")
    content["role_fact_set"] = conversion_trace["role_fact_set"]
    content["material_evidence_loss"] = conversion_trace["material_evidence_loss"]
    content["career_conversion_trace"] = conversion_trace
    content["public_copy_boundary_v1"] = public_copy_boundary(content)
    content["recruiter_copy_quality_v2"] = recruiter_copy_quality_v2(content, strategy=conversion_strategy)
    return content


def build_master_resume(workspace: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    profile = read_json(roots.state_root / "profile/career-profile.json")
    profile_manifest = read_json(roots.state_root / "profile/profile-build-manifest.json")
    content = master_resume_content(profile)
    created_at = utc_now(timestamp)
    role_family = {"role_family_id": "role-family:master-recruiter", "version": "comprehensive-v1"}
    storyline = {"storyline_id": "master-comprehensive-v1", "section_order": content["section_order"]}
    workspace_manifest = read_json(workspace / "workspace-manifest.json")
    freshness = build_freshness_contract(
        profile, profile_manifest, role_family, storyline,
        canonical_revision=int(workspace_manifest["canonical_head"]["revision"]),
        compiler_version=COMPILER_VERSION,
        editorial_policy_version=content["public_display_policy"]["policy_id"],
        build_timestamp=created_at,
    )
    omission_rationales = {
        item["record_id"]: "OMITTED_NO_SUPPORTED_RECRUITER_DETAIL"
        for item in profile.get("employment", [])
        if item["record_id"] not in {section["record_id"] for section in content["employment"]}
    }
    history = professional_history_sufficiency(profile.get("employment", []), content["employment"], omission_rationales)
    content["canonical_evidence_freshness"] = freshness
    content["professional_history_sufficiency"] = history
    content["recruiter_copy_specificity"] = recruiter_copy_specificity(content, profile)
    content["credential_opportunities"] = credential_opportunities(profile)
    content["editorial_quality"] = evaluate_editorial_quality(content)
    output = roots.output_root / "resumes" / recruiter_safe_filename(profile["candidate"]["public_name"], content["target_role"])
    render_pdf(content, output)
    round_trip = ats_resume_round_trip(content, output)
    registry = SchemaRegistry(schema_dir())
    registry.validate("urn:careeros:schema:resume-header:v1", content["resume_header"])
    registry.validate("urn:careeros:schema:recruiter-summary:v1", content["recruiter_summary"])
    registry.validate("urn:careeros:schema:role-fact-set:v1", content["role_fact_set"])
    registry.validate("urn:careeros:schema:material-evidence-loss:v1", content["material_evidence_loss"])
    registry.validate("urn:careeros:schema:career-conversion-trace:v1", content["career_conversion_trace"])
    registry.validate("urn:careeros:schema:recruiter-conversion-strategy:v2", content["recruiter_conversion_strategy_v2"])
    registry.validate("urn:careeros:schema:public-copy-boundary:v1", content["public_copy_boundary_v1"])
    registry.validate("urn:careeros:schema:recruiter-copy-quality:v2", content["recruiter_copy_quality_v2"])
    registry.validate("urn:careeros:schema:ats-resume-round-trip:v1", round_trip)
    registry.validate("urn:careeros:schema:resume-visual-density:v1", content["resume_visual_density"])
    registry.validate("urn:careeros:schema:premium-resume-quality:v1", content["premium_resume_quality"])
    qa = {
        "canonical_evidence_freshness": "PASS",
        "professional_history_sufficiency": history["status"],
        "empty_experience_entry": "PASS" if not any(not item.get("bullets") for item in content["employment"]) else "FAIL",
        "public_artifact_naming": "PASS",
        "recruiter_copy_specificity": content["recruiter_copy_specificity"]["status"],
        "system_artifact_leakage": len(content["editorial_quality"].get("system_artifact_leaks", [])),
        "header_ats_extraction": "PASS" if all(round_trip["gates"][name] for name in ("NAME_EXTRACTED", "EMAIL_EXTRACTED", "HEADLINE_EXTRACTED", "HEADER_READING_ORDER")) else "FAIL",
        "header_autofill": "PASS" if round_trip["gates"]["AUTOFILL"] else "FAIL",
        "recruiter_summary": validate_recruiter_summary(content["recruiter_summary"])["status"],
        "ats_round_trip": "PASS" if round_trip["status"] == "ATS_SAFE_HIGH_CONFIDENCE" else "FAIL",
        "resume_visual_density": content["resume_visual_density"]["status"],
        "premium_resume_quality": content["premium_resume_quality"]["status"],
        "public_copy_boundary": content["public_copy_boundary_v1"]["status"],
        "recruiter_copy_quality_v2": content["recruiter_copy_quality_v2"]["status"],
        "role_fact_preservation": "PASS" if content["career_conversion_trace"]["gates"]["ROLE_FACT_PRESERVATION"] else "FAIL",
        "material_evidence_loss": "PASS" if content["career_conversion_trace"]["gates"]["MATERIAL_EVIDENCE_LOSS"] else "FAIL",
        "critical_evidence_loss": "PASS" if content["career_conversion_trace"]["gates"]["CRITICAL_EVIDENCE_LOSS"] else "FAIL",
    }
    qa["status"] = "PASS" if all(value in {"PASS", 0} for value in qa.values()) else "FAIL"
    record = {
        "schema": "careeros.master-recruiter-resume.v1", "created_at": created_at,
        "profile_id": profile["profile_id"], "profile_hash": sha256_value(profile),
        "path": output.relative_to(workspace.resolve()).as_posix(), "sha256": sha256_file(output),
        "evidence_ids": sorted({eid for section in [*content["employment"], *content["projects"]] for bullet in section.get("bullets", []) for eid in bullet["evidence_ids"]}),
        "canonical_mutation": False,
        "canonical_evidence_freshness": freshness, "qa": qa,
    }
    atomic_write_json(roots.state_root / "onboarding-outputs/master-recruiter-resume.json", record)
    atomic_write_json(roots.state_root / "onboarding-outputs/master-recruiter-content.json", content)
    atomic_write_json(roots.state_root / "onboarding-outputs/master-resume-header.json", content["resume_header"])
    atomic_write_json(roots.state_root / "onboarding-outputs/master-recruiter-summary.json", content["recruiter_summary"])
    atomic_write_json(roots.state_root / "onboarding-outputs/master-role-fact-set.json", content["role_fact_set"])
    atomic_write_json(roots.state_root / "onboarding-outputs/master-material-evidence-loss.json", content["material_evidence_loss"])
    atomic_write_json(roots.state_root / "onboarding-outputs/master-career-conversion-trace.json", content["career_conversion_trace"])
    atomic_write_json(roots.state_root / "onboarding-outputs/master-recruiter-conversion-strategy-v2.json", content["recruiter_conversion_strategy_v2"])
    atomic_write_json(roots.state_root / "onboarding-outputs/master-public-copy-boundary-v1.json", content["public_copy_boundary_v1"])
    atomic_write_json(roots.state_root / "onboarding-outputs/master-recruiter-copy-quality-v2.json", content["recruiter_copy_quality_v2"])
    atomic_write_json(roots.state_root / "onboarding-outputs/master-ats-resume-round-trip.json", round_trip)
    atomic_write_json(roots.state_root / "onboarding-outputs/master-resume-visual-density.json", content["resume_visual_density"])
    atomic_write_json(roots.state_root / "onboarding-outputs/master-premium-resume-quality.json", content["premium_resume_quality"])
    return record


def discover_lanes(profile: dict[str, Any], *, market_opportunities=None, timestamp: str | None = None) -> dict[str, Any]:
    """Keep career suggestions tied to stated goals, work history and real titles."""
    from careeros.opportunity import evaluate_requirement
    lanes=[];seen=set()
    for intent in profile.get('preferences',{}).get('target_role_intents',[])[:6]:
        titles=intent.get('target_titles',[]);seen.update(t.casefold() for t in titles)
        lanes.append({'lane_id':'lane:'+str(uuid.uuid5(uuid.NAMESPACE_URL,intent['display_name'])),'display_name':intent['display_name'],'classification':'CURRENTLY_PLAUSIBLE','example_titles':titles,'why':'You said this kind of work interests you. Compare current job requirements with your experience before choosing your next step.','evidence_ids':sorted({eid for skill in profile.get('skills',[]) for eid in skill.get('evidence_ids',[])})[:12],'major_barriers':[],'preference_state':'PROPOSED'})
    for job in market_opportunities or []:
        title=job['role_title']
        if title.casefold() in seen:continue
        matches=[];ids=set()
        for requirement in job.get('requirements',[]):
            evidence,gaps,_=evaluate_requirement(profile,requirement)
            for match in evidence:
                if match['match'] in {'SUPPORTED_MATCH','TRANSFERABLE_MATCH'} and not gaps:
                    matches.append(match['capability']);ids.update(match['record_ids'])
        if not matches:continue
        seen.add(title.casefold())
        lanes.append({'lane_id':'lane:'+str(uuid.uuid5(uuid.NAMESPACE_URL,title)),'display_name':title,'classification':'BRIDGE_PLAUSIBLE','example_titles':[title],'why':'Your work with '+', '.join(dict.fromkeys(matches))+' is relevant to the posting from '+job['employer_name']+'. Check the remaining requirements before applying.','evidence_ids':sorted(ids),'major_barriers':['A matching skill does not mean you meet every requirement.'],'preference_state':'PROPOSED'})
    for employment in profile.get('employment',[]):
        title=employment['actual_title']
        if title.casefold() in seen:continue
        seen.add(title.casefold());lanes.append({'lane_id':'lane:'+str(uuid.uuid5(uuid.NAMESPACE_URL,title)),'display_name':title,'classification':'CURRENTLY_PLAUSIBLE','example_titles':[title],'why':'This builds on work you have already done. It is a search idea, not a verified opening.','evidence_ids':[],'major_barriers':[],'preference_state':'PROPOSED'})
    return {'schema':'careeros.career-lane-analysis.v1','created_at':utc_now(timestamp),'lanes':lanes[:12],'requires_candidate_review':True}


def development_intelligence(profile: dict[str, Any], readiness: dict[str, Any], *, timestamp: str | None = None) -> dict[str, Any]:
    gaps: list[dict[str, Any]] = []
    for record_id in readiness.get("recommended_record_ids", []):
        gaps.append({
            "gap_type": "PORTFOLIO_EVIDENCE_GAP", "record_id": record_id,
            "classification": "GENERAL_DEVELOPMENT_GAP", "priority": "NEXT",
            "smallest_intervention": "Answer the highest-value missing evidence questions; no credential is implied.",
        })
    unsupported_skills = [item for item in profile.get("skills", []) if not item.get("evidence_ids")]
    for skill in unsupported_skills:
        gaps.append({
            "gap_type": "SKILL_EVIDENCE_GAP", "record_id": skill["record_id"],
            "classification": "GENERAL_DEVELOPMENT_GAP", "priority": "NOW",
            "smallest_intervention": "Link existing professional, project, lab, or coursework evidence—or remove the unsupported claim.",
        })
    return {
        "schema": "careeros.development-intelligence.v1", "created_at": utc_now(timestamp),
        "education_gaps": [], "credential_gaps": [],
        "skill_tool_gaps": [item for item in gaps if item["gap_type"] == "SKILL_EVIDENCE_GAP"],
        "experience_gaps": [], "portfolio_gaps": [item for item in gaps if item["gap_type"] == "PORTFOLIO_EVIDENCE_GAP"],
        "recommendation_policy": "Smallest credible intervention; no certification recommendation without job or recurring-market evidence.",
    }


def generate_initial_outputs(workspace: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    """Produce all standard onboarding outputs in one package-owned workflow."""
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    profile = read_json(roots.state_root / "profile/career-profile.json")
    readiness = evaluate_profile_readiness(profile, timestamp=timestamp)
    lanes = discover_lanes(profile, timestamp=timestamp)
    titles = {
        "schema": "careeros.role-title-universe.v1", "created_at": utc_now(timestamp),
        "families": [{"lane_id": lane["lane_id"], "titles": lane["example_titles"]} for lane in lanes["lanes"]],
    }
    development = development_intelligence(profile, readiness, timestamp=timestamp)
    master = build_master_resume(workspace, timestamp=timestamp)
    output_root = roots.state_root / "onboarding-outputs"
    atomic_write_json(output_root / "profile-evidence-readiness.json", readiness)
    atomic_write_json(output_root / "career-lanes.json", lanes)
    atomic_write_json(output_root / "role-title-universe.json", titles)
    atomic_write_json(output_root / "career-gaps-development.json", development)
    manifest = {
        "schema": "careeros.initial-career-outputs.v1", "created_at": utc_now(timestamp),
        "career_profile": "state/profile/career-profile.json", "profile_readiness": "state/onboarding-outputs/profile-evidence-readiness.json",
        "master_recruiter_resume": master["path"], "career_lane_analysis": "state/onboarding-outputs/career-lanes.json",
        "role_title_universe": "state/onboarding-outputs/role-title-universe.json",
        "career_gap_analysis": "state/onboarding-outputs/career-gaps-development.json",
        "development_priorities": "state/onboarding-outputs/career-gaps-development.json",
        "canonical_mutation": False,
    }
    atomic_write_json(output_root / "manifest.json", manifest)
    return manifest
