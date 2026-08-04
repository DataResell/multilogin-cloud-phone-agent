# Multilogin cloud-phone agent — common tasks.
# Fresh clone flow:  make setup  ->  cp .env.example .env (fill in)  ->  make doctor  ->  make dry-run  ->  make demo
PY := .venv/bin/python

.PHONY: help setup doctor dry-run demo test clean

help:
	@echo "make setup    - create .venv and install dependencies"
	@echo "make doctor   - validate environment + credentials (no minutes spent)"
	@echo "make dry-run  - walk the full flow with no network/device"
	@echo "make demo     - real end-to-end demo (starts a phone; needs a filled .env)"
	@echo "make test     - run offline regression tests (no network/device)"
	@echo "make clean    - remove .venv and runtime artifacts"

setup:
	./scripts/setup.sh

doctor:
	$(PY) -m mlxphone.session doctor

dry-run:
	$(PY) -m mlxphone.session demo --dry-run --phone demo-phone

demo:
	$(PY) -m mlxphone.session demo

test:
	$(PY) tests/test_hardening.py

clean:
	rm -rf .venv .mlxphone results logs mlxphone/__pycache__ __pycache__
