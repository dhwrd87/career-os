"""Consent-gated, read-only enrichment from linked public career sources.

Linked sources are discovery inputs only.  This module never writes canonical
records and never upgrades project, lab, coursework, or repository evidence to
professional experience.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import urllib.parse
import urllib.request
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

from careeros.core.io import atomic_write_json, read_json
from careeros.schemas.validation import SchemaRegistry
from careeros.workspace import require_current_workspace, schema_dir, utc_now


SUPPORTED_SOURCE_TYPES = ("LINKEDIN", "GITHUB", "PORTFOLIO")
APPROVAL_STATES = ("PENDING", "APPROVED", "DECLINED")
URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s|<>'\"]+", re.I)
MAX_CAPTURE_BYTES = 2 * 1024 * 1024


class _ReadableHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.links: list[str] = []
        self.json_ld: list[str] = []
        self._buffer: list[str] = []
        self._tag = ""
        self._script_type = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._tag = tag.casefold()
        values = dict(attrs)
        if self._tag == "script":
            self._script_type = str(values.get("type") or "").casefold()
        href = values.get("href")
        if href:
            self.links.append(href)
        if self._tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "article", "section", "br"}:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "script":
            if self._script_type == "application/ld+json" and self._buffer:
                self.json_ld.append("".join(self._buffer).strip())
            self._buffer = []
            self._script_type = ""
            self._tag = ""
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "article", "section"}:
            self._flush(prefix="- " if tag == "li" else "")
        self._tag = ""

    def handle_data(self, data: str) -> None:
        if self._tag in {"style", "noscript"}:
            return
        self._buffer.append(data)

    def _flush(self, prefix: str = "") -> None:
        text = re.sub(r"\s+", " ", "".join(self._buffer)).strip()
        if text:
            self.lines.append(prefix + text)
        self._buffer = []

    def finish(self) -> None:
        self._flush()


def _normalize_url(value: str) -> str:
    value = value.rstrip(".,);]")
    if value.casefold().startswith("www."):
        value = "https://" + value
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("linked career sources require an http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("linked career source URLs may not contain credentials")
    hostname = parsed.hostname.casefold()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise ValueError("local network hostnames are not valid linked career sources")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal and (literal.is_private or literal.is_loopback or literal.is_link_local or literal.is_reserved):
        raise ValueError("private or local network URLs are not valid linked career sources")
    return urllib.parse.urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path or "/", parsed.query, ""))


def classify_url(value: str) -> str:
    url = _normalize_url(value)
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").casefold()
    path = parsed.path.casefold()
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        if path.startswith("/in/") or path.startswith("/pub/"):
            return "LINKEDIN"
        raise ValueError("only candidate LinkedIn profile URLs are supported")
    if host == "github.com" or host.endswith(".github.com"):
        return "GITHUB"
    return "PORTFOLIO"


def detect_linked_sources(extractions: list[dict[str, Any]], *, timestamp: str | None = None) -> dict[str, Any]:
    """Detect career links without fetching them."""
    detected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for extraction in extractions:
        for unit in extraction.get("units", []):
            for match in URL_PATTERN.finditer(str(unit.get("text") or "")):
                try:
                    url = _normalize_url(match.group(0))
                    source_type = classify_url(url)
                except ValueError:
                    continue
                if url in seen:
                    continue
                seen.add(url)
                locator = ",".join(f"{key}={value}" for key, value in unit.get("locator", {}).items())
                detected.append({
                    "enrichment_source_id": f"linked-source:{uuid.uuid5(uuid.NAMESPACE_URL, url)}",
                    "source_type": source_type,
                    "source_location": url,
                    "detected_from": f"{unit.get('source_reference')}#{locator}",
                    "capture_time": None,
                    "source_hash": None,
                    "records_proposed": [],
                    "conflicts_found": [],
                    "evidence_blocks_enriched": [],
                    "candidate_approval_state": "PENDING",
                    "capture_status": "NOT_REQUESTED",
                    "failure": None,
                })
    now = utc_now(timestamp)
    return {
        "schema": "careeros.source-enrichment-manifest.v1",
        "schema_version": "1.0.0",
        "manifest_id": f"source-enrichment:{uuid.uuid5(uuid.NAMESPACE_URL, '|'.join(sorted(seen)) or 'none')}",
        "created_at": now,
        "updated_at": now,
        "approval_prompted_at": now if detected else None,
        "approval_decided_at": None,
        "sources": detected,
        "authorized_source_count": 0,
        "captured_source_count": 0,
        "canonical_mutation": False,
    }


def prepare_manifest(workspace: Path, extractions: list[dict[str, Any]], *, timestamp: str | None = None) -> dict[str, Any]:
    require_current_workspace(workspace)
    manifest = detect_linked_sources(extractions, timestamp=timestamp)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:source-enrichment-manifest:v1", manifest)
    atomic_write_json(workspace / "state/intake/source-enrichment-manifest.json", manifest)
    return manifest


def _http_get(url: str, *, accept: str) -> tuple[bytes, str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CareerOS-SourceEnrichment/1.0 (read-only; candidate-authorized)",
            "Accept": accept,
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # nosec - URL is consented and validated
        final_url = _normalize_url(response.geturl())
        body = response.read(MAX_CAPTURE_BYTES + 1)
        if len(body) > MAX_CAPTURE_BYTES:
            raise ValueError("linked source exceeds the 2 MiB capture limit")
        media_type = response.headers.get_content_type()
    return body, media_type, final_url


def _github_api_capture(url: str) -> dict[str, Any]:
    """Create one bounded capture from GitHub's public, read-only API."""
    parsed = urllib.parse.urlsplit(url)
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        raise ValueError("GitHub source requires a user or repository path")
    owner = urllib.parse.quote(parts[0], safe="")
    if len(parts) == 1:
        api_url = f"https://api.github.com/users/{owner}/repos?per_page=10&type=owner&sort=updated"
        body, _, _ = _http_get(api_url, accept="application/vnd.github+json")
        repositories = json.loads(body.decode("utf-8"))
    else:
        repository = urllib.parse.quote(parts[1], safe="")
        api_url = f"https://api.github.com/repos/{owner}/{repository}"
        body, _, _ = _http_get(api_url, accept="application/vnd.github+json")
        repositories = [json.loads(body.decode("utf-8"))]
    if not isinstance(repositories, list):
        raise ValueError("GitHub provider returned an unexpected repository payload")
    enriched: list[dict[str, Any]] = []
    for repository in repositories[:10]:
        if not isinstance(repository, dict):
            continue
        full_name = str(repository.get("full_name") or "")
        contents: list[dict[str, Any]] = []
        readme = ""
        if full_name:
            try:
                root_body, _, _ = _http_get(
                    f"https://api.github.com/repos/{full_name}/contents",
                    accept="application/vnd.github+json",
                )
                value = json.loads(root_body.decode("utf-8"))
                contents = value if isinstance(value, list) else []
            except Exception:
                contents = []
            try:
                readme_body, _, _ = _http_get(
                    f"https://api.github.com/repos/{full_name}/readme",
                    accept="application/vnd.github.raw+json",
                )
                readme = readme_body.decode("utf-8", errors="replace")[:12000]
            except Exception:
                readme = ""
        names = {str(item.get("name") or "").casefold() for item in contents if isinstance(item, dict)}
        enriched.append({
            "@type": "SoftwareSourceCode",
            "name": repository.get("name") or full_name,
            "description": repository.get("description"),
            "readme": readme,
            "programmingLanguage": [repository["language"]] if repository.get("language") else [],
            "dateModified": repository.get("pushed_at") or repository.get("updated_at"),
            "has_tests": any(
                name in {"test", "tests", "spec", "specs"} or name.startswith(("test_", "spec_"))
                for name in names
            ),
            "has_documentation": bool(readme) or any(name in names for name in {"docs", "documentation"}),
            "codeRepository": repository.get("html_url"),
            "homepage": repository.get("homepage"),
            "fork": bool(repository.get("fork")),
            "owner": repository.get("owner", {}).get("login") if isinstance(repository.get("owner"), dict) else owner,
        })
    capture = json.dumps({"@type": "Person", "login": parts[0], "repositories": enriched}, sort_keys=True).encode("utf-8")
    return {"body": capture, "media_type": "application/json", "final_url": url}


