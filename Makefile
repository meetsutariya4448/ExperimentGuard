PY ?= python
DBT_DIR = dbt/experimentguard

.PHONY: help setup ingest analyze dbt build test lint fmt app export dashboard-warehouse all clean holdout

help:
	@echo "setup    create the Python 3.12 environment"
	@echo "ingest   download the archive and load DuckDB"
	@echo "analyze  run the decision engine (exploratory + confirmatory)"
	@echo "dbt      build the dimensional model and run all dbt tests"
	@echo "build    analyze + dbt"
	@echo "test     pytest suite"
	@echo "lint     ruff check + format check"
	@echo "app      launch the Streamlit application"
	@echo "export   write the Power BI star schema to exports/"
	@echo "dashboard-warehouse  build the compact deployment warehouse"
	@echo "all      ingest + build + test + export"
	@echo "holdout  final, once-only holdout evaluation (records to policy/HOLDOUT_LOG.md)"

setup:
	conda env create -f environment.yml || conda env update -f environment.yml

ingest:
	PYTHONPATH=src $(PY) -m experimentguard.ingest

analyze:
	PYTHONPATH=src $(PY) -m experimentguard.analyze --partition exploratory
	PYTHONPATH=src $(PY) -m experimentguard.analyze --partition confirmatory

# The holdout is once-only evidence: it is not part of `make all` by design.
holdout:
	PYTHONPATH=src $(PY) -m experimentguard.analyze --partition holdout --confirm-final

dbt:
	cd $(DBT_DIR) && dbt build --profiles-dir .

build: analyze dbt

test:
	PYTHONPATH=src $(PY) -m pytest

lint:
	ruff check .
	ruff format --check .

fmt:
	ruff check --fix .
	ruff format .

app:
	PYTHONPATH=src $(PY) -m streamlit run app/Home.py

export:
	PYTHONPATH=src $(PY) -m experimentguard.exports

dashboard-warehouse:
	$(PY) scripts/build_dashboard_warehouse.py

all: ingest build test export

clean:
	rm -rf $(DBT_DIR)/target $(DBT_DIR)/logs .pytest_cache .ruff_cache exports
	find . -name __pycache__ -type d -exec rm -rf {} +
