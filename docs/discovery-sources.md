# Read-only job discovery

Career OS includes a bounded Greenhouse public-board adapter and a provider-neutral reviewed-catalog ingestion path. The adapter uses the documented public GET job-board endpoint; see the [Greenhouse Job Board API](https://docs.greenhouse.io/job-board). It has no credential or application-submission path.

```bash
careeros --workspace <path> discover-source --greenhouse-board <board-token> \
  --employer "Verified Employer Name" --query "Support" --limit 25 --approve-network
```

This performs one GET request, rejects redirects and oversized responses, strips HTML into retained source text, ignores prospect posts, and writes a source proposal. Limits are 1–100 selected postings, 8 MiB and a 20-second request timeout. It sends only a public board token and generic request headers; no candidate profile is transmitted.

A fetched description is not automatically a reviewed requirement model. Read the retained text, extract required/preferred requirements with source-grounded language, fill the proposed jobs' `requirements` arrays, and set `requirement_review_status` to `REVIEWED`. Then run:

```bash
careeros --workspace <path> discover --catalog <saved-proposal.json> --limit 25
```

The ingestion path blocks unreviewed provider proposals and empty requirements. An independently supplied empty requirement list is BORDERLINE rather than qualified. Persistent registry reconciliation classifies new, known, updated, reposted and already-applied roles before creating work. Qualification and packet freshness remain separate gates.

The local release check made one real read-only request against a public board, observed 770 provider posts and bounded selection to two. Only aggregate results were retained for release evidence; no real job descriptions are shipped as fixtures. This proves the observed adapter path at that time, not future source availability, every board, other providers or scheduled alerts. Synthetic tests cover parsing, consent, endpoint control, GET-only behavior and review boundaries.