def _default_fetch(url: str) -> dict[str, Any]:
    if classify_url(url) == "GITHUB":
        return _github_api_capture(url)
    body, media_type, final_url = _http_get(
        url, accept="text/html,application/ld+json,application/json,text/plain;q=0.8",
    )
    return {"body": body, "media_type": media_type, "final_url": final_url}


def _fetch(fetcher: Callable[[str], Any] | None, url: str) -> tuple[bytes, str, str]:
    payload = (fetcher or _default_fetch)(url)
    if isinstance(payload, dict):
        body = payload.get("body", b"")
        media_type = str(payload.get("media_type") or "text/html")
        final_url = _normalize_url(str(payload.get("final_url") or url))
    else:
        body, media_type, final_url = payload, "text/html", url
    if isinstance(body, str):
        body = body.encode("utf-8")
    if not isinstance(body, bytes):
        raise TypeError("linked source fetcher must return bytes, text, or a response mapping")
    if len(body) > MAX_CAPTURE_BYTES:
        raise ValueError("linked source exceeds the 2 MiB capture limit")
    return body, media_type, final_url


def _json_ld_items(parser: _ReadableHTML) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in parser.json_ld:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        values = value if isinstance(value, list) else value.get("@graph", [value]) if isinstance(value, dict) else []
        result.extend(item for item in values if isinstance(item, dict))
    return result


