# Scope

## What Sensai does

Sensai is an assistant specialized in **mathematics**: it solves maths problems and explains how,
step by step. It is not limited to one school level or one curriculum: equations, derivatives and
integrals, sequences, probability, linear algebra, proofs… any maths problem is in scope.

To get the results right, Sensai does not calculate in its head. It calls maths tools and builds
its answer on what they return:

- **`run_python`** (merged): runs Python in an isolated Docker sandbox, with `sympy`, `numpy`,
  `scipy`, `matplotlib` and `pandas`, to solve, simplify, integrate, simulate or plot
  ([docs/core/sandbox.md](core/sandbox.md)).
- **`calculator`** (in review, PR #133): evaluates arithmetic expressions, and the prompts require
  every number in an answer to come from a tool result.

Requests outside maths are not what Sensai is built for: the tutor brings the conversation back
to maths.

The usage scenario follows one user, [Titouan](user-profile.md), a struggling Terminale student,
because a precise user drives the tone, the test data and the demo. The specialization itself is
maths in general, not his curriculum only.

## What we first wanted to build

Our first idea was a **Minecraft builder AI**: you describe what you want in natural language, and
the AI builds it in a Minecraft world.

We dropped it for three reasons:

- **Too hard to implement**: it needed an interface between the agent and a running Minecraft
  world, on top of everything the assistant itself requires.
- **Not enough time** to deliver it within the project timeline.
- **Local models are not powerful enough** for this task. Turning an instruction into a build means
  planning a structure in 3D and producing a long, exact sequence of actions, and the models we can
  run on our own computers do not do that reliably.

## Why maths

We looked for something much simpler to build, and that would be useful to real people:

- **It is achievable**: a maths assistant is a chat with tools, which the project's base loop
  already provides. The work goes into making it reliable, not into connecting it to another
  system.
- **The models we can run locally are good enough**: on our hardware, `qwen2.5:7b` answered all
  10 Terminale maths questions of our [benchmark](benchmark.md) correctly.
- **We need it ourselves**: we regularly have maths problems to solve, so we are its first users,
  and we can judge whether it actually helps.

How each catalog feature serves this scope, and which ones were left out and why, is in
[docs/features.md](features.md).
