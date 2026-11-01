# Accessibility

Sensai is a terminal assistant for mathematicians. This document lists the
accessibility questions that raises: who might struggle to use it today, why,
and which directions are worth exploring.

Math is a hard case for accessibility. Its meaning lives in **layout**
(fractions, exponents, matrices) and in **pictures** (plots, diagrams). Both are
easy to lose when the output is a stream of characters in a terminal, read by a
screen reader or seen with impaired vision.

## Who this is about

| Need | Examples | Where Sensai is affected |
| --- | --- | --- |
| Color vision deficiency | protanopia, deuteranopia (about 1 in 12 men), tritanopia | colored log levels and categories, the theme, plot colors |
| Low vision | needs large text, high contrast, magnification | small inline plots, dim text, box drawing |
| Blindness | uses a screen reader (Orca, NVDA, VoiceOver) or a braille display | the full-screen TUI, LaTeX formulas, plots |
| Motor impairments | keyboard only, one hand, slow typing | key bindings and chords, time limits |
| Cognitive and attention needs | dyslexia, ADHD, fatigue | long answers, animations, dense panels |
| Language | non-native speakers | French and English answers, math vocabulary |

## Color

**Principle: color can reinforce meaning, but never carry it alone.** The
current TUI mostly follows this already, and the remaining gaps are known.

- **`/logs`** colors levels and categories, and also writes them as text
  (`WARN`, `ERROR`, `ollama`, `tools`). Someone who can't tell yellow from green
  loses nothing but speed. Keep it that way: every new colored element should
  have a word or a symbol too.
- **Tool status** already pairs a symbol with its color (`●`, `✗`). Red and
  green are the pair most often confused, so the symbol matters more than the
  color.
- **Themes.** Textual themes could offer a high-contrast variant, and a
  palette checked for the common types of color blindness (blue/orange instead
  of red/green). The `NO_COLOR` environment variable is a widely used convention
  for "no colors at all", and worth respecting.
- **Dim text.** Hints, timestamps and placeholders use muted colors. They are
  the first thing to disappear with low contrast. Contrast should be checked
  against the WCAG ratios (4.5:1 for normal text), even though a terminal is
  not a web page.

## Plots

The sandbox's plots are often the answer itself, so they deserve the most care.

- **Colorblind-safe defaults.** The sandbox image could set a matplotlib style
  with a colorblind-safe palette (`viridis`/`cividis` for color maps, the
  "tableau colorblind" cycle for lines), so every plot benefits without the
  model having to think about it.
- **Not only color.** Several curves can be told apart by line style (solid,
  dashed, dotted) and markers as well as by color. Direct labels on the curves
  are easier to read than a legend that must be matched by color.
- **A text description with every plot.** The model wrote the code, so it knows
  what the plot shows. The tool could ask it to also `print()` the key facts
  (roots, extrema, asymptotes, intersections) so the answer states them in
  words. For a blind user, that text *is* the plot. It also helps everyone check
  that the picture says what the model claims.
- **The data behind the plot.** Saving the plotted values as a CSV next to the
  PNG lets a user explore them with their own tools: a screen reader, a braille
  display, a spreadsheet.
- **Size and resolution.** Inline images are blurry in terminals without Sixel
  or Kitty graphics (see `docs/adapters/tui.md`). The path under each image
  opens the full-resolution PNG, which can then be zoomed with system tools.
  That path must stay visible and easy to copy.
- **Sonification** (exploratory). Audio graphs map a curve's height to pitch.
  They are used in some screen readers and calculators so that blind students
  can "hear" a function's shape. A small sandbox library could produce a short
  audio file next to a plot. It's a niche feature, but a very math-specific one.

## Formulas

Answers use LaTeX (`\frac{a}{b}`, `x^{2}`, `\sqrt{\pi}`). In a terminal it is
shown raw.

- **Sighted users** who know LaTeX read it fine; others find it noisy. Unicode
  math (`a/b`, `x²`, `√π`) is lighter for simple expressions, and sympy can
  print it (`pretty()`). A persona or profile instruction could pick the
  notation.
