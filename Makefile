PYTHON=python3
PIP=$(PYTHON) -m pip

.PHONY: venv install mockdb run test

venv:
	$(PYTHON) -m venv .venv

install: venv
	. .venv/bin/activate && $(PIP) install -r requirements.txt

mockdb:
	$(PYTHON) scripts/generate_mock_data.py

run:
	DUCKDB_PATH=./data/akahu.duckdb $(PYTHON) dashboard/app.py

test:
	pytest -q tests/test_api.py
