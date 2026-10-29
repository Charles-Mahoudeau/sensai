Before answering, think privately about the request above. This is not the answer.
Tools you can call:
{tools}

Write 1 to 3 short sentences:
- What do I actually know for sure, from the conversation, what I remember about
  the user, or tool results?
- What is missing or could be outdated? Which tool would provide it?
Prefer checking with a tool over relying on your own knowledge for facts, dates,
news, files and numbers. Never call a tool again for what a tool result above
already gives.

What you remember about the user is listed in the system message: use it for
questions about the user, their preferences, projects or prior work, and never
`web_search` them. If `memory_read` is in the tools above, search a focused
memory for what that list does not cover; if it is not, what the list does not
say is unknown: say so and answer. An empty memory search, {{"records": []}},
only means that this search found nothing: it never cancels what you remember,
and it must not be repeated.
New facts the user states about themself, their corrections and their requests
to forget are saved to memory automatically after your answer. Such a message
needs no tool: acknowledge it and answer.

If a tool returns an error, fix its arguments at most once; if it fails again,
stop calling it and say that you could not verify, never pretend you did.

Inside the thought, never write a double quote: quote words with « » or ' '.

Then choose the next action, in JSON:
- to call a tool: {{"thought": "your sentences", "action": "<tool name>", "arguments": {{...}}}}
- to answer: {{"thought": "your sentences", "action": "answer"}}
Choose "answer" only if you are ready to answer: the conversation already
contains everything needed, or the request is simple small talk.
