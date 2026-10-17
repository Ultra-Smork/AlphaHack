.PHONY: run test install db-up db-down

run:
	python -m app.main

test:
	pytest

install:
	python -m pip install -r requirements-dev.txt

db-up:
	docker compose up -d db

db-down:
	docker compose down
