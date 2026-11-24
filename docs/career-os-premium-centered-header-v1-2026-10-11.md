# Premium Centered Header V1

Career OS 0.3.19 makes `PREMIUM_CENTERED_MASTHEAD` the default header presentation for premium single-column recruiter resumes. The source order remains name, positioning headline, location, phone, email, LinkedIn, portfolio, GitHub, then body content.

The masthead renders centered plain text in four semantic layers: identity, positioning, primary contact, and professional links. A single divider follows the links. It does not use tables, floating elements, text boxes, icon-only fields, hidden text, or graphical meaning.

Width handling is deterministic:

- `STANDARD_CENTERED` uses the normal production type scale.
- `COMPACT_CENTERED` applies bounded font-size adjustments and preserves the approved 8-point minimum.
- `CONTROLLED_HEADLINE_WRAP` breaks an overlong headline into two centered semantic lines.

Primary contact and professional-link rows wrap independently. Professional links remain visible, selectable, extractable, and annotated with their full destinations.

`MastheadGeometryV1` records measured PDF offsets, vertical gaps, masthead height, safe width, line counts, missing rows, and clipping risk. Production acceptance requires every centered line to fall within the configured center tolerance, no missing rows, no clipping risk, and a bounded masthead height.

The release-candidate spacing calibration retains the same masthead architecture and version. The premium divider uses a 4-point pre-space (previously 2 points), while its width, weight, post-space, typography, body spacing, and fallback remain unchanged. `MastheadGeometryV1` additionally records `professional_links_bottom_y`, `divider_y`, `summary_top_y`, `links_to_divider_gap`, `divider_to_summary_gap`, and `divider_balance_ratio` so optical balance is acceptance evidence rather than an unmeasured style judgment.

`ATS_MINIMAL_FALLBACK` preserves the earlier linear header. It remains available for an explicitly governed rendering fallback and continues to pass the same extraction, autofill, annotation, metadata, typography, and reading-order checks.