- **Screen readers** read raw LaTeX symbol by symbol ("backslash frac open
  brace a close brace…"). That's unusable for anything but short formulas.
  Spoken math, such as "a over b", "x squared" or "the square root of pi", is
  what blind mathematicians are used to. Tools that convert LaTeX or MathML to
  speech exist (Speech Rule Engine, the engine behind MathJax's speech output,
  and MathCAT), but they come from the web world.
- **Braille displays** can show math in Nemeth or UEB math codes. The
  converters that produce speech usually produce braille too, so both needs
  could be served by the same step.
- **Simplest first step:** a profile preference ("explain formulas in words")
  that asks the model to say each formula in plain language next to its LaTeX.
  It needs no code, and the model already knows how to read math aloud.

## Text to speech

Speaking answers aloud would help blind and low-vision users, people with
dyslexia, and anyone who prefers listening. Things to weigh:

- **Stay local.** Sensai runs on a local model. Local text-to-speech engines
  (Piper, espeak-ng) keep conversations off the network, like the rest of the
  app. A cloud voice would break that promise.
- **Speak the right text.** The streamed answer contains Markdown and LaTeX. It
  needs a "speakable" version: no Markdown symbols, formulas read as spoken
  math (see above), code blocks summarized rather than spelled out, tool calls
  announced briefly ("ran the Python sandbox, exit 0").
- **Latency.** Answers already take tens of seconds on a CPU, and text to speech
  competes for the same CPU. Speaking sentence by sentence while the answer
  streams would feel faster than waiting for the whole answer.
- **Control.** It must be easy to stop speech (the same `esc` that stops
  generation), skip to the next paragraph, change the speed, and turn it off.
  A `/speak` command or a config toggle fits the existing patterns.
- **Architecture.** A front-end concern: it would consume the engine's events,
  like the TUI does, with no change to the core.

## Screen readers and the TUI

Full-screen terminal apps are hard for screen readers. They redraw regions,
animate, and draw boxes with characters that get read aloud, so a user hears
noise or nothing.

- **Animations.** The companion face and the spinners change several times per
  second. They can make a screen reader repeat itself, and distract users with
  attention or vestibular needs. A "reduced motion" setting could freeze them.
- **Decorative characters.** Box drawing, `●`, `▸`, `↳` and the like are read as
  symbols by some screen readers. Plain words in a plain mode avoid that.
- **A plain mode.** The most robust answer is probably a non-full-screen mode:
  a simple line-by-line chat that prints messages and answers in order, without
  panels or redraws, which every screen reader handles. The engine already
  separates the core from the TUI, so a second, minimal front-end is a natural
  fit.
- **Keyboard.** Everything is reachable from the keyboard today: commands,
  panels, `esc`, `ctrl+t`. Keep it that way, avoid chords that need two hands,
  and never rely on the mouse alone (clicking a reasoning header must stay
  optional).

## Reading load

- **Answer length and structure.** Concise answers with the result first,
  short steps and plain sentences help people with dyslexia or fatigue, and
  everyone else too. The math persona already asks for "result first, then the
  key steps".
- **Reasoning display.** Collapsing the reasoning group by default already
  hides detail until it's wanted. That's a good pattern to keep.
- **No time pressure.** Nothing in Sensai expires or times out on the user's
  side. Keep it that way.
- **Language.** The profile sets the answer language. Math vocabulary differs
  between languages ("dérivée" / "derivative", the decimal comma), and the model
  should follow the user's conventions.

## Directions, from cheapest to most ambitious

| Idea | Effort | Helps |
| --- | --- | --- |
| A rule for new UI: never color alone, always a word or symbol | none (review rule) | color vision |
| Profile preference: "explain formulas in words" | none (profile text) | blind, low vision, learners |
| Colorblind-safe matplotlib style in the sandbox image | small | color vision, everyone |
| Print the key facts of every plot, and save its data as CSV | small (tool description) | blind, low vision |
| Respect `NO_COLOR`; a high-contrast theme | small | low vision, color vision |
| Reduced-motion setting (freeze companion and spinners) | small | screen readers, attention |
| Plain line-by-line front-end | medium | screen readers |
| Local text to speech with speakable answers | medium to large | blind, low vision, dyslexia |
| Spoken math and braille for formulas | large | blind |
| Sonified plots | large, exploratory | blind |

## Open questions

- Who are our real users? Testing with even one screen-reader user would teach
  more than this whole document.
- Should accessibility settings live in the profile (per user), in the config
  (per installation), or both?
- Can spoken math be done well in Python, or does it require a JavaScript
  engine such as Speech Rule Engine?
- How do we test it? Color checks can be automated (contrast ratios, simulated
  color blindness on plots); screen-reader behaviour mostly can't.
