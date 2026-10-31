# User stories

Every story starts from the same user: [Titouan](../user-profile.md), 17, in his final year of
*lycée* with the maths speciality, struggling, who revises alone in the evening on a laptop
without a GPU.

Format of each story:

> **As** [a type of user],
> **I want** [an action / feature],
> **so that** [the benefit / value gained].

Each story also names the part of the [user profile](../user-profile.md) it answers, gives
acceptance criteria that can be checked without the team, and the command to check them.

Example messages are written in French, the language Titouan uses with Sensai.

## Traceability

| Feature | Stories | Titouan's need covered |
|---|---|---|
| [B1] Base CLI chatbot | [B1-1 to B1-3](b1-base-loop.md) | Read the answer right away, understand errors alone, a model that fits his laptop |
| [M1] Sessions and profile | [M1-1, M1-2](m1-session-persistence-profile.md) | Resume yesterday's exercise, never repeat his level |
| [M3] Structured memory | [M3-1 to M3-3](m3-structured-memory.md) | Sensai remembers his weak points, he can correct them, his data is protected |
| [A1] ReAct | [A1-1 to A1-3](a1-react.md) | See the reasoning, fit the thinking to his machine, an answer even when a tool fails |
| [A4] Prompt versioning | [A4-1, A4-2](a4-prompt-versioning.md) | A tutor measured to explain better |
| [A5] Personas | [A5-1, A5-2](a5-persona.md) | Another explanation when the first one does not click |
| [T1] MCP and tools | [T1-1 to T1-4](t1-mcp.md) | Reliable tools, knowing what is available, practising without answers from the web |
| [T2] Python sandbox | [T2-1 to T2-5](t2-sandboxed-code-execution.md) | Exact calculations, simulations and plots, with no risk to his machine |
| [T3] Web search | [T3-1, T3-2](t3-web-search.md) | Up-to-date information about the bac, nothing made up |
| [T5] Structured output | [T5-1 to T5-3](t5-structured-output.md) | A reliable small model, a clean memory, measurable comparisons |

## Known gaps

What the stories describe but the code does not do yet, or no longer does:

- **T1**: the only "own" MCP server is `scripts/fake_mcp_server.py` (an `echo` tool). Sensai needs
  a server of its own that is useful to Titouan, and a test against a third-party server other
  than GitHub ([T1-2](t1-mcp.md)).
- **T5, plan mode**: the `plan` schema exists (`config/schemas/plan.json`) but nothing in the chat
  turns plan mode on, so `[structured_output] enabled` has no visible effect. The
  `permission_decision` schema is reserved for a future human confirmation (A3). The former T5
  stories that described these plans were replaced by T5-1 to T5-3.
- **X2**: `Esc` interrupts a generation ([B1-1](b1-base-loop.md)), but there is no editing of a
  past message and no branching. X2 is therefore not presented as a feature.
- **Default persona**: `config/personas/sensai.toml` describes an assistant "for mathematicians",
  concise, that gives "the result first". This goes against Titouan's profile, who needs the
  method step by step and a patient tone.
- **Profile**: `config/profile.toml` is not Titouan's yet (`language = "Python"`).
