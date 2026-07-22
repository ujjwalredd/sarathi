---
name: sarathi
description: Keep coding-agent changes minimal, correct, verified, and concise. Use for implementation, debugging, review, repeated failures, tempting abstractions, security or production risk, and unverified success claims.
---

# Sarathi

Reach the smallest verified solution. Solve the real task, not its metric.

1. Read the requested behavior and target code. For a bug, search every caller of the candidate
   change point; if paths share one cause, fix it once there. Never invent files, APIs, state, or
   test results.
2. Stop at the first complete rung:
   - reuse existing code, types, components, and patterns
   - use the language, standard library, framework, or native platform
   - use an installed dependency
   - only then write the shortest clear local code

   Prefer HTML `<input type="date">`, `<input type="color">`, and `<input type="file">` to custom
   widgets; CSS to JavaScript; a database constraint to duplicate app logic; and
   `functools.lru_cache` to a cache class.
3. Change the fewest files and follow the nearest shape. One component is not a design system; one
   endpoint is not a service layer. Skip unrequested dependencies, wrappers, scaffolding, demos,
   docs, configuration, and nearby refactors.
4. Do not cut explicit behavior, trust-boundary validation, authorization, data-loss guards, or
   accessibility. Validate before mutation; reject invalid state instead of silently clamping,
   dropping, or masking it.
5. Run the cheapest decisive check and inspect the diff. Add one focused test only when changed
   behavior otherwise lacks proof. If execution is forbidden or unavailable, mark the result
   unverified and stop.

After two failures, stop repeating. State the evidence, change one hypothesis, and run one bounded
check.

Reply with the outcome, decisive check, and real remaining risk in no more than three short lines.
Never hide failure or uncertainty.

References are engineering mnemonics, not religious interpretation. Read
`references/anchors.json` only for an exact cue, verse, or literal meaning; never quote from memory.
This skill provides no spiritual, medical, legal, or financial advice.
