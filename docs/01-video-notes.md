# Video notes — "LIVE: Uncle Bob on Software Fundamentals in the Age of AI"

- Source: https://www.youtube.com/watch?v=zcLPGC-tvgk (Matt Pocock's channel, streamed ~19 Aug 2026, 56 min)
- Guests: Matt Pocock (host), Robert C. Martin ("Uncle Bob")
- Notes are paraphrased from the auto-generated transcript; timestamps are mm:ss so you can jump to the spot.

## Why this video matters for the project

The "architecture viewer" is mentioned once (26:55–27:31), but it only makes sense inside the workflow Bob describes for the whole hour: agents write the code, deterministic tools constrain them, and the human's remaining job is to look at the *structure* — which is exactly what the viewer is for. The requirements in `02-requirements.md` are derived from the segment below plus Bob's real implementations (`03-reference-uncle-bob-tools.md`).

## The key segment (25:26 – 28:15): structure, the viewer, and the checker

- 25:26 Matt asks how Bob thinks about the internal structure of the code base — tests and mutation testing are great, but badly shaped modules and APIs undermine them.
- 26:06 Until about a month ago Bob did this part manually: after the agents built something he *interrogated* the agents about the structure (what are the modules, how do they relate, how do they talk to each other). The answers were frightening. He would then design a module partitioning himself, tell the agents how modules should communicate, and hand them an implementation plan.
- 26:55 So he had his agents build him an **architecture viewer**. What it does, in his words (paraphrased):
  - pops up a UML-style diagram of the modular structure of the system;
  - shows where the dependencies run (direction);
  - click a module → see inside it, its submodules;
  - click a submodule → the code itself pops up on screen;
  - so he can drill down as far as he wants and view the architecture *at any level*.
  - He says it was really useful and he has made good use of it.
- 27:31 He also built a second, **deterministic tool**: he defines which module should depend on which, which must not, and how the dependencies should flow. That goes into a tight little specification file. A checker runs at the end of the agents' work; if the rules are violated the agents have to fix it — usually by inverting a dependency, inserting an interface, or splitting a module in half. The agents cannot argue with it.
- 28:08 He is trying to automate the *design* step itself (having agents partition modules well without him) and has not had much luck so far.
- 28:17 Why module structure gives so much leverage: anything well partitioned with disciplined interfaces is graspable by humans *and* by models; agents work far better when they can focus on one module whose contents are all about one topic (Matt's "trajectory"). Loading a module with everything under the sun confuses the agent the same way it confuses a person (29:16, the "coffee and soap opera" context-window argument from 24:03).
- 29:40 Ousterhout's *deep modules* (small interface, lots hidden) — Bob agrees: models pay attention to interface names and structure, and can skip reading the code beneath, which is both a danger and an advantage (30:32). They also read the tests to understand the system. Anything that helps the structure of the code helps the models understand it.

## The surrounding workflow (context the tool has to fit into)

- 04:13 – 09:55 Started using agents around December (2025). Agents are fast but leave a mess ("dog do"), which made *him* slow. Insight: because they are fast and do not mind boring work, two old ideas that were impractical in the early 2000s become practical — the **CRAP** metric (cyclomatic complexity × coverage) and **mutation testing**. His principle now: set the agents working, make them run the deterministic tools, and get to a point where he does not have to look at the code at all; he verifies by looking at scores and spot checks.
- 10:49 – 12:10 Messy code hurts agents too: they start breaking one thing while fixing another, go in circles, and one even gave up. The threshold is different from humans but it exists.
- 12:11 – 15:14 Steering (long instruction files) vs deterministic checks: models treat rules as guidelines; "lost in the middle" means long prompts lose their middle. Keep the initial prompt minimal and apply deterministic tools *after the fact*.
- 16:18 – 17:37 Too many checks slow the agents down; the checks put the agent in a loop ("change the code until the tool says it's OK"). He trades productivity for quality and has not found the limit yet.
- 17:39 – 23:08 His pipeline of single-purpose agents, each born for one task with a clean context: **specifier** (human doc → Gherkin + QA procedure) → **coder** (unit tests + code, make the Gherkin pass) → **cleaner** (CRAP analysis, code review) → **hardener** (mutation testing, 100% coverage) → **QA** (turns the QA document into an executable script). About an hour per task vs. five minutes for one sloppy agent, still 4–5× a human.
- 32:24 – 35:21 Thresholds differ for agents: CRAP limit 4 for humans, 6 (maybe 8) for agents. He imposes human *values* on agents but not human *disciplines* (no forced TDD for agents).
- 35:46 – 41:36 Planning: heavy up-front planning ("spec-driven development") failed for him every time; he now does a story or two, looks at the architecture at the end, manually sorts things out, then continues — and suspects the manual organizing step at the end may never go away. The cost of change has plummeted, so iterate instead of planning.
- 42:38 – 44:02 Specs are ephemeral; the end result is the specification. His tools (CRAP for Clojure/Java/Go, mutation tester, agent harness) are public but he tells people: don't download them, point your agents at them and have them build one for *you*. (That is the approach this project takes.)
- 46:01 – 49:42 Tactical vs strategic programming (Ousterhout): agents are good at tactical, bad at strategic. Matt calls the module viewer an abstraction layer over the code that is also a great way to *learn* a system (49:24).
- 53:01 – 55:46 Fundamentals still matter because software is the most complex thing humans build, and the fundamentals are how we organize complexity so it can be conceived by humans and by models.

## One-line takeaways for the tool

1. The viewer exists so a human can do the strategic work (partitioning, dependency direction) without reading all the code.
2. The checker exists so the agents cannot drift from that design; it must be deterministic, fast, and produce failures the agent can act on.
3. Both must show the same truth: the actual dependencies in the source, not what anyone believes they are.
