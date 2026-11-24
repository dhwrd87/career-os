"""Governed lane-base resume lifecycle.

Lane bases are immutable derivative artifacts.  They summarize the strongest
truthful default story for an approved RoleFamilyV1 without introducing job
description language or changing canonical career records.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pdfplumber
from PIL import Image
from pypdf import PdfReader

from careeros.completeness import apply_actual_page_utilization, evaluate_resume_completeness
from careeros.career_conversion import build_career_conversion_trace
from careeros.config.loader import load_config
from careeros.core.io import append_jsonl, atomic_write_json, read_json, sha256_file, sha256_value
from careeros.editorial import (
    build_bullet_candidates,
    default_public_display_policy,
    evaluate_editorial_quality,
    group_skills,
    plan_storyline,
    public_credentials,
    public_education,
)
from careeros.resume import render_pdf
from careeros.resume_governance import (
    build_freshness_contract,
    compare_freshness,
    new_evidence_utilization,
    professional_history_sufficiency,
    public_artifact_title,
    public_label_leaks,
    recruiter_copy_specificity,
)
from careeros.resume_ats import (
    ats_resume_round_trip,
    build_recruiter_summary,
    build_resume_header,
    recruiter_safe_filename,
    validate_recruiter_summary,
)
from careeros.recruiter_conversion import (
    build_recruiter_conversion_strategy,
    public_copy_boundary,
    recruiter_copy_quality_v2,
)
from careeros.schemas.validation import SchemaRegistry
from careeros.updates import mark_derivative_current, require_derivative_current
from careeros.versions import COMPILER_VERSION, FONT_PROFILE_VERSION, TEMPLATE_VERSION, TRUTH_POLICY_VERSION
from careeros.workspace import require_current_workspace, schema_dir, utc_now


EDITORIAL_POLICY_VERSION = "resume-editorial-intelligence-v1"
USABLE_VISIBILITY = {"PUBLIC", "EMPLOYER_SAFE", "INTERNAL"}
POSITIVE_TIERS = {"ANCHOR", "SUPPORTING", "CONTEXT"}


def _safe_token(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9 ._()-]+", "", value).strip(" .")
    return re.sub(r"\s+", " ", result) or "Lane Base"


def _storyline_id(profile_hash: str, family: dict[str, Any]) -> str:
    key = f"{profile_hash}:{family['role_family_id']}:{EDITORIAL_POLICY_VERSION}"
    return f"storyline:{uuid.uuid5(uuid.NAMESPACE_URL, key)}"


def _lane_content(profile: dict[str, Any], family: dict[str, Any], storyline: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    policy = default_public_display_policy()
    rankings = {item["evidence_id"]: item.get("classification", "OPTIONAL") for item in storyline.get("evidence_rankings", [])}
    candidates = build_bullet_candidates(profile, storyline)
    candidates_by_evidence = {item["evidence_ids"][0]: item for item in candidates}
    selected_ids = {
        evidence_id for evidence_id, tier in rankings.items()
        if tier in POSITIVE_TIERS
    }
    # Real professional history is a credibility floor even when lane relevance is transferable.
    selected_ids.update(
        item["record_id"] for item in profile.get("evidence", [])
        if item.get("employment_ids") and item.get("visibility") in USABLE_VISIBILITY
    )
    # Lane bases preserve useful project breadth even when generic lane scoring
    # cannot promote a project above OPTIONAL without a specific JD.
    selected_ids.update(
        item["record_id"] for item in profile.get("evidence", [])
        if item.get("project_ids") and item.get("visibility") in USABLE_VISIBILITY
        and rankings.get(item["record_id"]) != "DISTRACTING"
    )
    omitted: list[dict[str, Any]] = []
    used: set[str] = set()
    employment_sections: list[dict[str, Any]] = []
    ordered_employment = sorted(
        profile.get("employment", []),
        key=lambda item: (item.get("end_year") in {None, "PRESENT"}, int(item.get("start_year") or 0)),
        reverse=True,
    )
    for employment in ordered_employment:
        if employment.get("visibility") not in USABLE_VISIBILITY:
            continue
        bullets = []
        for evidence_id in employment.get("evidence_ids", []):
            candidate = candidates_by_evidence.get(evidence_id)
            if candidate and evidence_id in selected_ids and evidence_id not in used:
                bullets.append(candidate)
        # A lane base is a reusable evidence-rich default, not a minimal
        # job-specific extract.  Keep enough supported detail to establish
        # professional credibility; account as used only what is rendered.
        rendered_bullets = bullets[:4]
        if not rendered_bullets:
            evidence_index = {item["record_id"]: item for item in profile.get("evidence", [])}
            fallback = next((
                evidence_index.get(evidence_id)
                for evidence_id in employment.get("evidence_ids", [])
                if evidence_index.get(evidence_id, {}).get("visibility") in USABLE_VISIBILITY
                and str(evidence_index.get(evidence_id, {}).get("summary", "")).strip()
            ), None)
            if fallback:
                rendered_bullets = [{
                    "bullet_id": f"bullet:{fallback['record_id']}:minimal",
                    "evidence_ids": [fallback["record_id"]],
                    "text": str(fallback["summary"]).strip().rstrip(".") + ".",
                    "outcome": "", "metric_refs": [], "unsupported_metric_tokens": [],
                    "variant_mode": "MINIMAL_HISTORY",
                }]
        used.update(
            evidence_id
            for bullet in rendered_bullets
            for evidence_id in bullet["evidence_ids"]
        )
        omitted.extend(
            {"bullet_id": item["bullet_id"], "reason": "SPACE", "evidence_ids": item["evidence_ids"]}
            for item in bullets[4:]
        )
        employment_sections.append({
            "employer": employment["employer"], "actual_title": employment["actual_title"],
            "public_title_alias": employment.get("public_title"), "display_title": employment["actual_title"],
            "start_year": employment.get("start_year"), "end_year": employment.get("end_year"),
            "record_id": employment["record_id"], "bullets": rendered_bullets,
            "display_mode": "FULL" if len(rendered_bullets) >= 2 else ("COMPACT" if rendered_bullets else "MINIMAL"),
        })
    project_rank = {item["evidence_id"]: index for index, item in enumerate(storyline.get("evidence_rankings", []))}
    projects = sorted(
        profile.get("projects", []),
        key=lambda item: min([project_rank.get(evidence_id, 10_000) for evidence_id in item.get("evidence_ids", [])] or [10_000]),
    )
    project_sections: list[dict[str, Any]] = []
    for project in projects:
        if project.get("visibility") not in USABLE_VISIBILITY:
            continue
        bullets = []
        for evidence_id in project.get("evidence_ids", []):
            candidate = candidates_by_evidence.get(evidence_id)
            if candidate and evidence_id in selected_ids and evidence_id not in used:
                bullets.append(candidate)
        # Preserve project breadth for early-career and career-changing users.
        # Six bounded projects still fit the two-page lane-base contract, while
        # avoiding underfilled one-page artifacts with useful evidence omitted.
        if bullets and len(project_sections) < 6:
            rendered_bullets = bullets[:3]
            used.update(
                evidence_id
                for bullet in rendered_bullets
                for evidence_id in bullet["evidence_ids"]
            )
            omitted.extend(
                {"bullet_id": item["bullet_id"], "reason": "SPACE", "evidence_ids": item["evidence_ids"]}
                for item in bullets[3:]
            )
            project_sections.append({
                "name": project["name"], "date_range": project.get("date_range"),
                "contribution": project.get("contribution") or "Project contributor",
                "record_id": project["record_id"], "bullets": rendered_bullets,
                "selection_tier": "PRIMARY" if len(project_sections) < 2 else "SECONDARY",
            })
        elif bullets:
            omitted.extend({"bullet_id": item["bullet_id"], "reason": "SPACE", "evidence_ids": item["evidence_ids"]} for item in bullets)
    displayed_evidence = {
        evidence_id
        for section in [*employment_sections, *project_sections]
        for bullet in section.get("bullets", [])
        for evidence_id in bullet.get("evidence_ids", [])
    }
    skill_groups = []
    for group in group_skills(profile, storyline, policy):
        skills = [
            item for item in group["skills"]
            if group["group"] == "LANGUAGES" or bool(set(item.get("evidence_ids", [])) & displayed_evidence)
        ]
        if skills:
            skill_groups.append({"group": group["group"], "skills": skills})
    skills = [item for group in skill_groups for item in group["skills"]]
    target = family.get("display_name") or family.get("label")
    content = {
        "schema": "careeros.resume-content.v1", "candidate": profile["candidate"],
        "target_role": target, "role_family_id": family["role_family_id"],
        "summary": (
            f"{storyline['candidate_positioning']} Brings a documented professional foundation and completed project preparation "
            f"while keeping project work distinct from professional {target} experience."
        ),
        "storyline": storyline, "public_display_policy": policy,
        "skills": [{"name": item["name"], "record_id": item["record_id"], "evidence_ids": item.get("evidence_ids", [])} for item in skills],
        "skill_groups": skill_groups, "employment": employment_sections, "projects": project_sections,
        "education": profile.get("education", []), "display_education": public_education(profile, policy),
        "credentials": [item for item in profile.get("credentials", []) if item.get("visibility") in USABLE_VISIBILITY],
        "display_credentials": public_credentials(profile, policy),
        "section_order": storyline["section_priority"],
    }
    conversion_strategy = build_recruiter_conversion_strategy(
        profile, family, selected_evidence_ids=displayed_evidence,
    )
    summary_contract = build_recruiter_summary(
        profile, storyline, family, selected_evidence_ids=displayed_evidence,
    )
    content["recruiter_summary"] = summary_contract
    content["summary"] = summary_contract["text"]
    content["recruiter_conversion_strategy_v2"] = conversion_strategy
    content["resume_header"] = build_resume_header(profile["candidate"], target)
    content["resume_completeness"] = evaluate_resume_completeness(profile, content, omitted)
    content["editorial_quality"] = evaluate_editorial_quality(content)
    omission_reasons = {
        evidence_id: str(item.get("reason") or "OTHER")
        for item in omitted for evidence_id in item.get("evidence_ids", [])
    }
    conversion_trace = build_career_conversion_trace(
        profile, content, build_scope="LANE", omission_reasons=omission_reasons,
    )
    content["role_fact_set"] = conversion_trace["role_fact_set"]
    content["material_evidence_loss"] = conversion_trace["material_evidence_loss"]
    content["career_conversion_trace"] = conversion_trace
    content["public_copy_boundary_v1"] = public_copy_boundary(content)
    content["recruiter_copy_quality_v2"] = recruiter_copy_quality_v2(content, strategy=conversion_strategy)
    return content, omitted


def _gate(name: str, passed: bool, detail: str) -> dict[str, str]:
    return {"gate": name, "status": "PASS" if passed else "FAIL", "detail": detail}


def _validate_pdf(workspace: Path, lane_dir: Path, base: dict[str, Any], content: dict[str, Any], artifact: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    roots = load_config(workspace / "careeros.yaml").roots
    pdf_path = roots.output_root / artifact["path"]
    profile = read_json(roots.state_root / "profile/career-profile.json")
    registry = SchemaRegistry(schema_dir())
    gates: list[dict[str, str]] = []
    from careeros.document_quality import inspect_pdf
    object_preflight = inspect_pdf(pdf_path)
    gates.append(_gate("PDF_OBJECT_PREFLIGHT", object_preflight['status'] == 'PASS', str(object_preflight['findings'])))
    try:
        registry.validate("urn:careeros:schema:lane-base-resume:v1", base)
        registry.validate("urn:careeros:schema:resume-artifact:v1", artifact)
        schema_ok, schema_detail = True, "typed lane base and artifact contracts"
    except Exception as exc:
        schema_ok, schema_detail = False, str(exc)
    gates.append(_gate("SCHEMA", schema_ok, schema_detail))
    round_trip = ats_resume_round_trip(content, pdf_path)
    registry.validate("urn:careeros:schema:resume-header:v1", content["resume_header"])
    registry.validate("urn:careeros:schema:recruiter-summary:v1", content["recruiter_summary"])
    registry.validate("urn:careeros:schema:ats-resume-round-trip:v1", round_trip)
    registry.validate("urn:careeros:schema:resume-visual-density:v1", content["resume_visual_density"])
    registry.validate("urn:careeros:schema:premium-resume-quality:v1", content["premium_resume_quality"])
    registry.validate("urn:careeros:schema:recruiter-conversion-strategy:v2", content["recruiter_conversion_strategy_v2"])
    registry.validate("urn:careeros:schema:public-copy-boundary:v1", content["public_copy_boundary_v1"])
    registry.validate("urn:careeros:schema:recruiter-copy-quality:v2", content["recruiter_copy_quality_v2"])
    for gate_name, passed in round_trip["gates"].items():
        gates.append(_gate(gate_name, bool(passed), round_trip["status"]))
    gates.append(_gate("ATS_CONFIDENCE", round_trip["status"] == "ATS_SAFE_HIGH_CONFIDENCE", round_trip["confidence"]))
    gates.append(_gate("SUMMARY_QUALITY", validate_recruiter_summary(content["recruiter_summary"])["status"] == "PASS", str(validate_recruiter_summary(content["recruiter_summary"]))))
    premium = content["premium_resume_quality"]
    density = content["resume_visual_density"]
    gates.append(_gate("PREMIUM_RESUME_QUALITY", premium["status"] == "PASS", f"score={premium['score']}; flags={premium['flags']}"))
    gates.append(_gate("RESUME_VISUAL_DENSITY", density["status"] == "PASS", f"utilization={density['measurements']['average_page_utilization']:.0%}"))
    profile_manifest = read_json(roots.state_root / "profile/profile-build-manifest.json")
    family = read_json(roots.state_root / "role-families/active.json")
    workspace_manifest = read_json(workspace / "workspace-manifest.json")
    current_freshness = build_freshness_contract(
        profile, profile_manifest, family, content["storyline"],
        canonical_revision=int(workspace_manifest["canonical_head"]["revision"]),
        compiler_version=COMPILER_VERSION, editorial_policy_version=EDITORIAL_POLICY_VERSION,
        build_timestamp=base["created_at"],
    )
    freshness = compare_freshness(base["canonical_evidence_freshness"], current_freshness)
    gates.append(_gate("CANONICAL_EVIDENCE_FRESHNESS", freshness["acceptance_allowed"], freshness["status"]))
    utilization = content.get("new_evidence_utilization", {})
    gates.append(_gate("NEW_EVIDENCE_UTILIZATION", utilization.get("status") == "PASS", f"silent_high_value={len(utilization.get('high_value_silent_omissions', []))}"))
    history = professional_history_sufficiency(
        [item for item in profile.get("employment", []) if item.get("visibility") in USABLE_VISIBILITY], content.get("employment", []),
    )
    gates.append(_gate("PROFESSIONAL_HISTORY_SUFFICIENCY", history["status"] == "PASS", str(history["failures"])))
    gates.append(_gate("EMPTY_EXPERIENCE_ENTRY", not any(item["code"] == "EMPTY_EXPERIENCE_ENTRY" for item in history["failures"]), "every displayed role has supported content"))
    evidence_ids = {item["record_id"] for item in profile.get("evidence", [])}
    bullets = [item for section in [*content.get("employment", []), *content.get("projects", [])] for item in section.get("bullets", [])]
    bullet_ids = {evidence_id for item in bullets for evidence_id in item.get("evidence_ids", [])}
    gates.append(_gate("TRUTH", bullet_ids <= evidence_ids, "all rendered bullets retain canonical evidence IDs"))
    gates.append(_gate("PROVENANCE", bullet_ids <= set(base["anchor_evidence_ids"] + base["supporting_evidence_ids"] + base["transferable_evidence_ids"]), "rendered evidence is declared by the lane base"))
    completeness = content["resume_completeness"]
    gates.append(_gate("CAREER_CONTINUITY", completeness["career_continuity"]["status"] in {"PASS", "REVIEW"}, "material chronology is retained or explicitly compressed"))
    gates.append(_gate("PROFESSIONAL_CREDIBILITY", completeness["professional_history_coverage"]["status"] != "REVIEW", "professional credibility floor satisfied"))
    gates.append(_gate("STORYLINE_COMPLETENESS", completeness["storyline_continuity"]["status"] == "PASS", "foundation, preparation, and target direction are present"))
    gates.append(_gate("EVIDENCE_SUFFICIENCY", completeness["status"] != "FAIL", f"completeness={completeness['status']}"))
    editorial = content["editorial_quality"]
    gates.append(_gate("EDITORIAL_QUALITY", editorial["status"] == "PASS", f"score={editorial['score']}"))
    specificity = recruiter_copy_specificity(content, profile)
    gates.append(_gate("RECRUITER_COPY_SPECIFICITY", specificity["status"] == "PASS", ", ".join(specificity["abstract_phrases"]) or "specific copy"))
    gates.append(_gate("PUBLIC_COPY_BOUNDARY", content.get("public_copy_boundary_v1", {}).get("status") == "PASS", str(content.get("public_copy_boundary_v1", {}).get("findings", []))))
    gates.append(_gate("RECRUITER_COPY_QUALITY_V2", content.get("recruiter_copy_quality_v2", {}).get("status") == "PASS", f"score={content.get('recruiter_copy_quality_v2', {}).get('score')}"))
    gates.append(_gate("LANE_DIFFERENTIATION", bool(base["target_title_family"] and base["positioning"] and base["storyline_id"]), "lane identity and ranked evidence are explicit"))
    gates.append(_gate("UNSUPPORTED_METRIC", not any(item.get("unsupported_metric_tokens") for item in bullets), "no unsupported metric rendered"))
    conversion = content.get("career_conversion_trace", {})
    for gate_name in ("ROLE_FACT_PRESERVATION", "MATERIAL_EVIDENCE_LOSS", "CRITICAL_EVIDENCE_LOSS"):
        gates.append(_gate(gate_name, bool(conversion.get("gates", {}).get(gate_name)), f"conversion_status={conversion.get('status', 'MISSING')}"))
    reader = PdfReader(str(pdf_path))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    label_leaks = public_label_leaks(extracted)
    gates.append(_gate("PUBLIC_ARTIFACT_NAMING", not label_leaks, ", ".join(label_leaks) or "public labels sanitized"))
    gates.append(_gate("SYSTEM_ARTIFACT_LEAKAGE", not label_leaks and not editorial.get("system_artifact_leaks"), "none" if not label_leaks and not editorial.get("system_artifact_leaks") else str(label_leaks + editorial.get("system_artifact_leaks", []))))
    gates.append(_gate("ATS", len(extracted) >= 120 and "EXPERIENCE" in extracted, f"{len(extracted)} extractable characters"))
    candidate = profile["candidate"]
    autofill_values = [candidate.get("public_name"), candidate.get("contact", {}).get("email"), candidate.get("contact", {}).get("phone")]
    gates.append(_gate("AUTOFILL", all(not item or item in extracted for item in autofill_values), "candidate contact fields remain extractable"))
    geometry_ok = all(abs(float(page.mediabox.width) - 612) < 1 and abs(float(page.mediabox.height) - 792) < 1 for page in reader.pages)
    gates.append(_gate("PAGE_GEOMETRY", geometry_ok and len(reader.pages) <= 2, f"letter pages={len(reader.pages)}"))
    render_paths: list[str] = []
    with pdfplumber.open(pdf_path) as document:
        within = all(
            page.chars and all(0 <= char["x0"] <= page.width and 0 <= char["x1"] <= page.width and 0 <= char["top"] <= page.height and 0 <= char["bottom"] <= page.height for char in page.chars)
            for page in document.pages
        )
        utilizations = [
            (max(char["bottom"] for char in page.chars) - min(char["top"] for char in page.chars)) / max(1.0, page.height - 72)
            for page in document.pages if page.chars
        ]
        utilization = sum(utilizations) / max(1, len(utilizations))
    visual_ok = bool(within)
    poppler = shutil.which("pdftoppm")
    if poppler:
        qa_root = roots.output_root / "qa" / base["lane_base_id"]
        qa_root.mkdir(parents=True, exist_ok=True)
        prefix = qa_root / "page"
        subprocess.run([poppler, "-png", "-r", "144", str(pdf_path), str(prefix)], check=True, capture_output=True)
        images = sorted(qa_root.glob("page-*.png"))
        checks = []
        for image_path in images:
            with Image.open(image_path) as image:
                bounds = image.convert("L").point(lambda pixel: 0 if pixel > 250 else 255).getbbox()
                checks.append(bool(bounds) and bounds[0] > 20 and bounds[1] > 20 and bounds[2] < image.width - 20 and bounds[3] < image.height - 20)
            render_paths.append(str(image_path.relative_to(roots.output_root)))
        visual_ok = visual_ok and bool(images) and all(checks)
    gates.append(_gate("VISUAL_QA", visual_ok, "bounded, nonblank pages"))
    completeness = apply_actual_page_utilization(completeness, utilization)
    content["resume_completeness"] = completeness
    gates.append(_gate("UNDERFILL_OVERFILL", completeness["page_utilization"]["status"] == "PASS", f"utilization={utilization:.0%}; status={completeness['page_utilization']['status']}"))
    metadata = reader.metadata or {}
    expected_title = f"{content['resume_header']['candidate_name']} - {content['resume_header']['positioning_headline']} Resume"
    metadata_ok = (
        metadata.get("/Author") == candidate["public_name"]
        and metadata.get("/Title") == expected_title
        and metadata.get("/Subject") == "Resume"
    )
    gates.append(_gate("METADATA", metadata_ok and sha256_file(pdf_path) == artifact["sha256"], "candidate metadata and artifact hash verified"))
    all_pass = all(item["status"] == "PASS" for item in gates)
    validation = {
        "schema": "careeros.lane-base-validation.v1", "lane_base_id": base["lane_base_id"],
        "build_id": base["build_id"], "status": "PASS" if all_pass else "FAIL",
        "gates": gates, "render_paths": render_paths,
    }
    atomic_write_json(lane_dir / "content.json", content)
    atomic_write_json(lane_dir / "ats-resume-round-trip.json", round_trip)
    atomic_write_json(lane_dir / "resume-visual-density.json", density)
    atomic_write_json(lane_dir / "premium-resume-quality.json", premium)
    atomic_write_json(lane_dir / "validation.json", validation)
    return validation, content


def build_lane_base(workspace: Path, *, accept: bool = False, actor: str | None = None, timestamp: str | None = None) -> dict[str, Any]:
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    profile = read_json(roots.state_root / "profile/career-profile.json")
    profile_manifest = read_json(roots.state_root / "profile/profile-build-manifest.json")
    family = read_json(roots.state_root / "role-families/active.json")
    if family.get("approval_state") != "APPROVED":
        raise PermissionError("BUILD_LANE_BASE requires an approved RoleFamilyV1")
    require_derivative_current(roots, "CAREER_PROFILE", profile["profile_id"])
    require_derivative_current(roots, "ROLE_FAMILY", family["role_family_id"])
    created_at = utc_now(timestamp)
    profile_hash = profile_manifest["profile_hash"]
    storyline = plan_storyline(profile, family)
    storyline["storyline_id"] = _storyline_id(profile_hash, family)
    content, omitted = _lane_content(profile, family, storyline)
    selected_ids = sorted({evidence_id for section in [*content["employment"], *content["projects"]] for bullet in section.get("bullets", []) for evidence_id in bullet.get("evidence_ids", [])})
    role_hash = sha256_value(family)
    key = f"{profile_hash}:{role_hash}:{EDITORIAL_POLICY_VERSION}:{TEMPLATE_VERSION}"
    lane_base_id = f"lane-base:{uuid.uuid5(uuid.NAMESPACE_URL, key)}"
    build_id = f"lane-base-build:{uuid.uuid5(uuid.NAMESPACE_URL, key + ':build')}"
    artifact_id = f"artifact:{uuid.uuid5(uuid.NAMESPACE_URL, key + ':pdf')}"
    public_title = public_artifact_title("LANE_BASE", family.get("display_name") or family.get("label"))
    filename = recruiter_safe_filename(profile["candidate"]["public_name"], public_title)
    pdf_path = roots.output_root / "lane-bases" / filename
    lane_dir = roots.state_root / "lane-bases" / lane_base_id
    if lane_dir.exists():
        existing = read_json(lane_dir / "lane-base.json")
        return {"lane_base": existing, "validation": read_json(lane_dir / "validation.json"), "artifact": read_json(lane_dir / "artifact.json"), "idempotency_status": "EXISTING_BUILD"}
    render_pdf(content, roots.assert_write_allowed(pdf_path, "output"))
    reader = PdfReader(str(pdf_path))
    artifact = {
        "schema": "careeros.resume-artifact.v1", "schema_version": "1.0.0", "artifact_id": artifact_id,
        "build_id": build_id, "media_type": "application/pdf", "path": str(pdf_path.relative_to(roots.output_root)),
        "sha256": sha256_file(pdf_path), "page_count": len(reader.pages),
        "metadata": {"title": f"{content['resume_header']['candidate_name']} - {content['resume_header']['positioning_headline']} Resume", "author": profile["candidate"]["public_name"], "subject": "Resume", "template": TEMPLATE_VERSION, "font_profile": FONT_PROFILE_VERSION, "artifact_kind": "LANE_BASE"},
        "status": "CANDIDATE", "accepted_at": None, "supersedes": None,
    }
    workspace_manifest = read_json(workspace / "workspace-manifest.json")
    freshness = build_freshness_contract(
        profile, profile_manifest, family, storyline,
        canonical_revision=int(workspace_manifest["canonical_head"]["revision"]),
        compiler_version=COMPILER_VERSION, editorial_policy_version=EDITORIAL_POLICY_VERSION,
        build_timestamp=created_at,
    )
    rendered_evidence = {
        evidence_id for section in [*content["employment"], *content["projects"]]
        for bullet in section.get("bullets", []) for evidence_id in bullet.get("evidence_ids", [])
    }
    omission_dispositions = {
        evidence_id: ("OMITTED_REDUNDANT" if item.get("reason") == "REDUNDANT" else "OMITTED_SPACE")
        for item in omitted for evidence_id in item.get("evidence_ids", [])
    }
    for item in profile.get("evidence", []):
        if item["record_id"] not in rendered_evidence and item["record_id"] not in omission_dispositions:
            omission_dispositions[item["record_id"]] = "OMITTED_PRIVACY" if item.get("visibility") not in USABLE_VISIBILITY else "OMITTED_LOW_RELEVANCE"
    utilization = new_evidence_utilization(
        None, profile, rendered_evidence, omission_dispositions,
        relevant_evidence_ids=set(storyline.get("anchor_evidence", [])) | set(storyline.get("supporting_evidence", [])) | set(storyline.get("context_evidence", [])),
    )
    history = professional_history_sufficiency(
        [item for item in profile.get("employment", []) if item.get("visibility") in USABLE_VISIBILITY], content["employment"],
    )
    content["canonical_evidence_freshness"] = freshness
    content["new_evidence_utilization"] = utilization
    content["professional_history_sufficiency"] = history
    content["recruiter_copy_specificity"] = recruiter_copy_specificity(content, profile)
    base = {
        "schema": "careeros.lane-base-resume.v1", "schema_version": "1.0.0", "lane_base_id": lane_base_id,
        "candidate_profile_id": profile["profile_id"], "role_family_id": family["role_family_id"],
        "career_profile_hash": profile_hash, "storyline_id": storyline["storyline_id"],
        "target_title_family": family.get("target_titles") or [family.get("display_name") or family["label"]],
        "positioning": storyline["candidate_positioning"],
        "anchor_evidence_ids": storyline["anchor_evidence"],
        "supporting_evidence_ids": sorted(set(storyline["supporting_evidence"]) | {
            item["record_id"] for item in profile.get("evidence", [])
            if item.get("project_ids") and item.get("record_id") in selected_ids
        }),
        "transferable_evidence_ids": storyline["context_evidence"], "default_section_order": content["section_order"],
        "default_project_order": [item["record_id"] for item in content["projects"]], "skill_groups": content["skill_groups"],
        "allowed_claims": [item for item in family.get("core_capabilities", []) if any(skill.get("name", "").casefold() == item.casefold() and skill.get("evidence_ids") for skill in profile.get("skills", []))],
        "prohibited_claims": ["Project, lab, simulation, and coursework evidence must not be represented as professional experience", "Unsupported metrics, seniority, titles, credentials, and tools are prohibited"],
        "gap_assumptions": list(family.get("common_gaps", [])), "compiler_version": COMPILER_VERSION,
        "editorial_policy_version": EDITORIAL_POLICY_VERSION, "template_version": TEMPLATE_VERSION,
        "build_id": build_id, "artifact_id": artifact_id, "status": "REVIEW_REQUIRED",
        "created_at": created_at, "updated_at": created_at, "supersedes": None,
        "canonical_evidence_freshness": freshness,
    }
    manifest = {
        "schema": "careeros.lane-base-build-manifest.v1", "schema_version": "1.0.0", "build_id": build_id,
        "lane_base_id": lane_base_id, "career_profile_hash": profile_hash, "role_family_hash": role_hash,
        "storyline_hash": sha256_value(storyline), "input_evidence_ids": sorted(item["record_id"] for item in profile.get("evidence", [])),
        "selected_evidence_ids": selected_ids, "compiler_version": COMPILER_VERSION,
        "editorial_policy_version": EDITORIAL_POLICY_VERSION, "template_version": TEMPLATE_VERSION,
        "font_profile_version": FONT_PROFILE_VERSION, "qa_status": "BUILDING", "created_at": created_at,
        "canonical_evidence_freshness": freshness,
    }
    registry = SchemaRegistry(schema_dir())
    registry.validate("urn:careeros:schema:lane-base-resume:v1", base)
    registry.validate("urn:careeros:schema:lane-base-build-manifest:v1", manifest)
    registry.validate("urn:careeros:schema:resume-storyline:v1", storyline)
    registry.validate("urn:careeros:schema:resume-artifact:v1", artifact)
    registry.validate("urn:careeros:schema:canonical-evidence-freshness:v1", freshness)
    registry.validate("urn:careeros:schema:new-evidence-utilization:v1", utilization)
    registry.validate("urn:careeros:schema:professional-history-sufficiency:v1", history)
    registry.validate("urn:careeros:schema:recruiter-copy-specificity:v1", content["recruiter_copy_specificity"])
    registry.validate("urn:careeros:schema:resume-header:v1", content["resume_header"])
    registry.validate("urn:careeros:schema:recruiter-summary:v1", content["recruiter_summary"])
    registry.validate("urn:careeros:schema:role-fact-set:v1", content["role_fact_set"])
    registry.validate("urn:careeros:schema:material-evidence-loss:v1", content["material_evidence_loss"])
    registry.validate("urn:careeros:schema:career-conversion-trace:v1", content["career_conversion_trace"])
    registry.validate("urn:careeros:schema:recruiter-conversion-strategy:v2", content["recruiter_conversion_strategy_v2"])
    registry.validate("urn:careeros:schema:public-copy-boundary:v1", content["public_copy_boundary_v1"])
    registry.validate("urn:careeros:schema:recruiter-copy-quality:v2", content["recruiter_copy_quality_v2"])
    atomic_write_json(lane_dir / "lane-base.json", base)
    atomic_write_json(lane_dir / "storyline.json", storyline)
    atomic_write_json(lane_dir / "build-manifest.json", manifest)
    atomic_write_json(lane_dir / "artifact.json", artifact)
    atomic_write_json(lane_dir / "omitted-evidence.json", {"items": omitted})
    atomic_write_json(lane_dir / "canonical-evidence-freshness.json", freshness)
    atomic_write_json(lane_dir / "new-evidence-utilization.json", utilization)
    atomic_write_json(lane_dir / "professional-history-sufficiency.json", history)
    atomic_write_json(lane_dir / "resume-header.json", content["resume_header"])
    atomic_write_json(lane_dir / "recruiter-summary.json", content["recruiter_summary"])
    atomic_write_json(lane_dir / "role-fact-set.json", content["role_fact_set"])
    atomic_write_json(lane_dir / "material-evidence-loss.json", content["material_evidence_loss"])
    atomic_write_json(lane_dir / "career-conversion-trace.json", content["career_conversion_trace"])
    atomic_write_json(lane_dir / "recruiter-conversion-strategy-v2.json", content["recruiter_conversion_strategy_v2"])
    atomic_write_json(lane_dir / "public-copy-boundary-v1.json", content["public_copy_boundary_v1"])
    atomic_write_json(lane_dir / "recruiter-copy-quality-v2.json", content["recruiter_copy_quality_v2"])
    validation, content = _validate_pdf(workspace, lane_dir, base, content, artifact)
    manifest["qa_status"] = validation["status"]
    atomic_write_json(lane_dir / "build-manifest.json", manifest)
    if validation["status"] != "PASS":
        base["status"] = "REJECTED"
        base["updated_at"] = created_at
        artifact["status"] = "REJECTED"
        atomic_write_json(lane_dir / "lane-base.json", base)
        atomic_write_json(lane_dir / "artifact.json", artifact)
        return {"lane_base": base, "validation": validation, "artifact": artifact, "build_manifest": manifest}
    mark_derivative_current(roots, "LANE_BASE_RESUME", lane_base_id, timestamp=created_at, lineage_hash=artifact["sha256"])
    active_path = roots.state_root / "lane-bases/active.json"
    active = read_json(active_path) if active_path.is_file() else {"schema": "careeros.lane-base-index.v1", "entries": []}
    active["entries"] = [item for item in active["entries"] if item["role_family_id"] != family["role_family_id"]]
    active["entries"].append({"role_family_id": family["role_family_id"], "lane_base_id": lane_base_id, "path": str((lane_dir / "lane-base.json").relative_to(roots.state_root)), "status": base["status"]})
    atomic_write_json(active_path, active)
    if accept:
        return accept_lane_base(workspace, lane_base_id, actor=actor or "human", timestamp=created_at)
    return {"lane_base": base, "validation": validation, "artifact": artifact, "build_manifest": manifest}


def accept_lane_base(workspace: Path, lane_base_id: str, *, actor: str, timestamp: str | None = None) -> dict[str, Any]:
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    lane_dir = roots.state_root / "lane-bases" / lane_base_id
    base = read_json(lane_dir / "lane-base.json")
    validation = read_json(lane_dir / "validation.json")
    artifact = read_json(lane_dir / "artifact.json")
    if validation["status"] != "PASS":
        raise PermissionError("lane base cannot be accepted until all QA gates pass")
    fresh_gate = next((item for item in validation.get("gates", []) if item.get("gate") == "CANONICAL_EVIDENCE_FRESHNESS"), None)
    if not fresh_gate or fresh_gate.get("status") != "PASS":
        raise PermissionError("lane base cannot be accepted from stale canonical inputs")
    accepted_at = utc_now(timestamp)
    base["status"] = "ACCEPTED"
    base["updated_at"] = accepted_at
    artifact["status"] = "ACCEPTED"
    artifact["accepted_at"] = accepted_at
    atomic_write_json(lane_dir / "lane-base.json", base)
    atomic_write_json(lane_dir / "artifact.json", artifact)
    active = read_json(roots.state_root / "lane-bases/active.json")
    for item in active["entries"]:
        if item["lane_base_id"] == lane_base_id:
            item["status"] = "ACCEPTED"
    atomic_write_json(roots.state_root / "lane-bases/active.json", active)
    append_jsonl(roots.state_root / "audit-events.jsonl", {
        "schema": "careeros.audit-event.v1", "event": "LANE_BASE_ACCEPTED", "actor": actor,
        "occurred_at": accepted_at, "source_hash": artifact["sha256"], "record_ids": [lane_base_id],
    })
    return {"lane_base": base, "validation": validation, "artifact": artifact, "approval": {"actor": actor, "accepted_at": accepted_at}}


def effective_status(workspace: Path, lane_base_id: str) -> dict[str, Any]:
    require_current_workspace(workspace)
    roots = load_config(workspace / "careeros.yaml").roots
    lane_dir = roots.state_root / "lane-bases" / lane_base_id
    base = read_json(lane_dir / "lane-base.json")
    manifest = read_json(lane_dir / "build-manifest.json")
    reasons: list[str] = []
    current_profile = read_json(roots.state_root / "profile/profile-build-manifest.json")
    current_family = read_json(roots.state_root / "role-families/active.json")
    if base["career_profile_hash"] != current_profile["profile_hash"]:
        reasons.append("STALE_PROFILE_CHANGE")
    if manifest["role_family_hash"] != sha256_value(current_family):
        reasons.append("STALE_ROLE_FAMILY_CHANGE")
    if base["editorial_policy_version"] != EDITORIAL_POLICY_VERSION:
        reasons.append("STALE_POLICY_CHANGE")
    if base["template_version"] != TEMPLATE_VERSION:
        reasons.append("STALE_TEMPLATE_CHANGE")
    status_path = roots.state_root / "derivative-status.json"
    if status_path.is_file():
        entry = next((item for item in read_json(status_path).get("entries", []) if item.get("derivative_type") == "LANE_BASE_RESUME" and item.get("derivative_id") == lane_base_id), None)
        if entry and entry.get("status") == "STALE" and "STALE_PROFILE_CHANGE" not in reasons:
            reasons.append("STALE_PROFILE_CHANGE")
    return {
        "schema": "careeros.lane-base-status.v1", "lane_base_id": lane_base_id,
        "contract_status": base["status"], "effective_status": reasons[0] if reasons else "CURRENT",
        "stale_reasons": reasons, "reuse_allowed": base["status"] == "ACCEPTED" and not reasons,
        "historical_artifact_immutable": base["status"] == "ACCEPTED",
    }


def load_current_for_role(workspace: Path, role_family_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    roots = load_config(workspace / "careeros.yaml").roots
    active_path = roots.state_root / "lane-bases/active.json"
    if not active_path.is_file():
        return None
    entry = next((item for item in read_json(active_path).get("entries", []) if item.get("role_family_id") == role_family_id and item.get("status") == "ACCEPTED"), None)
    if entry is None:
        return None
    base = read_json(roots.state_root / entry["path"])
    status = effective_status(workspace, base["lane_base_id"])
    if not status["reuse_allowed"]:
        raise PermissionError(f"lane base {base['lane_base_id']} is stale and must be rebuilt before job tailoring")
    require_derivative_current(roots, "LANE_BASE_RESUME", base["lane_base_id"])
    storyline = read_json(roots.state_root / "lane-bases" / base["lane_base_id"] / "storyline.json")
    return base, storyline
