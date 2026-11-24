# Where job results come from

Career OS compares actual postings. Your assistant can read supported Greenhouse employer boards or bring in current postings from another allowed source. It must have access to the full employer description, not just a search snippet.

A posting needs an employer, title, source link, saved description, checked date and observed status. Required qualifications stay separate from preferences. The assistant reviews source wording before comparing the job with your profile. Missing requirements cannot be treated as a good match.

A search uses your experience, approved direction and preferences. Supported searches are bounded; they do not cover every employer or job board. A request for current jobs permits the relevant public read-only search, not unrelated personal-source access. Private career details stay out of outside search queries.

Previously seen jobs are compared with saved results so they are not called new every time. A changed or reposted job is shown as such. Old or unavailable details need checking; age alone does not prove that a role closed.

Ready Now results need current source details and a supported qualification match. Other jobs may be useful stretch or dream targets, with their gaps clearly explained. Closed or mismatched postings are left out with a reason. See [finding your next role](find-your-next-role.md).

## Assistant and developer tools

`workflow jobs --request <json> --approve-network` handles the supported board reader and reviewed catalogs. Live proposals require requirement review before ingestion. The original `discover-source`, `discover` and persistent opportunity registry remain available. No authenticated job-board API, scheduled alert or application submission is included.
