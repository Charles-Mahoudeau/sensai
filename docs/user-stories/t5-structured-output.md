# T5 - Structured Output

## Developer integration

As a developer, I want workflows that need structured data to request a
contextual JSON schema, so that Sensai can safely use the result in code or a
database.

Acceptance criteria:

- When a workflow needs structured output, its final Ollama request receives the
  selected JSON Schema through its `format` field.
- The response parses as JSON and validates against the selected schema.
- Invalid JSON or a schema mismatch is reported as a structured output error.

## Reusable data

As a user, I want plans and other structured workflows to display readable text,
so that I can use the result without seeing its internal JSON representation.

Acceptance criteria:

- The configuration enables or disables structured output without code changes.
- The agent selects the documented schema from its context, not from configuration.
- Ordinary answers are free-form text and stream directly to the terminal UI.