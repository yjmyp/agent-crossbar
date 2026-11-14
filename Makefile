ifeq ($(OS),Windows_NT)
PYTHON := .venv/Scripts/python.exe
else
PYTHON := .venv/bin/python
endif

.PHONY: bootstrap demo verify security benchmark perf build

bootstrap:
	uv sync
	npm ci

demo:
	$(PYTHON) scripts/demo.py

security:
	$(PYTHON) -m agent_crossbar.security.cli --root backend/agent_crossbar --format sarif -o work/security.sarif

benchmark:
	$(PYTHON) scripts/security-benchmark.py --prepare

perf:
	$(PYTHON) scripts/security-perf.py --prepare

verify:
	npm run verify

build:
	npm run build
