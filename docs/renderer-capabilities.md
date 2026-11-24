# Renderer capabilities

The production PDF backend is ReportLab, renderer 0.3.7 with `premium-ats-single-column-v1` and the core Helvetica font profile. It uses US Letter pages, 0.62-inch horizontal and 0.46-inch vertical margins, a centered adaptive masthead, consistent section hierarchy and selectable single-column text. Resume acceptance allows at most two pages; a longer output fails QA rather than claiming success.

The premium template is an intentional portable alternative to compact two-column presentation. It preserves explicit roles, dates and evidence while reducing reading-order ambiguity. Arbitrary theme/font substitutions and compact fallback are not supported.

Validation uses pypdf plus pdfplumber, Poppler rasterization, ATS field/reading-order reconstruction, contact links, visual density, public-copy/evidence controls, PDF object/font inspection and artifact hashes. Core Helvetica is accepted without embedding; non-core fonts require embedding. Object preflight rejects invisible text, unexpected raster content, active actions and unsafe bounds. Semantic accessibility checks do not establish PDF/UA certification.

DOCX uses the same semantic resume content and configurable candidate identity. It is editable, uses a portable Arial style and keeps headings/role metadata with following content. DOCX has semantic readback; pagination must be inspected in Word or LibreOffice. PDF remains the validated application artifact. See the visual gallery for actual generated comparison renders and any layout differences.

For geometry regression, run `careeros --workspace <path> resume geometry --build-id <id>` to inspect the actual PDF. Compare to an independently reviewed synthetic signature using `--golden <signature.json>`; drift returns a failing exit code. This command never rewrites a golden. Review generated pages and source/evidence changes before accepting a new baseline. Existing fixture goldens remain unchanged by release preparation.
