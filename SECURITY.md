# Security

## Reporting

Do not open a public issue for a vulnerability in the harness, the build scripts,
or anything that executes locally. Email the maintainer instead.

## Scan before you install

This is a Claude Code plugin. Installing one grants it prompt-level influence over
every session, and plugins that register hooks can execute local commands. That is
true of this plugin and of every other one.

Scan it before trusting it:

```bash
skillspector scan https://github.com/<your-org>/sarathi
```

[NVIDIA/SkillSpector](https://github.com/nvidia/skillspector) is free, Apache-2.0,
and covers 64 vulnerability patterns including hidden instructions, prompt injection,
and trigger abuse. Ten seconds, regardless of who wrote the plugin.

## What this plugin does and does not do

- **Registers no hooks.** No local command execution at install or session start.
- **Ships no network calls** in the skill itself. `bench/build_anchors.py` fetches
  verse data from GitHub, but only when a maintainer runs it deliberately.
- **Reads nothing outside its own directory** at runtime.

The benchmark harness (`bench/`) invokes the `claude` CLI as a subprocess. That is
opt-in, costs money, and never runs automatically.

## Scope note

The skill offers reasoning discipline for engineering work. It is not a source of
spiritual, medical, legal, or financial advice, and it claims no religious authority.
