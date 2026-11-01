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
| [B1] Base CLI chatbot | [B1-1 to B1-4](b1-base-loop.md) | Read the answer right away, understand errors alone, a model that fits his laptop, formulas that look like his textbook |
| [M1] Sessions and profile | [M1-1, M1-2](m1-session-persistence-profile.md) | Resume yesterday's exercise, never repeat his level |
| [M3] Structured memory | [M3-1 to M3-3](m3-structured-memory.md) | Sensai remembers his weak points, he can correct them, his data is protected |
| [A1] ReAct | [A1-1 to A1-3](a1-react.md) | See the reasoning, fit the thinking to his machine, an answer even when a tool fails |
| [A4] Prompt versioning | [A4-1, A4-2](a4-prompt-versioning.md) | A tutor measured to explain better |
| [A5] Personas | [A5-1, A5-2](a5-persona.md) | Another explanation when the first one does not click |
| [T1] MCP and tools | [T1-1 to T1-6](t1-mcp.md) | Reliable tools, knowing what is available, practising without answers from the web, exact calculations from a calculator |
| [T2] Python sandbox | [T2-1 to T2-5](t2-sandboxed-code-execution.md) | Exact calculations, simulations and plots, with no risk to his machine |
| [T3] Web search | [T3-1, T3-2](t3-web-search.md) | Up-to-date information about the bac, nothing made up |
| [T5] Structured output | [T5-1 to T5-3](t5-structured-output.md) | A reliable small model, a clean memory, measurable comparisons |
| [EV3] Logging (partial) | [EV3-1, EV3-2](ev3-logging.md) | The team finds what went wrong and what is slow in his sessions |
