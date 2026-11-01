# Target user: Titouan

<p align="center">
  <img src="assets/titouan.jpg" alt="Titouan" width="480">
</p>

Sensai is built for one user. Every feature, prompt, persona and test input in this repository
should make sense for him; if it does not, it is out of scope.

## Who he is

| | |
|---|---|
| **Name** | Titouan |
| **Age** | 17 |
| **School** | Final year of *lycée* (Terminale), maths speciality (*spécialité mathématiques*) |
| **Level in maths** | Struggling: he chose the speciality but is far behind the class |
| **Language** | French |
| **Goal** | Catch up, pass the maths speciality exam of the *baccalauréat*, and become confident enough in maths to keep studying it |

## His problem

Titouan is not lazy: he works, but alone he gets stuck and does not know why. In class the pace
is too fast for him to ask about every step, and private lessons are expensive.

He already tried general-purpose assistants (ChatGPT, Gemini) on their free plans. They did not
work for him:

- **Usage limits**: the free plans cap the messages or fall back to a weaker model, so a long
  revision evening stops halfway.
- **They give the answer, not the method**: he copies the solution, understands it in the
  moment, and is stuck again on the next exercise.
- **They forget him**: every conversation starts from zero. He has to explain his level and his
  weak points again each time, so the explanations are never pitched at him.
- **They are not about maths**: a general assistant answers at the level of whoever asks, with
  notation and shortcuts from outside the French curriculum.

## What he needs from Sensai

| Need | What it means for Sensai |
|---|---|
| Understand the method, not just get the result | Step-by-step solutions that explain *why* each step is taken, with every intermediate calculation shown |
| Answers pitched at his level | A user profile (level, curriculum, preferences) injected into every conversation |
| Not repeating himself | Long-term memory of his weak points and progress across sessions |
| Practise every day, as long as he wants | Runs locally through Ollama: free, no quota, no account |
| Trust what he reads | Visible reasoning, and sources when the answer comes from the web |
| Different explanations when one does not click | Personas he can switch mid-conversation (rigorous tutor, simpler explanations…) without losing the context |

## A typical session

It is 9 p.m. on a weekday. Titouan has an exercise on sequences and proof by induction due
tomorrow. He opens Sensai on his laptop at his desk:

1. Sensai already knows he is in Terminale, maths speciality, and that sequences are one of his
   weak points: he does not explain it again.
2. He pastes the exercise. Sensai restates what is asked, explains which method fits, then
   solves it step by step.
3. He does not understand the induction step. He switches to a persona that explains more
   simply; the conversation and the exercise stay in context.
4. He asks for a similar exercise to try on his own, then checks his answer with Sensai.
5. At the end, Sensai has noted that induction is still shaky. The next evening, it takes this
   into account without being told.

## Constraints this puts on the system

- **Hardware**: a personal or family laptop, no dedicated GPU. The model must run on CPU with
  acceptable latency, and the answer must stream so he is never staring at a blank screen.
- **Tone**: patient and encouraging, never condescending; he is a teenager who already feels
  bad at maths.
- **Language and notation**: French, with the notation used in French *lycée* maths.
- **Privacy**: he is a minor. His questions, profile and what Sensai remembers about him stay on
  his machine and are never sent to a cloud service.
- **Curriculum**: test inputs and examples come from the Terminale maths speciality programme
  (sequences, limits, derivatives and convexity, exponential and logarithm, integration,
  probability, space geometry, proof by induction), not from generic questions.

## Assumptions to confirm

These details are not in the brief and were filled in to make the profile usable. Change them if
they do not match what the team has in mind:

- He is in Terminale (the usual class at 17), preparing the speciality exam of the bac.
- His machine is a laptop without a dedicated GPU, with 8–16 GB of RAM.
- He works in the evening at home, alone, in French.
- The weak points used as examples (sequences, induction) are illustrative.
