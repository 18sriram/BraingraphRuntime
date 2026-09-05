.PHONY: up down build logs backend frontend

up:
	docker compose up --build

down:
	docker compose down -v

build:
	docker compose build

logs:
	docker compose logs -f

backend:
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

frontend:
	cd frontend && npm install
