# [T3] Web search: user stories

Target user: [Titouan](../user-profile.md).

## T3-1 · Find recent information about the bac

**As** Titouan, who is preparing the maths speciality exam of the bac,
**I want** Sensai to search the web for information a local model cannot know (exam dates, the
official curriculum in force, recent past papers),
**so that** I revise from up-to-date information, with the links to check it myself.

Link to the scenario: [who he is](../user-profile.md#who-he-is), the bac goal, and
[his needs](../user-profile.md#what-he-needs-from-sensai), "trust what he reads".

Acceptance criteria:

- « Quelle est la date de l'épreuve de spécialité maths du bac cette année ? » shows a
  `web_search` call in the reasoning block, with its query and the results returned (title, URL,
  snippet).
- The answer relies on these results and gives at least one URL from the search.
- A maths question that does not depend on current events (« Dérive x² + 3x ») triggers no search.
- Sensai only claims to have searched if it actually called `web_search`.

Check: the manual test above (it depends on the network: have a recording ready for the defense),
and `uv run pytest tests/core/agent/test_re_act.py` for the call loop.

## T3-2 · An honest answer when the search fails

**As** Titouan, who sometimes revises without a reliable internet connection,
**I want** Sensai to tell me when the search found nothing or could not run,
**so that** I do not revise from made-up dates or past papers.

Link to the scenario: [his needs](../user-profile.md#what-he-needs-from-sensai), "trust what he
reads".

Acceptance criteria:

- With the network down (Ollama still reachable), the same question shows the `web_search` call as
  failed in the reasoning block; the answer says the search failed and gives no made-up date or
  URL.
- A search with no results returns `No results found.` to the model, which says so in its answer.
- With `web_search` disabled in `/tools`, no search runs and Sensai answers with what it knows,
  saying so.

Check: the manual test above, and `uv run pytest tests/core/tools/test_registry.py` for turning a
tool exception into an error result.

> There is no unit test yet for the `web_search` tool itself
> (`core/tools/builtin/web_search.py`).
