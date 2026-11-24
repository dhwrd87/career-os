"""Portable source ingestion and consolidated Career OS intake compilation.

Everything produced here is proposal material.  The module deliberately stops
before the existing onboarding commit boundary.
"""

from __future__ import annotations

import copy
import hashlib
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree

from careeros.core.io import atomic_write_json, read_json, sha256_value
from careeros.core.errors import SourceEnrichmentApprovalRequiredError
from careeros.evidence_expansion import (
    assess_evidence_depth,
    decompose_source_bullet,
    evidence_block_from_record,
    generate_targeted_questions,
)
from careeros.schemas.validation import SchemaRegistry
from careeros.source_enrichment import capture_authorized_sources, prepare_manifest, update_manifest_results
from careeros.workspace import require_current_workspace, schema_dir, utc_now


SECTION_ALIASES = {
    "SUMMARY": "summary", "PROFILE": "summary", "OBJECTIVE": "summary",
    "EXPERIENCE": "employment", "EMPLOYMENT": "employment", "WORK EXPERIENCE": "employment",
    "EDUCATION": "education", "CREDENTIALS": "credentials", "CERTIFICATIONS": "credentials",
    "CERTIFICATES": "credentials", "SKILLS": "skills", "TECHNICAL SKILLS": "skills",
    "PROJECTS": "projects", "PORTFOLIO": "projects", "LANGUAGES": "languages",
}
DATE_RANGE = re.compile(
    r"(?P<start_month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)?\s*"
    r"(?P<start_year>(?:19|20)\d{2})\s*(?:-|–|—|to)\s*"
    r"(?:(?P<end_month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)?\s*"
    r"(?P<end_year>(?:19|20)\d{2})|(?P<present>Present|Current))",
    re.I,
)
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")
URL = re.compile(r"(?:https?://|www\.)[^\s|]+", re.I)


def _source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pdf_units(path: Path) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - exercised by Doctor in core-only installs
        raise RuntimeError("PDF ingestion requires the 'resume' extra (pypdf)") from exc
    units: list[dict[str, Any]] = []
    for page_number, page in enumerate(PdfReader(str(path)).pages, 1):
        for line_number, text in enumerate((page.extract_text() or "").splitlines(), 1):
            if text.strip():
                units.append({"locator": {"page": page_number, "line": line_number}, "text": text.strip()})
    return units


def _docx_units(path: Path) -> list[dict[str, Any]]:
    # OOXML is parsed with the standard library so DOCX ingestion has no mandatory
    # runtime dependency.  Tables are included in document order as text nodes.
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    units: list[dict[str, Any]] = []
    for index, paragraph in enumerate(root.findall(".//w:p", namespace), 1):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
        if text:
            units.append({"locator": {"paragraph": index}, "text": text})
    return units


def _text_units(path: Path) -> list[dict[str, Any]]:
    return [
        {"locator": {"line": index}, "text": line.strip().lstrip("#").strip()}
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if line.strip().lstrip("#").strip()
    ]


