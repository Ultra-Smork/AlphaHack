.PHONY: run dev backend frontend test check install reset-db

run: backend

dev:
	./scripts/dev.sh

reset-db:
	python scripts/reset_db.py

backend:
	python -m app.main

frontend:
	npm --prefix Alpha-front run dev

test:
	pytest

check:
	python -m pytest
	npm --prefix Alpha-front run lint
	npm --prefix Alpha-front run build

install:
	python -m pip install -r requirements-dev.txt
	npm --prefix Alpha-front install
