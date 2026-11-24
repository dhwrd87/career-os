# Approval boundaries

| Class | Default | Examples |
|---|---|---|
| `LOCAL_READ` | Allowed | Doctor, status, schema list, workspace verification |
| `LOCAL_DRAFT` | Allowed | Proposed onboarding answers, clarification drafts, recruiter-message draft |
| `LOCAL_GENERATE` | Allowed | Profile, role family proposal, qualification, resume candidate, packet |
| `CANONICAL_MUTATION` | Explicit approval | Commit proposed factual records or corrected career facts |
| `EXTERNAL_READ` | User-approved source access | Bounded Greenhouse GET and consented source enrichment; read-only, no candidate profile transmitted to a job board |
| `EXTERNAL_WRITE` | Not implemented; specific future approval | Submit application or send recruiter message |
| `PUBLIC_MUTATION` | Not implemented; specific future approval | Edit a public professional profile |
| `COMMITMENT` | Not implemented; specific future approval | Accept an offer or send compensation terms |

Ask immediately before the consequential operation, after showing what will change. Approval for a canonical commit does not authorize any external action.

Migration also requires explicit approval after a read-only plan, even though it is local. Verify the workspace after applying it.

When an unavailable external action is requested, offer the closest safe result: prepare the packet, draft the message, create a scheduling checklist, or draft the compensation response. Clearly report `External action: NOT PERFORMED`.