def ingest_source(workspace: Path, path: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    """Copy a user source into the workspace and extract text with provenance."""
    require_current_workspace(workspace)
    path = path.resolve()
    suffix = path.suffix.casefold()
    if suffix not in {".pdf", ".docx", ".txt", ".md", ".markdown"}:
        raise ValueError(f"unsupported source type: {suffix or '<none>'}")
    digest = _source_hash(path)
    source_id = f"source:{digest[:16]}"
    target_root = workspace.resolve() / "sources" / "imports" / source_id.replace(":", "-")
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / ("resume" + suffix)
    if not target.exists():
        shutil.copy2(path, target)
    units = _pdf_units(target) if suffix == ".pdf" else _docx_units(target) if suffix == ".docx" else _text_units(target)
    relative = target.relative_to(workspace.resolve()).as_posix()
    for unit in units:
        unit["source_reference"] = relative
        unit["source_hash"] = digest
        unit["captured_at"] = utc_now(timestamp)
    result = {
        "schema": "careeros.source-extraction.v1", "schema_version": "1.0.0",
        "source_id": source_id, "media_type": suffix.lstrip("."), "source_reference": relative,
        "source_sha256": digest, "captured_at": utc_now(timestamp), "units": units,
        "canonical_mutation": False,
    }
    atomic_write_json(target_root / "extraction.json", result)
    return result


def _sectioned(units: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {"header": []}
    section = "header"
    for unit in units:
        heading = re.sub(r"[^A-Z &/]", "", unit["text"].upper()).strip()
        if heading in SECTION_ALIASES:
            section = SECTION_ALIASES[heading]
            result.setdefault(section, [])
            continue
        item = dict(unit)
        item["section"] = section
        result.setdefault(section, []).append(item)
    return result


def _slug(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return token[:48] or "record"


def _date_fields(text: str) -> dict[str, Any] | None:
    match = DATE_RANGE.search(text)
    if not match:
        return None
    return {
        "start_month": match.group("start_month"), "start_year": int(match.group("start_year")),
        "end_month": match.group("end_month"),
        "end_year": "PRESENT" if match.group("present") else int(match.group("end_year")),
        "date_precision": "MONTH" if match.group("start_month") else "YEAR",
    }


def _line_provenance(unit: dict[str, Any]) -> str:
    locator = ",".join(f"{key}={value}" for key, value in unit["locator"].items())
    return f"{unit['source_reference']}#{locator}"


def _record_provenance(unit: dict[str, Any], local_id: str) -> list[dict[str, Any]]:
    source_type = "PUBLIC_SOURCE" if unit.get("linked_source_type") else "DOCUMENT"
    return [{
        "source_id": f"source:{str(unit.get('source_hash') or '')[:16]}",
        "source_type": source_type,
        "source_reference": str(unit.get("source_reference") or "unknown"),
        "source_record_id": local_id,
        "field": None,
        "source_hash": str(unit.get("source_hash") or sha256_value(unit.get("text"))),
        "captured_at": str(unit.get("captured_at") or utc_now()),
    }]


def _question(question_id: str, section: str, prompt: str, target_fields: list[str], *,
              career_value: int, deficiency: int, effort: int, privacy: int = 0,
              required: bool = False, why: str = "") -> dict[str, Any]:
    score = career_value * 3 + deficiency * 3 + 2 + 2 - effort - privacy
    return {
        "schema": "careeros.question-value.v1", "schema_version": "1.0.0",
        "question_id": question_id, "section": section, "prompt": prompt,
        "target_fields": target_fields, "required": required, "allows_unknown": True,
        "value": {
            "career_value": career_value, "target_lane_relevance": 2,
            "evidence_deficiency": deficiency, "answerability": 2,
            "downstream_reuse": 2, "user_effort": effort, "privacy_sensitivity": privacy,
            "score": score,
        },
        "why_asked": why,
    }


def _parse_source(extractions: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    units = [unit for extraction in extractions for unit in extraction["units"]]
    sections = _sectioned(units)
    all_text = "\n".join(unit["text"] for unit in units)
    header = sections.get("header", [])
    public_name = next((item["text"] for item in header if not EMAIL.search(item["text"]) and not PHONE.search(item["text"]) and not URL.search(item["text"])), "")
    email = (EMAIL.search(all_text).group(0) if EMAIL.search(all_text) else None)
    phone = (PHONE.search(all_text).group(0) if PHONE.search(all_text) else None)
    urls = list(dict.fromkeys(match.group(0) for match in URL.finditer(all_text)))
    proposed: dict[str, Any] = {
        "schema": "careeros.onboarding-input.v1", "schema_version": "1.0.0",
        "privacy_consent": False, "review_confirmed": False,
        "candidate": {
            "local_id": "candidate", "public_name": public_name, "legal_name": None,
            "location": None, "contact": {"email": email, "phone": phone, "urls": urls},
            "work_authorization": None, "visibility": "INTERNAL", "confidence": "MEDIUM",
            "source_provenance": _record_provenance(header[0], "candidate") if header else [],
        },
        "employment": [], "education": [], "credentials": [], "skills": [],
        "evidence": [], "projects": [],
        "preferences": {
            "local_id": "preferences", "target_role_family_ids": [], "target_industries": [],
            "work_modes": [], "location_preferences": [], "compensation": None,
            "travel_preference": None, "schedule_preferences": [], "career_change_intent": None,
            "constraints": [], "career_gaps": [], "visibility": "INTERNAL", "confidence": "MEDIUM",
        },
        "role_intents": [],
    }
    original_claims: list[dict[str, Any]] = []
    contradictions: list[str] = []

    # Employment headers use a candidate-friendly, widely exportable format:
    # Employer | Actual title | dates | optional location.  Lines with only a
    # date but no delimiter remain unparsed and are surfaced for confirmation.
    current_job: dict[str, Any] | None = None
    for unit in sections.get("employment", []):
        text = unit["text"].lstrip("•-* ").strip()
        dates = _date_fields(text)
        parts = [part.strip() for part in re.split(r"\s*[|]\s*", text)]
        if dates and len(parts) >= 2 and not unit["text"].lstrip().startswith(("-", "•", "*")):
            clean = [DATE_RANGE.sub("", part).strip(" ,-–—") for part in parts]
            clean = [part for part in clean if part]
            employer = clean[0] if clean else ""
            title = clean[1] if len(clean) > 1 else ""
            current_job = {
                "local_id": f"employment-{len(proposed['employment']) + 1}-{_slug(employer)}",
                "employer": employer, "actual_title": title, "normalized_title": None,
                "public_title": None, "employment_type": "UNKNOWN", "location": clean[2] if len(clean) > 2 else None,
                **dates, "role_context": None, "evidence_ids": [], "claim_boundaries": [],
                "visibility": "INTERNAL", "confidence": "MEDIUM",
            }
            current_job["source_provenance"] = _record_provenance(unit, current_job["local_id"])
            proposed["employment"].append(current_job)
        elif current_job and text:
            evidence_local = f"evidence-employment-{len(proposed['evidence']) + 1}"
            decomposition = decompose_source_bullet(text, source_ref=_line_provenance(unit))
            evidence = {
                "local_id": evidence_local, "evidence_type": "EMPLOYMENT", "summary": text,
                "context": None, "ownership": None,
                "actions": [claim["value"] for claim in decomposition["atomic_claims"] if claim["component"] in {"ACTION", "OBJECT"}],
                "tools_methods": [claim["value"] for claim in decomposition["atomic_claims"] if claim["component"] == "TOOL"],
                "stakeholders": [claim["value"] for claim in decomposition["atomic_claims"] if claim["component"] == "STAKEHOLDER"],
                "outcomes": [claim["value"] for claim in decomposition["atomic_claims"] if claim["component"] == "RESULT"],
                "skill_ids": [], "employment_ids": [f"ref:{current_job['local_id']}"], "project_ids": [],
                "metric_boundaries": ["Source numbers require review."] if any(claim["component"] == "METRIC" for claim in decomposition["atomic_claims"]) else [],
                "claim_boundaries": ["Imported source wording; proposed until approved."],
                "visibility": "INTERNAL", "verification_state": "UNVERIFIED", "confidence": "LOW",
                "source_original_wording": [text], "source_reference": _line_provenance(unit),
            }
            evidence["source_provenance"] = _record_provenance(unit, evidence_local)
            proposed["evidence"].append(evidence)
            current_job["evidence_ids"].append(f"ref:{evidence_local}")
            original_claims.append(decomposition)

    for unit in sections.get("education", []):
        text = unit["text"].strip()
        if not text:
            continue
        parts = [part.strip() for part in text.split("|")]
        years = re.findall(r"(?:19|20)\d{2}", text)
        local_id = f"education-{len(proposed['education']) + 1}"
        proposed["education"].append({
            "local_id": local_id,
            "institution": parts[0], "program": parts[1] if len(parts) > 1 else "Education",
            "field_of_study": parts[2] if len(parts) > 2 and not re.search(r"\d", parts[2]) else None,
            "completion_status": "UNKNOWN", "start_year": None,
            "end_year": int(years[-1]) if years else None,
            "claim_boundaries": ["Completion state requires confirmation."],
            "visibility": "INTERNAL", "confidence": "MEDIUM",
            "source_provenance": _record_provenance(unit, local_id),
        })

    for unit in sections.get("credentials", []):
        text = unit["text"].lstrip("•-* ").strip()
        parts = [part.strip() for part in text.split("|")]
        local_id = f"credential-{len(proposed['credentials']) + 1}"
        proposed["credentials"].append({
            "local_id": local_id, "title": parts[0],
            "issuer": parts[1] if len(parts) > 1 else "Unknown issuer", "platform": None,
            "credential_state": "UNKNOWN", "issued_date": None, "expiration_date": None,
            "credential_identifier": None, "credential_url": None, "capability_ids": [],
            "claim_boundaries": ["Status and issuer require confirmation."],
            "visibility": "INTERNAL", "confidence": "LOW", "verification_state": "UNVERIFIED",
            "source_provenance": _record_provenance(unit, local_id),
        })

    skill_names: list[str] = []
    for unit in sections.get("skills", []) + sections.get("languages", []):
        for name in re.split(r"[,|•;]", unit["text"]):
            name = name.strip()
            if name and name.casefold() not in {item.casefold() for item in skill_names}:
                skill_names.append(name)
                proposed["skills"].append({
                    "local_id": f"skill-{_slug(name)}", "name": name,
                    "category": "Languages" if unit["section"] == "languages" else "Unclassified",
                    "aliases": [], "proficiency": "UNKNOWN", "most_recent_use": None,
                    "contexts": ["SOURCE_MENTION"], "evidence_ids": [],
                    "claim_boundaries": ["Source mention does not establish proficiency."],
                    "visibility": "INTERNAL", "confidence": "LOW",
                    "source_provenance": _record_provenance(unit, f"skill-{_slug(name)}"),
                })

    current_project: dict[str, Any] | None = None
    for unit in sections.get("projects", []):
        text = unit["text"].lstrip("•-* ").strip()
        bullet = unit["text"].lstrip().startswith(("-", "•", "*"))
        if not bullet:
            parts = [part.strip() for part in text.split("|")]
            current_project = {
                "local_id": f"project-{len(proposed['projects']) + 1}-{_slug(parts[0])}",
                "name": parts[0], "purpose": None, "date_range": parts[1] if len(parts) > 1 else None,
                "contribution": "AMBIGUOUS", "technologies": [], "skill_ids": [], "evidence_ids": [],
                "professional_equivalence_boundary": "Project evidence is not employment experience.",
                "claim_boundaries": ["Contribution requires confirmation."],
                "visibility": "INTERNAL", "confidence": "LOW",
            }
            current_project["source_provenance"] = _record_provenance(unit, current_project["local_id"])
            proposed["projects"].append(current_project)
        elif current_project:
            evidence_local = f"evidence-project-{len(proposed['evidence']) + 1}"
            decomposition = decompose_source_bullet(text, source_ref=_line_provenance(unit))
            evidence_type = "VOLUNTEER" if current_project["name"].casefold().startswith("volunteer:") else "PROJECT"
            evidence = {
                "local_id": evidence_local, "evidence_type": evidence_type, "summary": text,
                "context": None, "ownership": None,
                "actions": [claim["value"] for claim in decomposition["atomic_claims"] if claim["component"] in {"ACTION", "OBJECT"}],
                "tools_methods": [claim["value"] for claim in decomposition["atomic_claims"] if claim["component"] == "TOOL"],
                "stakeholders": [claim["value"] for claim in decomposition["atomic_claims"] if claim["component"] == "STAKEHOLDER"],
                "outcomes": [claim["value"] for claim in decomposition["atomic_claims"] if claim["component"] == "RESULT"],
                "skill_ids": [], "employment_ids": [], "project_ids": [f"ref:{current_project['local_id']}"],
                "metric_boundaries": ["Source numbers require review."] if any(claim["component"] == "METRIC" for claim in decomposition["atomic_claims"]) else [],
                "claim_boundaries": ["Imported project claim; professional equivalence prohibited."],
                "visibility": "INTERNAL", "verification_state": "UNVERIFIED", "confidence": "LOW",
                "source_original_wording": [text], "source_reference": _line_provenance(unit),
            }
            evidence["source_provenance"] = _record_provenance(unit, evidence_local)
            proposed["evidence"].append(evidence)
            current_project["evidence_ids"].append(f"ref:{evidence_local}")
            original_claims.append(decomposition)
    deduplicated_employment: list[dict[str, Any]] = []
    seen_employment: set[tuple[Any, ...]] = set()
    retained_by_signature: dict[tuple[Any, ...], str] = {}
    employment_ref_remap: dict[str, str] = {}
    dates_by_role: dict[tuple[str, str], set[tuple[Any, Any]]] = {}
    for item in proposed["employment"]:
        role_key = (item["employer"].casefold(), item["actual_title"].casefold())
        dates = (item.get("start_year"), item.get("end_year"))
        dates_by_role.setdefault(role_key, set()).add(dates)
        signature = (*role_key, *dates)
        if signature not in seen_employment:
            deduplicated_employment.append(item)
            seen_employment.add(signature)
            retained_by_signature[signature] = item["local_id"]
        else:
            employment_ref_remap[f"ref:{item['local_id']}"] = f"ref:{retained_by_signature[signature]}"
    proposed["employment"] = deduplicated_employment
    for evidence in proposed["evidence"]:
        evidence["employment_ids"] = [employment_ref_remap.get(value, value) for value in evidence.get("employment_ids", [])]
    for role_key, dates in dates_by_role.items():
        if len(dates) > 1:
            contradictions.append(f"Conflicting date ranges for {role_key[0]} / {role_key[1]}")

    # Multiple authorized sources may describe the same project.  Preserve all
    # evidence and provenance while keeping one proposed project authority.
    deduplicated_projects: list[dict[str, Any]] = []
    retained_projects: dict[str, dict[str, Any]] = {}
    project_ref_remap: dict[str, str] = {}
    for item in proposed["projects"]:
        key = item["name"].casefold().strip()
        if key not in retained_projects:
            retained_projects[key] = item
            deduplicated_projects.append(item)
            continue
        retained = retained_projects[key]
        if item.get("date_range") and retained.get("date_range") and item["date_range"] != retained["date_range"]:
            contradictions.append(f"Conflicting project dates for {item['name']}")
        retained["source_provenance"].extend(
            value for value in item.get("source_provenance", []) if value not in retained["source_provenance"]
        )
        retained["evidence_ids"].extend(
            value for value in item.get("evidence_ids", []) if value not in retained["evidence_ids"]
        )
        project_ref_remap[f"ref:{item['local_id']}"] = f"ref:{retained['local_id']}"
    proposed["projects"] = deduplicated_projects
    for evidence in proposed["evidence"]:
        evidence["project_ids"] = [project_ref_remap.get(value, value) for value in evidence.get("project_ids", [])]

    deduplicated_evidence: list[dict[str, Any]] = []
    seen_evidence: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()
    for item in proposed["evidence"]:
        signature = (
            item["summary"].casefold(), tuple(item.get("employment_ids", [])), tuple(item.get("project_ids", [])),
        )
        if signature not in seen_evidence:
            deduplicated_evidence.append(item)
            seen_evidence.add(signature)
    proposed["evidence"] = deduplicated_evidence

    # A linked-source skill mention becomes evidence-linked familiarity, never
    # inferred proficiency.  Contribution and proficiency still require review.
    for skill in proposed["skills"]:
        public_sources = {
            item["source_reference"] for item in skill.get("source_provenance", [])
            if item.get("source_type") == "PUBLIC_SOURCE"
        }
        if not public_sources:
            continue
        matches = [
            evidence for evidence in proposed["evidence"]
            if public_sources.intersection(
                item["source_reference"] for item in evidence.get("source_provenance", [])
                if item.get("source_type") == "PUBLIC_SOURCE"
            )
        ]
        skill["evidence_ids"] = [f"ref:{item['local_id']}" for item in matches]
        for evidence in matches:
            ref = f"ref:{skill['local_id']}"
            if ref not in evidence["skill_ids"]:
                evidence["skill_ids"].append(ref)
    return proposed, original_claims, contradictions


def prepare_source_stage(workspace: Path, source_paths: list[Path], *, mode: str = "FAST",
                         timestamp: str | None = None) -> dict[str, Any]:
    """Ingest local sources and detect links without performing network reads."""
    require_current_workspace(workspace)
    mode = mode.upper()
    if mode not in {"FAST", "DEEP"}:
        raise ValueError("intake mode must be FAST or DEEP")
    extractions = [ingest_source(workspace, path, timestamp=timestamp) for path in source_paths]
    manifest = prepare_manifest(workspace, extractions, timestamp=timestamp)
    plan = {
        "schema": "careeros.intake-source-plan.v1", "mode": mode,
        "source_extractions": [
            str((workspace / item["source_reference"]).parent.joinpath("extraction.json").relative_to(workspace))
            for item in extractions
        ],
        "created_at": utc_now(timestamp), "canonical_mutation": False,
    }
    atomic_write_json(workspace / "state/intake/source-plan.json", plan)
    return manifest


def _depth_after_enrichment(proposed: dict[str, Any], *, timestamp: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in proposed.get("evidence", []):
        group = (item.get("employment_ids") or item.get("project_ids") or [item["local_id"]])[0]
        record = copy.deepcopy(item)
        record["record_id"] = record["local_id"]
        record["provenance"] = copy.deepcopy(record.get("source_provenance", []))
        block = evidence_block_from_record(record, timestamp=timestamp)
        if group not in grouped:
            grouped[group] = block
            continue
        aggregate = grouped[group]
        for field in ("actions", "tools_methods", "stakeholders", "outcomes", "deliverables", "artifacts", "source_refs", "provenance", "source_original_wording"):
            aggregate[field].extend(value for value in block.get(field, []) if value not in aggregate[field])
        aggregate["summary"] = " | ".join(dict.fromkeys(filter(None, [aggregate.get("summary"), block.get("summary")])))
    assessments = [assess_evidence_depth(block, timestamp=timestamp) for block in grouped.values()]
    questions: list[dict[str, Any]] = []
    for block, assessment in zip(grouped.values(), assessments):
        questions.extend(generate_targeted_questions(block, assessment, max_questions=4))
    priority = {"HIGH_VALUE": 0, "MEDIUM_VALUE": 1, "OPTIONAL": 2}
    questions.sort(key=lambda item: (priority.get(item.get("priority"), 9), item["question_id"]))
    return assessments, questions


def compile_prepared_intake(
    workspace: Path, *, approved_linked_sources: bool,
    fetcher: Callable[[str], Any] | None = None, timestamp: str | None = None,
) -> dict[str, Any]:
    """Compile only after the candidate's single linked-source decision."""
    require_current_workspace(workspace)
    plan = read_json(workspace / "state/intake/source-plan.json")
    extractions = [read_json(workspace / path) for path in plan["source_extractions"]]
    manifest, linked = capture_authorized_sources(
        workspace, approved=approved_linked_sources, fetcher=fetcher, timestamp=timestamp,
    )
    all_extractions = [*extractions, *linked]
    proposed, claims, contradictions = _parse_source(all_extractions)
    assessments, evidence_questions = _depth_after_enrichment(proposed, timestamp=timestamp)
    mode = plan["mode"]
    has_employment = bool(proposed["employment"])
    has_projects = bool(proposed["projects"])
    has_skills = bool(proposed["skills"])
    questions = [
        _question("intake.identity", "identity_work_eligibility_contact", "Confirm or correct your name, contact details, location, and work authorization. Mark anything unknown.", ["candidate"], career_value=3, deficiency=2, effort=1, privacy=2, required=True, why="Required identity and eligibility facts are not inferred."),
        _question("intake.goals", "career_goals_constraints", "What roles or kinds of work interest you now, and what location, work-mode, schedule, travel, compensation, or other constraints matter?", ["preferences", "role_intents"], career_value=3, deficiency=3, effort=2, privacy=1, required=True, why="One answer guides lanes, qualification, and resume strategy."),
        _question("intake.chronology", "employment_chronology_titles", "Review the pre-filled employers, actual titles, and dates. Correct omissions, overlaps, part-time/concurrent work, or unknown dates; do not rewrite bullets.", ["employment"], career_value=3, deficiency=2 if has_employment else 3, effort=2, required=True, why="Chronology is a consequential truth boundary."),
        _question("intake.role_depth", "role_depth_achievements", "For each recent or target-relevant role, add only what is missing: what you owned, who you supported, recurring work, deliverables, outcomes, scale, leadership, or escalations. Unknown is acceptable.", ["evidence"], career_value=3, deficiency=3, effort=3, why="Richer evidence improves resumes and interviews without polishing facts."),
        _question("intake.tools", "tools_skills", "Confirm where and how you used the listed tools and skills (professional, project, lab, coursework, or familiarity). Add important missing ones and mark proficiency unknown when needed.", ["skills", "evidence"], career_value=3, deficiency=2 if has_skills else 3, effort=2, why="A source mention alone does not establish skill context or proficiency."),
        _question("intake.education", "education_credentials", "Confirm each education and credential item, including status, expected/completed date, issuer, expiration, and whether it may appear publicly.", ["education", "credentials"], career_value=2, deficiency=3, effort=2, privacy=1, why="Completion and verification states must not be assumed."),
        _question("intake.projects", "projects_portfolio", "For each useful project, lab, portfolio item, or volunteer effort, confirm the objective, your contribution, tools, deliverables/results, completion state, and public-use boundary.", ["projects", "evidence"], career_value=3, deficiency=2 if has_projects else 3, effort=2, why="Project evidence must remain distinct from employment."),
        _question("intake.privacy", "privacy_public_use", "Set public-use visibility for roles, projects, credentials, and evidence, especially confidential client or employer material.", ["visibility"], career_value=3, deficiency=3, effort=1, privacy=3, required=True, why="Career OS never infers permission to publish."),
        _question("intake.metrics", "optional_metrics_scale", "Optional: add defensible counts, frequency, team/user scope, turnaround, accuracy, or other scale. Approximate and unknown are both acceptable; identify the source when possible.", ["evidence.metrics"], career_value=2, deficiency=2, effort=3, privacy=1, why="Scale can improve outputs, but unsupported numbers are prohibited."),
    ]
    if manifest["captured_source_count"]:
        questions = [item for item in questions if item["question_id"] not in {"intake.tools", "intake.projects"}]
        questions.append(_question(
            "intake.linked_technical_evidence", "tools_skills_projects_portfolio",
            "Review the pre-filled tools, skills, repositories, projects, work samples, and live artifacts together. Confirm your contribution and skill context, correct anything that is not yours, and set public-use boundaries; unknown is acceptable.",
            ["skills", "projects", "evidence"], career_value=3, deficiency=2, effort=2, privacy=2,
            why="Authorized linked evidence pre-fills technical detail, so contribution, proficiency, and privacy can be confirmed once.",
        ))
    if mode == "DEEP":
        questions.extend([
            _question("intake.stories", "interview_story_material", "Which examples best show problem solving, communication, leadership, conflict handling, troubleshooting, or process improvement? Supply facts only.", ["evidence"], career_value=2, deficiency=2, effort=3, why="Deep mode prepares reusable interview evidence."),
            _question("intake.artifacts", "evidence_artifacts", "Which work samples, certificates, reports, links, or portfolio artifacts can support important claims, and what access or confidentiality rules apply?", ["evidence.source_refs"], career_value=2, deficiency=2, effort=2, privacy=2, why="Artifact links strengthen verification and provenance."),
        ])
    questions.sort(key=lambda item: (-item["value"]["score"], item["question_id"]))
    compiled = {
        "schema": "careeros.career-intake.v1", "schema_version": "1.0.0",
        "intake_id": f"intake:{uuid.uuid5(uuid.NAMESPACE_URL, sha256_value([item['source_sha256'] for item in all_extractions]))}",
        "mode": mode, "state": "AWAITING_COMPLETION", "created_at": utc_now(timestamp),
        "sources": [{key: item[key] for key in ("source_id", "source_reference", "source_sha256", "media_type")} for item in all_extractions],
        "prefilled_onboarding": proposed, "source_claims": claims, "contradictions": contradictions,
        "questions": questions, "question_count": len(questions), "exception_questions": [],
        "inference_policy": {
            "auto_accepted": ["source structure", "explicit dates", "exact names/titles", "source-linked tool mentions"],
            "confirmation_required": ["scale", "responsibility", "metrics", "outcomes", "proficiency", "privacy", "professional equivalence"],
        },
        "source_enrichment_manifest": "state/intake/source-enrichment-manifest.json",
        "evidence_depth_assessments": assessments,
        "evidence_expansion_questions": evidence_questions,
        "evidence_expansion_question_count": len(evidence_questions),
        "canonical_mutation": False,
    }
    manifest = update_manifest_results(
        workspace, proposed=proposed, conflicts=contradictions,
        assessments=assessments, timestamp=timestamp,
    )
    compiled["linked_source_summary"] = {
        "detected": len(manifest["sources"]),
        "authorized": manifest["authorized_source_count"],
        "captured": manifest["captured_source_count"],
    }
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:career-intake:v1", compiled)
    target = workspace / "state" / "intake" / "career-intake.json"
    atomic_write_json(target, compiled)
    return compiled


def compile_intake(
    workspace: Path, source_paths: list[Path], *, mode: str = "FAST",
    linked_source_decision: bool | None = None,
    fetcher: Callable[[str], Any] | None = None, timestamp: str | None = None,
) -> dict[str, Any]:
    """Convenience entrypoint; linked sources require an explicit decision."""
    manifest = prepare_source_stage(workspace, source_paths, mode=mode, timestamp=timestamp)
    if manifest["sources"] and linked_source_decision is None:
        raise SourceEnrichmentApprovalRequiredError(
            "linked career sources were detected; approve or decline one read-only enrichment pass",
            context={
                "manifest": "state/intake/source-enrichment-manifest.json",
                "sources": [
                    {"source_type": item["source_type"], "source_location": item["source_location"]}
                    for item in manifest["sources"]
                ],
            },
        )
    return compile_prepared_intake(
        workspace, approved_linked_sources=bool(linked_source_decision),
        fetcher=fetcher, timestamp=timestamp,
    )


def apply_completion(workspace: Path, answers_path: Path, *, timestamp: str | None = None) -> dict[str, Any]:
    """Merge agent-structured candidate answers and emit a commit-ready proposal source.

    The answers document is a workspace-local transport contract.  Candidate UX
    remains ordinary prose; the skill maps confirmed answers into these fields.
    """
    require_current_workspace(workspace)
    path = workspace / "state" / "intake" / "career-intake.json"
    intake = read_json(path)
    answers = read_json(answers_path)
    result = copy.deepcopy(intake["prefilled_onboarding"])
    replacements = answers.get("confirmed_onboarding", {})
    for key in ("candidate", "employment", "education", "credentials", "skills", "evidence", "projects", "preferences", "role_intents"):
        if key in replacements:
            result[key] = replacements[key]
    result["privacy_consent"] = answers.get("privacy_consent") is True
    result["review_confirmed"] = answers.get("review_confirmed") is True
    unresolved: list[dict[str, Any]] = []
    resolved_conflicts = set(answers.get("resolved_source_conflicts", []))
    for conflict in intake.get("contradictions", []):
        if conflict not in resolved_conflicts:
            unresolved.append({"issue": "SOURCE_CONFLICT", "detail": conflict, "required": True})
    if not result["candidate"].get("public_name"):
        unresolved.append({"issue": "MISSING_PUBLIC_NAME", "required": True})
    if not result["privacy_consent"]:
        unresolved.append({"issue": "PRIVACY_CONSENT_REQUIRED", "required": True})
    if not result["review_confirmed"]:
        unresolved.append({"issue": "REVIEW_CONFIRMATION_REQUIRED", "required": True})
    if any(item.get("completion_status") in {None, "UNKNOWN"} for item in result["education"]):
        unresolved.append({"issue": "EDUCATION_STATUS_UNRESOLVED", "required": True})
    if any(item.get("credential_state") in {None, "UNKNOWN"} for item in result["credentials"]):
        unresolved.append({"issue": "CREDENTIAL_STATUS_UNRESOLVED", "required": True})
    if any(item.get("contribution") in {None, "", "AMBIGUOUS"} for item in result["projects"]):
        unresolved.append({"issue": "PROJECT_CONTRIBUTION_UNRESOLVED", "required": True})
    intake["exception_questions"] = unresolved[:5]
    intake["state"] = "EXCEPTION_CLARIFICATION" if unresolved else "COMMIT_PREVIEW_READY"
    intake["completed_at"] = utc_now(timestamp)
    target = workspace / "sources" / "career-intake" / "completed-onboarding-input.json"
    atomic_write_json(target, result)
    intake["completed_source"] = target.relative_to(workspace).as_posix()
    atomic_write_json(path, intake)
    return {"intake": intake, "onboarding_input": result, "output": str(target), "canonical_mutation": False}


def review_preview(workspace: Path) -> dict[str, Any]:
    intake = read_json(workspace / "state" / "intake" / "career-intake.json")
    onboarding_input = read_json(workspace / intake["completed_source"])
    counts = {key: len(onboarding_input.get(key, [])) for key in ("employment", "education", "credentials", "skills", "evidence", "projects", "role_intents")}
    return {
        "schema": "careeros.intake-commit-preview.v1", "intake_id": intake["intake_id"],
        "state": intake["state"], "record_counts": counts,
        "source_count": len(intake["sources"]), "exception_count": len(intake["exception_questions"]),
        "requires_explicit_approval": True, "canonical_mutation": False,
    }
