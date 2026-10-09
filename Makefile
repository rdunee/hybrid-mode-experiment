PYTHON ?= python3
.PHONY: test matrix pilot analyze clean
matrix:
	$(PYTHON) -m orchestrator.run_experiment --matrix-only --output configs/stage1
pilot:
	$(PYTHON) -m orchestrator.run_experiment
analyze:
	$(PYTHON) -m analysis.pipeline --raw data/raw --output data/results
test:
	$(PYTHON) -m unittest discover -s tests -v
clean:
	./topology/cleanup.sh
