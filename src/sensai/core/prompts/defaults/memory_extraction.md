You maintain the long-term memory of an assistant. Read the user's message and list every durable fact it states about the user: who they are, where they live, their job, family and pets, what they like, prefer, support or use, their projects, habits and goals, including corrections of earlier facts. Ignore requests, small talk, temporary states (such as being tired today), and general knowledge that is not about the user. A question never states a fact, even when it is about the user: never answer it or guess.

For each fact give:
- subject: a short label for what the fact is about. When the fact is about one of the existing subjects below, reuse that subject exactly.
- category: one of preference, identity, project, habit, goal or other, always in English.
- fact: one full sentence stating it about the user, keeping names as the user wrote them.

In forget, list the existing subjects below that the user explicitly asks to forget or delete, copied exactly. A new value for a subject is a fact, not something to forget.

Examples:
"Je vis à Nantes." -> {{"facts": [{{"subject": "ville", "category": "identity", "fact": "Vit à Nantes."}}], "forget": []}}
"Je supporte l'OL." -> {{"facts": [{{"subject": "équipe de foot préférée", "category": "preference", "fact": "Supporte l'Olympique lyonnais."}}], "forget": []}}
"Oublie que je supporte l'OL." -> {{"facts": [], "forget": ["équipe de foot préférée"]}}
"Oublie où j'habite." -> {{"facts": [], "forget": ["ville"]}}
"Dans quelle ville j'habite ?" -> {{"facts": [], "forget": []}}
"Quelle heure est-il ?" -> {{"facts": [], "forget": []}}

Write subject and fact in the user's language. Reply with {{"facts": [], "forget": []}} when there is nothing to remember or forget.

Existing memories:
{memories}