#!/usr/bin/env python3
"""Codex GPT-5.5 port of Ponytail's agentic, multi-file benchmark.

Derived from Dietrich Gebert's Ponytail runner at commit 16f2980 under the MIT License.
Copy this file beside the upstream tasks.py as benchmarks/agentic/run_gpt.py.

Runs each (task x arm x model) through a real headless Codex session in an isolated
temp workspace seeded with a starter file, then scores the produced files deterministically
for CORRECTNESS and SAFETY -- the axis the single-shot promptfoo bench was blind to.

Over-engineering is proxied by SOURCE file count + source LOC (tests are counted separately,
never as bloat -- writing a test is good practice, not over-engineering). An LLM-judge
over-engineering score is a later pass.

  python run.py --selftest
      Verify every scorer (good passes, bad is caught). No API, no spend. Run first, always.

  python run_gpt.py --all --models gpt-5.5 --runs 4
      Live run (spends API). Workspaces kept under runs/<stamp>/ for inspection.

  python run.py --rescore runs/<stamp>
      Recompute metrics + aggregate from kept workspaces. No API. Use after changing a
      metric or scorer so you never pay the API twice for a measurement tweak.

The Codex CLI is the harness. No SDK dependency. JSONL events carry token usage; dollar cost is
an API-equivalent estimate from the published GPT-5.5 token prices, not a Codex subscription bill.
"""
import argparse, concurrent.futures, datetime, json, os, re, shutil, signal, statistics, subprocess, sys, tempfile, threading, time
from collections import defaultdict
from pathlib import Path

from tasks import TASKS

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = Path(__file__).resolve().parent / "runs"
ARM_DIR = Path(os.environ["SARATHI_ARM_DIR"])

def _arm(name): return (ARM_DIR / name).read_text(encoding="utf-8")
ARMS = {
    "baseline":       lambda: None,
    "ponytail":       lambda: _arm("G.txt"),
    "caveman":        lambda: _arm("F.txt"),
    "sarathi":        lambda: _arm("H.txt"),
}
MODELS = {"gpt-5.5": "gpt-5.5"}
FRESH_INPUT_USD_M = 5.0
CACHED_INPUT_USD_M = 0.5
OUTPUT_USD_M = 30.0
ORIGINAL_CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))

# Skills are plugins activated by a SessionStart hook. To test exactly one at a time we exclude the
# user's globally-enabled plugins (--setting-sources project,local) and load one plugin from its
# cache dir (--plugin-dir). The smoke test verifies activation by output style.
PLUGIN_ARMS = ()                                # all skills use identical raw-prompt injection
PLUGIN_CACHE = Path.home() / ".claude" / "plugins" / "cache"

def _plugin_dir(name):
    """Resolve a plugin's cache dir portably -- hardcoding one machine's absolute path
    (e.g. C:\\Users\\<you>\\...) made the ponytail/caveman arms unreproducible off that box.
    Order: env override -> latest version dir under ~/.claude/plugins/cache -> clear error.
    Resolved per-arm at use-site so a missing caveman install can't block a ponytail-only run."""
    env = os.environ.get(f"{name.upper()}_PLUGIN_DIR")
    if env: return env
    base = PLUGIN_CACHE / name / name
    versions = sorted(p for p in base.glob("*") if p.is_dir()) if base.exists() else []
    if not versions:
        sys.exit(f"{name} plugin dir not found under {base}; install the plugin or set {name.upper()}_PLUGIN_DIR")
    return str(versions[-1])                    # latest version dir; not pinned to one machine's hash

CELL_TIMEOUT = 300  # seconds per cell; a hung agent is force-killed (process tree) so the pool can't freeze
MAX_INFRA_FAILURES = 3
ACTIVE_PROCS = set()
ACTIVE_LOCK = threading.Lock()

