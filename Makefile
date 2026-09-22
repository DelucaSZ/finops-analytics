.PHONY: setup up down logs test lint format

setup:
	cp .env.example .env

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

test:
	cd backend && pytest -q

lint:
	cd backend && ruff check .
	cd frontend && npm run lint

format:
	cd backend && ruff format .
	cd frontend && npm run format
