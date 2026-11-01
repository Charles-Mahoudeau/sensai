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

The agent selects this schema in plan mode (`/mode plan`), where Sensai gives the
method to solve an exercise instead of the answer. The plan has a title, at least
one step, and how to check the result. Every step has a title (what to do), a
description (how to do it) and the course notion it relies on.

```json
{
  "title": "Résoudre x² − 5x + 6 = 0",
  "steps": [
    {
      "title": "Calculer le discriminant",
      "description": "Identifie a, b et c, puis calcule Δ.",
      "notion": "Δ = b² − 4ac"
    }
  ],
  "check": "Remplace chaque solution dans l'équation."
}
```

It is shown as a numbered list: each step's title in bold, its description, its
notion in italics, then the check after `✓`.

In plan mode the agent makes a single call: no reasoning step and no tool, so no
tool result can give the answer away. The versioned prompt `react_plan` is
appended to the user's message for that call only; it asks for the method and
forbids any calculation or result. Without structured output, the agent refuses
plan mode (`ModeUnavailableError`) and stays in the default mode.

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