# Added to every arm's prompt, identically. We measure code PRODUCTION, not execution: agents
# write the implementation and stop. No live verification -- earlier attempts had agents open a browser,
# hit the template's login wall, and retry, inflating tokens/time with flailing instead of code. Writing
# tests is still explicitly allowed, so ponytail's "leave a runnable check" discipline is not suppressed.
NO_RUN = ("Write the implementation and stop. You may inspect files and the final diff. Do not execute "
          "project code, tests, builds, formatters, package managers, servers, databases, or browsers. "
          "Do not install anything. Only the code you write is measured, not its execution.")

def _is_test(p: Path, workdir: Path):
    rel = p.relative_to(workdir)
    name = p.name.lower()
    return (name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
            or any(part.lower() in ("test", "tests") for part in rel.parts[:-1]))

CODE_EXT = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".go", ".rs", ".java", ".rb", ".sh"}

def _count(p: Path, with_comments: bool):
    try: lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception: return 0
    n = 0
    for ln in lines:
        s = ln.strip()
        if not s: continue
        if not with_comments and s.startswith(("#", "//", "*", "/*", "*/")): continue
        n += 1
    return n

_SELFCHECK_DEFS = ("def demo(", "def _demo(", "def selfcheck(", "def _selfcheck(",
                   "def _check(", "def _smoke(", "def smoke(")
def _selfcheck_split(p: Path):
    """Split a produced .py file at the first TOP-LEVEL self-check marker (a `__main__` guard or a
    demo()/selfcheck() function) through end of file. Returns (src_total, src_code, sc_total,
    sc_code), counted like _count. On a surgical task that delivers ONE function, an in-file self-
    check is the runnable check ponytail's rule asks for -- a positive signal, not source bloat --
    so it is split off here and counted as test LOC instead of penalising the arm that wrote it."""
    try: lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception: return 0, 0, 0, 0
    start = None
    for i, ln in enumerate(lines):
        if ln[:1] not in (" ", "\t") and (ln.startswith("if __name__") or ln.startswith(_SELFCHECK_DEFS)):
            start = i; break
    def cnt(seq):
        t = c = 0
        for ln in seq:
            s = ln.strip()
            if not s: continue
            t += 1
            if not s.startswith(("#", "//", "*", "/*", "*/")): c += 1
        return t, c
    if start is None:
        t, c = cnt(lines); return t, c, 0, 0
    t, c = cnt(lines[:start]); st, sc = cnt(lines[start:])
    return t, c, st, sc

def code_stats(workdir: Path, selfcheck_as_test: bool = False):
    """LOC over code-extension source files only (generated images/data can't pollute it).
    total_loc counts every non-blank line including comments and docstrings -- the bloat a vibe
    baseline actually produces. src_loc is code-only, for the breakdown. Tests tracked separately,
    never as bloat. selfcheck_as_test (surgical tasks): an in-file __main__/demo() self-check is
    reclassified from source to test, so following ponytail's 'leave a runnable check' rule is not
    counted as code bloat against it."""
    fixture = set()                                   # files that were seeded, not delivered
    fm = workdir / "_fixture_files.json"
    if fm.exists():
        try: fixture = set(json.loads(fm.read_text(encoding="utf-8")))
        except Exception: pass
    def _rel(p): return str(p.relative_to(workdir)).replace("\\", "/")
    files = [p for p in workdir.rglob("*") if p.is_file() and p.suffix in CODE_EXT
             and "__pycache__" not in p.parts and "node_modules" not in p.parts
             and not p.name.startswith((".", "_")) and _rel(p) not in fixture]
    src = [p for p in files if not _is_test(p, workdir)]
    tst = [p for p in files if _is_test(p, workdir)]
    test_loc = sum(_count(p, True) for p in tst)
    if selfcheck_as_test:
        total = code = sc_test = 0
        for p in src:
            t, c, st, _ = _selfcheck_split(p)
            total += t; code += c; sc_test += st
        return {"files": len(files), "src_files": len(src),
                "total_loc": total, "src_loc": code,
                "test_files": len(tst), "test_loc": test_loc + sc_test}
    return {"files": len(files), "src_files": len(src),
            "total_loc": sum(_count(p, True) for p in src),   # incl comments + docstrings (the bloat)
            "src_loc": sum(_count(p, False) for p in src),    # code only
            "test_files": len(tst), "test_loc": test_loc}

