.PHONY: help build test validate check pilot bench fidelity install uninstall clean all

# Stdlib only, by design: a benchmark that is hard to install is a benchmark
# nobody re-runs, and re-running is the whole point of this repo.
PY ?= python3
JOBS ?= 4
N ?= 1

help:
	@echo "sarathi — make targets"
	@echo ""
	@echo "  build       regenerate reference/anchors.json and all five arms"
	@echo "  test        run the unit suite (no API calls, no cost)"
	@echo "  validate    check repo invariants (no API calls, no cost)"
	@echo "  check       test + validate. run this before every commit"
	@echo ""
	@echo "  COSTS REAL MONEY — each call is a full Claude Code session:"
	@echo "  fidelity    do the verse pointers resolve?  (9 x N calls)"
	@echo "  pilot       fidelity N=3 + all five arms N=1 (~67 calls)"
	@echo "  bench       full run, set N=5 or higher     (40 x N calls)"
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

install:
	claude plugin marketplace add $(CURDIR)
	claude plugin install sarathi@sarathi

uninstall:
	claude plugin uninstall sarathi@sarathi || true
	claude plugin marketplace remove sarathi || true

clean:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name '.DS_Store' -delete 2>/dev/null || true
	@echo "note: results/ is kept — published numbers must stay reproducible"

all: build check
