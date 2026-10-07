# Structured Output

When structured output is enabled, Sensai passes a JSON Schema to Ollama only
when the current agent workflow needs structured data. The JSON stays internal:
Sensai formats the validated value as Markdown before persisting it and sending
it to the terminal UI. Ordinary answers are free-form text and stream directly
to the terminal UI.

```toml
[structured_output]
enabled = true
```

The configuration loads every bundled schema; the agent selects one from its
current context.

## `plan`

File: `config/schemas/plan.json`.

The agent selects this schema in plan mode. It returns a title and at least one
step. Every step has a title, description, and a priority of `low`, `medium`,
or `high`.

```json
{
  "title": "Prepare a release",
  "steps": [
    {
      "title": "Run tests",
      "description": "Execute the project test suite.",
      "priority": "high"
    }
  ]
}
```

## `permission_decision`

File: `config/schemas/permission_decision.json`.

This schema is reserved for the future A3 confirmation flow. It is loaded with
the other schemas but is not selected or used until that flow is implemented.
It will describe the requested action, its targets, risk, and the need for user
confirmation.

```json
{
  "action": "write_file",
  "targets": ["notes.txt"],
  "risk": "medium",
  "reason": "The action changes a file on disk.",
  "requires_confirmation": true
}
```