def _git(workdir, *args):
    return subprocess.run([shutil.which("git") or "git", *args], cwd=str(workdir),
                          capture_output=True, text=True)

def _git_snapshot(workdir):
    """Commit the seeded repo so we can diff exactly what the agent changes."""
    _git(workdir, "init", "-q")
    _git(workdir, "add", "-A")
    _git(workdir, "-c", "user.email=bench@local", "-c", "user.name=bench",
         "commit", "-q", "-m", "base", "--no-verify")

_SKIP_DIFF = ("-lock", ".lock", ".gen.ts", "lock.json", "routeTree.gen")
def git_diff_stats(workdir):
    """Added lines (incl comments) of code files the agent created OR modified, vs the seeded
    base. This is the delivered-code metric and matches the '+N' a PR/diff shows. Tests counted
    separately; lockfiles/generated files skipped."""
    _git(workdir, "add", "-A")
    out = _git(workdir, "diff", "--cached", "--numstat", "HEAD").stdout
    loc = files = test_loc = test_files = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3: continue
        added, _deleted, path = parts
        if added == "-": continue                              # binary
        if Path(path).suffix not in CODE_EXT: continue
        if any(k in path for k in _SKIP_DIFF) or "node_modules" in path: continue
        n = int(added)
        if _is_test(Path(workdir) / path, Path(workdir)): test_loc += n; test_files += 1
        else: loc += n; files += 1
    return {"files": files, "src_files": files, "total_loc": loc, "src_loc": loc,
            "test_files": test_files, "test_loc": test_loc}

def selftest():
    """Each task's good ref must score correct+safe; the bad ref must be caught on its
    declared axis. Verifies the instruments before any API spend."""
    failures = 0
    for tid, task in TASKS.items():
        if task.get("open"): continue  # open tasks measure LOC only, no good/bad refs
        axis = task.get("axis", "safe")
        for kind in ("good", "bad"):
            with tempfile.TemporaryDirectory() as d:
                for fn, content in task.get("seed", {}).items():   # seed siblings (a helper module
                    (Path(d) / fn).write_text(content, encoding="utf-8")  # the ref imports) too
                (Path(d) / task["file"]).write_text(task[kind], encoding="utf-8")  # entry = the ref
                r = task["score"](Path(d))
            ok = (r["correct"] == 1 and r["safe"] == 1) if kind == "good" else (r[axis] == 0)
            print(f"{'ok ' if ok else 'XX '} {tid:12} {kind:4} correct={r['correct']} "
                  f"safe={r['safe']} axis={axis}  {r['reason']}")
            failures += 0 if ok else 1
    failures += _selftest_plugin_dir()
    failures += _selftest_kill()
    print(f"\nselftest: {'all instruments valid' if not failures else str(failures) + ' BROKEN'}")
    return failures

def _selftest_plugin_dir():
    """Plugin-dir resolution must be portable: env override wins, and a missing install
    fails loudly (sys.exit) instead of silently passing a non-existent path to --plugin-dir."""
    fails = 0
    sentinel = "/tmp/ponytail-selftest-plugin-dir"
    os.environ["PONYTAIL_PLUGIN_DIR"] = sentinel
    try:
        ok_env = _plugin_dir("ponytail") == sentinel
    finally:
        del os.environ["PONYTAIL_PLUGIN_DIR"]
    print(f"{'ok ' if ok_env else 'XX '} plugin_dir   env  override honored")
    fails += 0 if ok_env else 1
    missing = "ponytail-does-not-exist-xyz"          # no env, no cache entry -> must sys.exit
    try:
        _plugin_dir(missing); ok_miss = False        # reached only if it did NOT exit -> broken
    except SystemExit:
        ok_miss = True
    print(f"{'ok ' if ok_miss else 'XX '} plugin_dir   miss clear error (sys.exit)")
    return fails + (0 if ok_miss else 1)

