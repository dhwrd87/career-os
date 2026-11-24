# Set your preferences

Tell your assistant what matters for your next job: the work you want, locations, remote or in-person arrangements, hours, travel and pay. Clear preferences make the results more useful. When a posting leaves something important unclear, check it rather than assuming it fits.

For a learning plan, add your current knowledge, time each week, budget and currency, preferred learning formats and subscriptions. A subscription only covers a resource when its plan details say so. Unknown prices or study time may keep an option out of a strict plan.

Your assistant uses these settings behind the scenes. You do not need to learn the internal file layout. Corrections to career facts still use the normal review and approval process.

## Technical reference

Initialization writes JSON to `careeros.yaml`; no YAML dependency is required. `package_root`, `user_data_root`, `state_root`, `output_root` and `cache_root` are relative to that file and must remain separate. Runtime data does not belong in the package root. Use `careeros schemas list` and `careeros schemas validate <json>` for exact contracts.

Search-request fields and learning preferences are documented in the skill references. Do not store passwords, API keys or tokens in configuration. Rendered pages are generated copies; rebuilding replaces them. Correct the source facts through the update workflow.
