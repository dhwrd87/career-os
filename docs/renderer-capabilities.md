# Resume files and layout

Career OS creates a premium, single-column PDF resume. The design uses a clear name and headline, readable sections and consistent spacing. Checks look for layout problems, missing content, text order and changed files before a draft is used.

PDF text can be selected and read by software. This helps with application systems, but no tool can promise that every employer's ATS will read every field correctly. PDFs are not tagged for PDF accessibility standards.

An editable DOCX export uses the same resume content. It may wrap or paginate differently in Word, LibreOffice or another editor. Check the file in the editor you intend to use. Microsoft Word and Windows layout are not yet verified.

One tested design is supported. Your name, contact details, career information and target job can change; arbitrary fonts/themes and broad non-Latin-script support are not included. Multi-page resumes use the existing page, spacing and content checks. Do not remove useful career facts merely to force a one-page result.

Poppler is required for PDF checks. LibreOffice is useful for reviewing DOCX appearance but is not required by the automated test suite. See the [actual visual examples](visual-gallery.md) and [setup guide](installation.md).

Developers should retain the exact template, renderer and font versions recorded with each build. Geometry comparisons and accepted artifact hashes remain technical controls; visual goldens are not refreshed just to pass a check.
