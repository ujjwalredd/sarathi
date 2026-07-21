.PHONY: help build vendor test validate check pilot bench compare compare-codex fidelity codex-baseline codex-auto codex-explicit install uninstall clean all

# Stdlib only, by design: a benchmark that is hard to install is a benchmark
# nobody re-runs, and re-running is the whole point of this repo.
PY ?= python3
JOBS ?= 4
N ?= 1

help:
	@echo "sarathi make targets"
	@echo ""
	@echo "  build       regenerate bundled references and all local benchmark arms"
	@echo "  vendor      refresh pinned Caveman and Ponytail source snapshots"
	@echo "  test        run the unit suite (no API calls, no cost)"
	@echo "  validate    check repo invariants (no API calls, no cost)"
	@echo "  check       test + validate. run this before every commit"
	@echo ""
	@echo "  COSTS REAL MONEY: each call starts a full model session"
	@echo "  fidelity    do the verse pointers resolve?  (9 x N calls)"
	@echo "  pilot       fidelity N=3 + all five arms N=1 (~67 calls)"
	@echo "  bench       codebook ablation A-E           (40 x N calls)"
	@echo "  compare     Claude: control, competitors, deployed Sarathi"
	@echo "  compare-codex  same comparison through Codex"
	@echo "  codex-baseline  installed-skill control; run before installing Sarathi"
	@echo "  codex-auto      installed skill with normal automatic routing"
	@echo "  codex-explicit  installed skill explicitly requested in every prompt"
	@echo ""
	@echo "  install     install the plugin into Claude Code from this directory"
	@echo "  uninstall   remove it"
	@echo "  clean       remove __pycache__ and local run artifacts"
	@echo ""
	@echo "  vars: N=$(N) JOBS=$(JOBS) PY=$(PY)"

build:
	@test -f /tmp/gita_verse.json || curl -sL -o /tmp/gita_verse.json \
		https://raw.githubusercontent.com/gita/gita/main/data/verse.json
	$(PY) bench/build_anchors.py --source /tmp/gita_verse.json
	$(PY) bench/build_arms.py

vendor:
	$(PY) bench/vendor_competitors.py

test:
	$(PY) -m unittest discover bench -v

validate:
	$(PY) bench/validate.py

check: test validate

fidelity:
	$(PY) bench/fidelity.py --n $(N) --jobs $(JOBS)

pilot:
	$(PY) bench/fidelity.py --n 3 --jobs $(JOBS)
	$(PY) bench/run.py --arms A B C D E --n 1 --jobs $(JOBS)

bench:
	$(PY) bench/run.py --arms A B C D E --n $(N) --jobs $(JOBS)

compare:
	$(PY) bench/run.py --arms A F G H --tasks reasoning minimalism --n $(N) --jobs $(JOBS)

compare-codex:
	$(PY) bench/run.py --backend codex --model gpt-5.5 --arms A F G H \
		--tasks reasoning minimalism --n $(N) --jobs $(JOBS)

codex-baseline:
	$(PY) bench/codex_skill.py --condition baseline --expect-skill absent --n $(N) --jobs $(JOBS)

codex-auto:
	$(PY) bench/codex_skill.py --condition sarathi --expect-skill present --n $(N) --jobs $(JOBS)

codex-explicit:
	$(PY) bench/codex_skill.py --condition sarathi-explicit --expect-skill present --n $(N) --jobs $(JOBS)

install:
	claude plugin marketplace add $(CURDIR)
	claude plugin install sarathi@sarathi

uninstall:
	claude plugin uninstall sarathi@sarathi || true
	claude plugin marketplace remove sarathi || true

clean:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name '.DS_Store' -delete 2>/dev/null || true
	rm -rf bench/arms results

all: build check
