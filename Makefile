PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: venv install seed mock operator ui test smoke demo package

venv:
	python3.12 -m venv .venv

install: venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m playwright install chromium

seed:
	$(PYTHON) -m mock_company.seed --reset

mock:
	$(PYTHON) -m uvicorn mock_company.app:app --host 127.0.0.1 --port 8001 --reload

operator:
	$(PYTHON) -m uvicorn server.api:app --host 127.0.0.1 --port 8000 --reload

ui:
	cd ui && npm install && npm run dev -- --host 127.0.0.1

test:
	$(PYTHON) -m pytest -q

smoke:
	$(PYTHON) scripts/smoke.py

demo:
	$(PYTHON) scripts/demo.py

package:
	$(PYTHON) scripts/package.py
