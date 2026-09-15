# Raccourcis de développement. `make up` construit et démarre la stack.
.PHONY: up down logs ps lint test health migrate seed-kb seed-modules create-admin

up:            ## Construit et démarre la stack de dev
	docker compose up -d --build
down:          ## Arrête la stack
	docker compose down
logs:          ## Suit les logs
	docker compose logs -f
ps:            ## État des conteneurs
	docker compose ps

lint:          ## Lint + typage des deux services
	cd gateway && uv run ruff check . && uv run mypy .
	cd api_pentest && uv run ruff check . && uv run mypy .
test:          ## Tests des deux services
	cd gateway && uv run pytest
	cd api_pentest && uv run pytest
health:        ## Vérifie les endpoints /health (stack démarrée)
	@curl -fsS http://127.0.0.1:8001/health && echo "  <- gateway OK"
	@curl -fsS http://127.0.0.1:8000/health && echo "  <- api_pentest OK"

# --- Cibles à implémenter dans les briques suivantes ---
migrate:       ## (B0.2) Applique les migrations
	@echo "TODO B0.2 : alembic upgrade head"
seed-kb:       ## (Phase 2) Ingère la base de connaissances
	@echo "TODO"
seed-modules:  ## (B0.2) Charge le registre des modules
	@echo "TODO"
create-admin:  ## (B0.3) Crée le premier compte admin + MFA
	@echo "TODO"
