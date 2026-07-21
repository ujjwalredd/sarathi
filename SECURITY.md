# Security

## Report a vulnerability

Please do not open a public issue for a security problem in the plugin, benchmark, or build
scripts. Contact the maintainer privately so the issue can be reviewed before details are shared.

## Review before installing

An agent plugin can influence model behavior. A plugin may also run local commands if it
registers hooks, so review any plugin before trusting it.

You can scan this repository with NVIDIA SkillSpector:

```bash
skillspector scan https://github.com/ujjwalredd/sarathi
```

[NVIDIA SkillSpector](https://github.com/nvidia/skillspector) is available under the Apache 2.0
license and checks for common plugin risks such as hidden instructions, prompt injection, and
unsafe hooks.

## What Sarathi can access

- The skill registers no hooks and runs no commands automatically.
- The skill itself makes no network requests.
- The skill does not read files outside its own package unless the user or active task requires it.
- `bench/build_anchors.py` downloads source verse data only when a maintainer runs it directly.
- Benchmark scripts call the Claude or Codex CLI only when a user starts a paid benchmark run.

## Scope

Sarathi is a reasoning aid for engineering work. It is not spiritual, medical, legal, or
financial guidance, and it claims no religious authority.
