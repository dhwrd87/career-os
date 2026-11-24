# Persisted contracts

The formal registry is distributed as `careeros/schemas/registry.v1.json`. `careeros schemas list` reports contract ID, version, status, supported package range, migration availability, and documentation location. `careeros schemas validate <json-path>` selects the schema from the document's `schema` field and performs read-only validation.