def _name(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        return str(value.get("name") or "").strip() or None
    return None


def _date_range(item: dict[str, Any]) -> str:
    start = str(item.get("startDate") or item.get("start_date") or "").strip()
    end = str(item.get("endDate") or item.get("end_date") or "Present").strip()
    start_display = start[:4] if re.match(r"^(?:19|20)\d{2}", start) else start
    end_display = end[:4] if re.match(r"^(?:19|20)\d{2}", end) else end
    return f"{start_display} - {end_display}" if start else "Date not supplied"


def _unit(text: str, *, source: dict[str, Any], index: int, section: str | None = None) -> dict[str, Any]:
    item = {
        "locator": {"linked_item": index},
        "text": text,
        "source_reference": source["source_location"],
        "source_hash": source["source_hash"],
        "captured_at": source["capture_time"],
        "linked_source_type": source["source_type"],
    }
    if section:
        item["section_hint"] = section
    return item


def _linked_units(source: dict[str, Any], body: bytes, media_type: str) -> list[dict[str, Any]]:
    text = body.decode("utf-8", errors="replace")
    data: Any = None
    if "json" in media_type.casefold() or text.lstrip().startswith(("{", "[")):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
    parser = _ReadableHTML()
    if data is None:
        parser.feed(text)
        parser.finish()
        structured = _json_ld_items(parser)
    else:
        structured = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
    units: list[dict[str, Any]] = []

    if source["source_type"] == "LINKEDIN":
        persons = [item for item in structured if str(item.get("@type") or "").casefold() == "person"]
        person = persons[0] if persons else {}
        occupations = person.get("hasOccupation") or person.get("occupations") or []
        occupations = occupations if isinstance(occupations, list) else [occupations]
        if occupations:
            units.append(_unit("EXPERIENCE", source=source, index=len(units) + 1))
        for occupation in occupations:
            if not isinstance(occupation, dict):
                continue
            employer = _name(occupation.get("hiringOrganization") or occupation.get("worksFor") or occupation.get("employer")) or "Employer not supplied"
            title = _name(occupation) or str(occupation.get("jobTitle") or "Title not supplied")
            units.append(_unit(f"{employer} | {title} | {_date_range(occupation)}", source=source, index=len(units) + 1))
            if occupation.get("description"):
                units.append(_unit(f"- {occupation['description']}", source=source, index=len(units) + 1))
        education = person.get("alumniOf") or person.get("education") or []
        education = education if isinstance(education, list) else [education]
        if education:
            units.append(_unit("EDUCATION", source=source, index=len(units) + 1))
            for item in education:
                label = _name(item) or str(item)
                if label:
                    units.append(_unit(label, source=source, index=len(units) + 1))
        credentials = person.get("hasCredential") or person.get("credentials") or []
        credentials = credentials if isinstance(credentials, list) else [credentials]
        if credentials:
            units.append(_unit("CREDENTIALS", source=source, index=len(units) + 1))
            for item in credentials:
                if isinstance(item, dict):
                    label = _name(item) or "Credential"
                    issuer = _name(item.get("recognizedBy") or item.get("issuer")) or "Unknown issuer"
                    units.append(_unit(f"{label} | {issuer}", source=source, index=len(units) + 1))
        projects = person.get("subjectOf") or person.get("projects") or []
        projects = projects if isinstance(projects, list) else [projects]
        if projects:
            units.append(_unit("PROJECTS", source=source, index=len(units) + 1))
            for item in projects:
                if isinstance(item, dict):
                    units.append(_unit(_name(item) or "Project", source=source, index=len(units) + 1))
                    if item.get("description"):
                        units.append(_unit(f"- {item['description']}", source=source, index=len(units) + 1))
        volunteer = person.get("volunteerExperience") or []
        volunteer = volunteer if isinstance(volunteer, list) else [volunteer]
        if volunteer:
            units.append(_unit("PROJECTS", source=source, index=len(units) + 1))
            for item in volunteer:
                if isinstance(item, dict):
                    organization = _name(item.get("organization")) or "Volunteer organization"
                    role = _name(item) or "Volunteer"
                    units.append(_unit(f"Volunteer: {role} — {organization} | {_date_range(item)}", source=source, index=len(units) + 1))
                    if item.get("description"):
                        units.append(_unit(f"- {item['description']}", source=source, index=len(units) + 1))
        skills = person.get("knowsAbout") or person.get("skills") or []
        skills = skills if isinstance(skills, list) else [skills]
        skill_names = [name for value in skills if (name := _name(value))]
        if skill_names:
            units.extend([
                _unit("SKILLS", source=source, index=len(units) + 1),
                _unit(", ".join(skill_names), source=source, index=len(units) + 2),
            ])

    elif source["source_type"] == "GITHUB":
        repositories: list[dict[str, Any]] = []
        for item in structured:
            item_type = str(item.get("@type") or item.get("type") or "").casefold()
            if item_type in {"softwaresourcecode", "code", "repository"}:
                repositories.append(item)
            repositories.extend(child for child in item.get("repositories", []) if isinstance(child, dict))
        if repositories:
            units.append(_unit("PROJECTS", source=source, index=len(units) + 1))
        language_names: list[str] = []
        for repository in repositories[:20]:
            name = _name(repository) or str(repository.get("repository") or "Repository")
            activity = str(repository.get("dateModified") or repository.get("updated_at") or "").strip()
            header = f"{name} | {activity[:10]}" if activity else name
            units.append(_unit(header, source=source, index=len(units) + 1))
            description = str(repository.get("description") or repository.get("readme") or "").strip()
            if description:
                units.append(_unit(f"- {description}", source=source, index=len(units) + 1))
            artifacts = []
            if repository.get("tests") or repository.get("has_tests"):
                artifacts.append("tests")
            if repository.get("documentation") or repository.get("has_documentation"):
                artifacts.append("documentation")
            deployment = repository.get("codeRepository") or repository.get("homepage") or repository.get("deployment")
            if deployment:
                artifacts.append(f"live/code artifact: {deployment}")
            if artifacts:
                units.append(_unit(f"- Observable deliverables: {', '.join(artifacts)}", source=source, index=len(units) + 1))
            languages = repository.get("programmingLanguage") or repository.get("languages") or []
            languages = languages if isinstance(languages, list) else [languages]
            language_names.extend(name for value in languages if (name := _name(value)))
        if language_names:
            units.extend([
                _unit("SKILLS", source=source, index=len(units) + 1),
                _unit(", ".join(dict.fromkeys(language_names)), source=source, index=len(units) + 2),
            ])

    else:
        works: list[dict[str, Any]] = []
        credentials: list[dict[str, Any]] = []
        for item in structured:
            item_type = str(item.get("@type") or "").casefold()
            if item_type in {"creativework", "project", "case study", "softwaresourcecode"}:
                works.append(item)
            works.extend(child for child in item.get("projects", []) if isinstance(child, dict))
            credentials.extend(child for child in item.get("credentials", []) if isinstance(child, dict))
        if works:
            units.append(_unit("PROJECTS", source=source, index=len(units) + 1))
            for work in works[:20]:
                units.append(_unit(_name(work) or "Portfolio project", source=source, index=len(units) + 1))
                description = str(work.get("description") or "").strip()
                if description:
                    units.append(_unit(f"- {description}", source=source, index=len(units) + 1))
                artifact = work.get("url") or work.get("sameAs") or work.get("demo")
                if artifact:
                    units.append(_unit(f"- Work sample: {artifact}", source=source, index=len(units) + 1))
        if credentials:
            units.append(_unit("CREDENTIALS", source=source, index=len(units) + 1))
            for credential in credentials:
                units.append(_unit(f"{_name(credential) or 'Credential'} | {_name(credential.get('issuer')) or 'Unknown issuer'}", source=source, index=len(units) + 1))

    # Candidate-controlled exports and simple public pages often already use
    # resume-style headings; retain them as a conservative fallback.
    if not units and parser.lines:
        units = [_unit(line, source=source, index=index) for index, line in enumerate(parser.lines, 1)]
    return units


def capture_authorized_sources(
    workspace: Path, *, approved: bool, fetcher: Callable[[str], Any] | None = None,
    timestamp: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply one candidate decision and capture approved sources read-only."""
    require_current_workspace(workspace)
    manifest_path = workspace / "state/intake/source-enrichment-manifest.json"
    manifest = read_json(manifest_path)
    now = utc_now(timestamp)
    linked_extractions: list[dict[str, Any]] = []
    for source in manifest["sources"]:
        source["candidate_approval_state"] = "APPROVED" if approved else "DECLINED"
        if not approved:
            source["capture_status"] = "DECLINED"
            continue
        try:
            body, media_type, final_url = _fetch(fetcher, source["source_location"])
            if source["source_type"] in {"LINKEDIN", "GITHUB"} and classify_url(final_url) != source["source_type"]:
                raise ValueError("linked source redirected outside its approved provider boundary")
            source["source_location"] = final_url
            source["capture_time"] = now
            source["source_hash"] = hashlib.sha256(body).hexdigest()
            source["capture_status"] = "CAPTURED"
            source_dir = workspace / "sources/enrichment" / source["enrichment_source_id"].replace(":", "-")
            source_dir.mkdir(parents=True, exist_ok=True)
            extension = ".json" if "json" in media_type.casefold() else ".html" if "html" in media_type.casefold() else ".txt"
            capture = source_dir / f"capture{extension}"
            capture.write_bytes(body)
            units = _linked_units(source, body, media_type)
            extraction = {
                "schema": "careeros.source-extraction.v1", "schema_version": "1.0.0",
                "source_id": source["enrichment_source_id"], "media_type": media_type,
                "source_reference": source["source_location"], "source_sha256": source["source_hash"],
                "captured_at": now, "units": units, "canonical_mutation": False,
            }
            atomic_write_json(source_dir / "extraction.json", extraction)
            linked_extractions.append(extraction)
        except Exception as exc:  # captured source failures are visible and non-mutating
            source["capture_status"] = "FAILED"
            source["failure"] = {"type": exc.__class__.__name__, "message": str(exc)}
    manifest["approval_decided_at"] = now
    manifest["updated_at"] = now
    manifest["authorized_source_count"] = sum(item["candidate_approval_state"] == "APPROVED" for item in manifest["sources"])
    manifest["captured_source_count"] = sum(item["capture_status"] == "CAPTURED" for item in manifest["sources"])
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:source-enrichment-manifest:v1", manifest)
    atomic_write_json(manifest_path, manifest)
    return manifest, linked_extractions


def update_manifest_results(
    workspace: Path, *, proposed: dict[str, Any], conflicts: list[str],
    assessments: list[dict[str, Any]], timestamp: str | None = None,
) -> dict[str, Any]:
    manifest_path = workspace / "state/intake/source-enrichment-manifest.json"
    manifest = read_json(manifest_path)
    for source in manifest["sources"]:
        url = source["source_location"]
        records: list[dict[str, str]] = []
        evidence_ids: list[str] = []
        for kind in ("employment", "education", "credentials", "skills", "projects", "evidence"):
            for record in proposed.get(kind, []):
                provenance = record.get("source_provenance", [])
                if any(item.get("source_reference") == url for item in provenance):
                    record_id = str(record.get("local_id") or "")
                    records.append({"record_type": kind.upper(), "record_id": record_id})
                    if kind == "evidence":
                        evidence_ids.append(record_id)
        source["records_proposed"] = records
        source["conflicts_found"] = list(conflicts) if source["capture_status"] == "CAPTURED" else []
        assessed_ids = {assessment["evidence_id"] for assessment in assessments}
        source["evidence_blocks_enriched"] = list(dict.fromkeys([
            *evidence_ids,
            *(evidence_id for evidence_id in evidence_ids if evidence_id in assessed_ids),
        ]))
    manifest["updated_at"] = utc_now(timestamp)
    SchemaRegistry(schema_dir()).validate("urn:careeros:schema:source-enrichment-manifest:v1", manifest)
    atomic_write_json(manifest_path, manifest)
    return manifest
