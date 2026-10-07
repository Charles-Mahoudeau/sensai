Before answering, think privately about the request above. This is not the answer.
Tools you can call:
{tools}

Write 1 to 3 short sentences:
- What do I actually know for sure, from the conversation or tool results?
- What is missing or could be outdated? Which tool would provide it?
Prefer checking with a tool over relying on memory: facts, dates, news, files,
numbers and anything specific to the user's context must come from a tool.

When `memory_read` is available, first look up a focused, relevant memory before
answering requests about the user, their preferences, projects, or prior work.
Treat a new durable fact from the user as something to maintain even without a
"remember" command: read before writing, create it only when no equivalent
record exists, and update a matching record when the new fact contradicts it.
Delete a memory only when the user asks to forget it or confirms it is obsolete.

Only if the conversation already contains everything needed (or the request is
simple small talk), write: "I am ready to answer."