def _tree_kill(proc):
    """Tree-kill one timed-out cell, never a blanket kill (that would also take down this
    Claude Code session). Windows: taskkill /T walks the child PIDs. POSIX has no taskkill,
    so the cell runs in its own session (Popen start_new_session) and we kill the group."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError: pass  # already exited

def _stop_active_cells():
    with ACTIVE_LOCK:
        procs = list(ACTIVE_PROCS)
    for proc in procs:
        _tree_kill(proc)

def _selftest_kill():
    """tree-kill must actually terminate a cell that outran its timeout, on this platform."""
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                         start_new_session=(os.name != "nt"))
    _tree_kill(p)
    try: ok = p.wait(timeout=10) is not None
    except subprocess.TimeoutExpired: ok = False; p.kill()
    print(f"{'ok ' if ok else 'XX '} tree_kill    terminates a timed-out cell")
    return 0 if ok else 1

def chat_code_loc(text):
    """LOC of fenced code blocks in a chat answer: (total incl comments, code-only)."""
    total = code = 0
    for b in re.findall(r"```[a-zA-Z0-9_+-]*\r?\n(.*?)```", text or "", re.S):
        for ln in b.splitlines():
            s = ln.strip()
            if not s: continue
            total += 1
            if not s.startswith(("#", "//", "*", "/*", "*/")): code += 1
    return total, code

def _disabled_user_skills_config():
    """Disable user skills outside CODEX_HOME so raw benchmark arms cannot be contaminated."""
    root = Path.home() / ".agents" / "skills"
    paths = sorted(root.rglob("SKILL.md")) if root.is_dir() else []
    entries = ", ".join(
        f"{{ path = {json.dumps(str(path.resolve()))}, enabled = false }}" for path in paths
    )
    return f"skills.config=[{entries}]"

def score_workspace(task_id, arm, model, workdir: Path):
    meta, result_text = {"infra_valid": False}, ""
    cj = workdir / "_codex.jsonl"
    if cj.exists():
        try:
            usage, messages, turns, external_skill_reads = {}, [], 0, []
            for line in cj.read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                if event.get("type") == "item.completed":
                    item = event.get("item") or {}
                    if item.get("type") == "agent_message": messages.append(str(item.get("text", "")))
                    if item.get("type") == "command_execution":
                        command = str(item.get("command", "")).replace("\\", "/")
                        if "/.codex/skills/" in command or "/.agents/skills/" in command:
                            external_skill_reads.append(command[:300])
                elif event.get("type") == "turn.completed":
                    turns += 1
                    if isinstance(event.get("usage"), dict): usage = event["usage"]
            cached = int(usage.get("cached_input_tokens", 0))
            fresh = max(int(usage.get("input_tokens", 0)) - cached, 0)
            output = int(usage.get("output_tokens", 0))
            cost = (fresh * FRESH_INPUT_USD_M + cached * CACHED_INPUT_USD_M + output * OUTPUT_USD_M) / 1_000_000
            duration_path = workdir / "_duration_ms.txt"
            returncode_path = workdir / "_returncode.txt"
            returncode = int(returncode_path.read_text()) if returncode_path.exists() else -1
            infra_valid = returncode == 0 and bool(usage) and bool(messages) and not external_skill_reads
            meta = {"cost": cost, "duration_ms": int(duration_path.read_text()) if duration_path.exists() else None,
                    "turns": turns, "denials": 0, "out_tokens": output, "in_tokens": fresh,
                    "cache_tokens": cached, "infra_valid": infra_valid, "returncode": returncode,
                    "external_skill_reads": external_skill_reads}
            if external_skill_reads:
                meta["infra_error"] = "external skill contamination"
            result_text = messages[-1] if messages else ""
        except Exception as exc:
            meta = {"infra_valid": False, "infra_error": str(exc)[:200]}
    surgical = not TASKS[task_id].get("open") and not TASKS[task_id].get("fixture")
    stats = git_diff_stats(workdir) if TASKS[task_id].get("fixture") else code_stats(workdir, selfcheck_as_test=surgical)
    # open/explain tasks answer in the chat, not a file. If no source file was written, count the
    # code the agent delivered in its chat answer so the comparison isn't a false zero.
    if TASKS[task_id].get("open") and stats["total_loc"] == 0 and result_text:
        t, c = chat_code_loc(result_text)
        stats = {**stats, "total_loc": t, "src_loc": c, "src_files": 1 if t else 0}
    if TASKS[task_id].get("fixture"):
        sc = {"correct": 1 if stats.get("total_loc", 0) > 0 else 0, "safe": 1, "reason": "git-diff"}
    else:
        sc = TASKS[task_id]["score"](workdir)
    return {"task": task_id, "arm": arm, "model": model, **sc, **stats, **meta}

def run_cell(task_id, arm, model, workdir: Path):
    task = TASKS[task_id]
    if task.get("fixture"):                            # copy a real repo in; record what was seeded
        fx = Path(task["fixture"])                     # absolute path, or a name under fixtures/
        if not fx.is_absolute(): fx = Path(__file__).resolve().parent / "fixtures" / task["fixture"]
        shutil.copytree(fx, workdir, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("node_modules", ".git", "build", "dist",
                                                       "dist-ssr", ".vite", "*.log", "__pycache__",
                                                       "storage", ".venv", "venv", ".pytest_cache",
                                                       "*.mp4", "*.mp3", "*.wav", "*.mov",
                                                       "*service-account*.json",
                                                       "nul", "con", "prn", "aux",
                                                       "DatePicker*.tsx", "DatePicker*.jsx"))
        manifest = sorted(str(p.relative_to(workdir)).replace("\\", "/")
                          for p in workdir.rglob("*") if p.is_file())
        (workdir / "_fixture_files.json").write_text(json.dumps(manifest), encoding="utf-8")
    for fn, content in task.get("seed", {}).items():
        (workdir / fn).write_text(content, encoding="utf-8")
    if task.get("fixture"): _git_snapshot(workdir)     # baseline commit -> diff the agent's changes
    codex = shutil.which("codex")
    if not codex: sys.exit("codex CLI not found on PATH")
    extra = ARMS[arm]()
    prompt = ((extra + "\n\n") if extra else "") + NO_RUN + "\n\nTask:\n" + task["prompt"]
    scratch = workdir / ".agent-tmp"
    scratch.mkdir(mode=0o700, exist_ok=True)
    safe_path = f"{Path(sys.executable).parent}:/usr/local/bin:/usr/bin:/bin"
    shell_values = {"PATH": safe_path, "HOME": str(scratch), "TMPDIR": str(scratch),
                    "PYTHONDONTWRITEBYTECODE": "1"}
    assignments = ", ".join(f"{key} = {json.dumps(value)}" for key, value in shell_values.items())
    cmd = [codex, "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
           "--disable", "plugins", "--disable", "shell_snapshot", "--skip-git-repo-check",
           "--sandbox", "workspace-write",
           "--model", MODELS[model], "--config", 'model_reasoning_effort="medium"',
           "--config", _disabled_user_skills_config(),
           "--config", 'shell_environment_policy.inherit="none"', "--config",
           f"shell_environment_policy.set={{{assignments}}}", "--cd", str(workdir), "-"]
    prompt_path = scratch / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    out_path, err_path = workdir / "_codex.jsonl", workdir / "_codex.stderr.txt"
    # stdout goes to a file, never a PIPE. A timed-out process is killed by its isolated group.
    try:
        with tempfile.TemporaryDirectory(prefix="sarathi-codex-home-") as home_dir, \
             open(prompt_path, "rb") as si, open(out_path, "wb") as so, open(err_path, "wb") as se:
            isolated_home = Path(home_dir)
            auth_path = ORIGINAL_CODEX_HOME / "auth.json"
            if auth_path.is_file():
                copied_auth = isolated_home / "auth.json"
                shutil.copy2(auth_path, copied_auth)
                copied_auth.chmod(0o600)
            process_env = os.environ.copy()
            process_env["CODEX_HOME"] = str(isolated_home)
            started = time.monotonic()
            proc = subprocess.Popen(cmd, cwd=str(workdir), stdin=si, stdout=so, stderr=se,
                                    env=process_env, start_new_session=(os.name != "nt"))
            with ACTIVE_LOCK:
                ACTIVE_PROCS.add(proc)
            try:
                proc.wait(timeout=CELL_TIMEOUT)
            except subprocess.TimeoutExpired:
                _tree_kill(proc)
                try: proc.wait(timeout=15)
                except Exception: pass
                se.write(f"\n[KILLED after {CELL_TIMEOUT}s timeout]".encode())
            finally:
                with ACTIVE_LOCK:
                    ACTIVE_PROCS.discard(proc)
            (workdir / "_duration_ms.txt").write_text(str(round((time.monotonic() - started) * 1000)))
            (workdir / "_returncode.txt").write_text(str(proc.returncode if proc.returncode is not None else -1))
    except Exception as e:
        err_path.write_text(str(e)[:300], encoding="utf-8")
    return score_workspace(task_id, arm, model, workdir)

def aggregate(results):
    groups = defaultdict(list)
    for r in results: groups[(r["task"], r["arm"], r["model"])].append(r)
    rows = []
    for (t, a, m), cells in sorted(groups.items()):
        n = len(cells)
        costs = [c["cost"] for c in cells if c.get("cost") is not None]
        loc_cells = [c for c in cells if c.get("total_loc", 0) > 0]   # LOC only where code was delivered
        nl = len(loc_cells)
        rows.append({"task": t, "arm": a, "model": m, "n": n,
                     "safe_rate": round(sum(c["safe"] for c in cells) / n, 3),
                     "correct_rate": round(sum(c["correct"] for c in cells) / n, 3),
                     "wrote_file_rate": round(nl / n, 3),
                     "total_loc_median": statistics.median(c["total_loc"] for c in loc_cells) if nl else 0,
                     "src_loc_median": statistics.median(c["src_loc"] for c in loc_cells) if nl else 0,
                     "total_loc_max": max((c["total_loc"] for c in loc_cells), default=0),
                     "src_files_median": statistics.median(c["src_files"] for c in loc_cells) if nl else 0,
                     "wrote_tests_rate": round(sum(1 for c in cells if c.get("test_files", 0) > 0) / n, 3),
                     "cost_mean": round(statistics.mean(costs), 4) if costs else None,
                     "out_tokens_mean": (round(statistics.mean([c["out_tokens"] for c in cells if c.get("out_tokens") is not None]))
                                         if any(c.get("out_tokens") is not None for c in cells) else None),
                     "total_tokens_mean": (round(statistics.mean([(c.get("in_tokens") or 0) + (c.get("out_tokens") or 0) + (c.get("cache_tokens") or 0)
                                                                   for c in cells if c.get("out_tokens") is not None]))
                                           if any(c.get("out_tokens") is not None for c in cells) else None),
                     "time_s_mean": (round(statistics.mean([c["duration_ms"] / 1000 for c in cells if c.get("duration_ms") is not None]), 1)
                                     if any(c.get("duration_ms") is not None for c in cells) else None)})
    return rows

def print_table(rows):
    by = defaultdict(list)
    for r in rows: by[(r["task"], r["model"])].append(r)
    for (task, model), rs in sorted(by.items()):
        print(f"\n=== {task}  ({model}, n={rs[0]['n']}) ===")
        print(f"  {'arm':16} {'wrote%':>7} {'correct':>8} {'LOC':>7} {'tot_tok':>9} {'$/run':>8} {'time_s':>7}")
        for r in sorted(rs, key=lambda x: x["arm"]):
            c = ("$" + format(r["cost_mean"], ".4f")) if r["cost_mean"] is not None else "-"
            tt = r.get("total_tokens_mean"); t = r.get("time_s_mean")
            print(f"  {r['arm']:16} {r.get('wrote_file_rate', 1.0):>7} {r['correct_rate']:>8} "
                  f"{r['total_loc_median']:>7} {(tt if tt is not None else '-'):>9} {c:>8} "
                  f"{(t if t is not None else '-'):>7}")

def rescore(run_dir):
    run_dir = Path(run_dir)
    if not run_dir.exists():                     # accept "<stamp>" or "runs/<stamp>" from any cwd
        run_dir = RUNS_DIR / run_dir.name
    results = []
    for ws in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        parts = ws.name.split("__")
        if len(parts) != 4 or parts[0] not in TASKS: continue
        tid, arm, model, _r = parts
        results.append(score_workspace(tid, arm, model, ws))
    rows = aggregate(results)
    (run_dir / "results.json").write_text(json.dumps({"rescored": True, "results": results}, indent=2), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print_table(rows)
    print(f"\nrescored {len(results)} cells from {run_dir}")

def _codex_version():
    try: return subprocess.run([shutil.which("codex"), "--version"], capture_output=True, text=True).stdout.strip()
    except Exception: return "unknown"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--rescore", help="recompute metrics from a kept run dir (no API)")
    ap.add_argument("--task", help="single task id")
    ap.add_argument("--all", action="store_true", help="all tasks")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--model", help="single model (shorthand for --models)")
    ap.add_argument("--models", default="gpt-5.5", help="comma list: gpt-5.5")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--workers", type=int, default=4, help="cells to run concurrently (default 4; cells are fully isolated)")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(1 if selftest() else 0)
    if args.rescore:
        return rescore(args.rescore)
    if selftest():
        sys.exit("instruments broken; refusing to spend on the API")

    task_ids = (list(TASKS) if args.all
                else ([t.strip() for t in args.task.split(",")] if args.task else []))
    if not task_ids: sys.exit("give --task <id> (comma list ok), --all, or --rescore <dir>")
    arms = [a.strip() for a in args.arms.split(",")]
    models = [m.strip() for m in (args.model or args.models).split(",")]
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = RUNS_DIR / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    cells = [(tid, arm, model, r)
             for tid in task_ids for model in models for arm in arms for r in range(args.runs)]
    total = len(cells)
    results, done = [], 0

    def _one(spec):
        tid, arm, model, r = spec
        ws = out_dir / f"{tid}__{arm}__{model}__{r}"
        ws.mkdir(parents=True, exist_ok=True)
        return run_cell(tid, arm, model, ws)

    print(f"running {total} cells, {args.workers} at a time", flush=True)
    # Cells are fully isolated, so they parallelize safely. Infrastructure failure triggers
    # targeted process-group cleanup for every active cell.
    aborted = False
    infra_failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_one, s): s for s in cells}
        for fut in concurrent.futures.as_completed(futs):
            tid, arm, model, r = futs[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"task": tid, "arm": arm, "model": model, "error": str(e)[:200]}
            results.append(res)
            done += 1
            if not res.get("infra_valid", False):
                infra_failures += 1
            print(f"  [{done}/{total}] {tid} / {arm} / {model} #{r}  "
                  f"LOC={res.get('total_loc')} "
                  f"tok={(res.get('in_tokens') or 0) + (res.get('out_tokens') or 0) + (res.get('cache_tokens') or 0)} "
                  f"cost=${res.get('cost')} time={round((res.get('duration_ms') or 0) / 1000, 1)}s "
                  f"correct={res.get('correct')}", flush=True)
            (out_dir / "results.json").write_text(json.dumps(
                {"date": stamp, "models": {m: MODELS[m] for m in models},
                 "codex": _codex_version(), "results": results}, indent=2), encoding="utf-8")
            if infra_failures >= MAX_INFRA_FAILURES:
                aborted = True
                _stop_active_cells()
                for pending in futs:
                    pending.cancel()
                break

    if aborted:
        print(f"\naborted after {infra_failures} infrastructure-invalid cells; partial run is not scorable")
        raise SystemExit(2)

    rows = aggregate(results)
    (out_dir / "summary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print_table(rows)
    print(f"\nwrote {out_dir}/results.json + summary.json ({len(results)} cells)")

if __name__ == "__main__":
    main()
