.PHONY: dev backend frontend test install install-backend install-frontend

# Run backend + frontend together (needs `npm i -g concurrently`, or run the two targets in separate shells).
dev:
	@echo "Run 'make backend' and 'make frontend' in two shells (or install concurrently)."
	@command -v concurrently >/dev/null 2>&1 && concurrently -n api,web "make backend" "make frontend" || (echo "concurrently not found — use two shells" && exit 1)

backend:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && pytest -q

install: install-backend install-frontend

install-backend:
	cd backend && pip install -r requirements.txt

install-frontend:
	cd frontend && npm install
