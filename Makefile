# Raccourcis de développement.
.PHONY: up down logs ps lint test migrate revision health ready seed-kb seed-modules create-admin reset-admin

up:            ## Construit et démarre la stack (attend que la gateway soit "ready")
	docker compose up -d --build
down:          ## Arrête la stack
	docker compose down
logs:          ## Suit les logs
	docker compose logs -f
ps:            ## État des conteneurs
	docker compose ps

lint:          ## Lint + typage
	cd gateway && uv run ruff check . && uv run mypy app
	cd api_pentest && uv run ruff check . && uv run mypy .
test:          ## Tests
	cd gateway && uv run pytest
	cd api_pentest && uv run pytest

migrate:       ## Applique les migrations dans le conteneur gateway
	docker compose run --rm gateway alembic upgrade head
revision:      ## Crée une révision vide (usage : make revision m="message")
	docker compose run --rm gateway alembic revision -m "$(m)"

health:        ## /health des deux services
	@curl -fsS http://127.0.0.1:8001/health && echo "  <- gateway OK"
	@curl -fsS http://127.0.0.1:8000/health && echo "  <- api_pentest OK"
ready:         ## /health/ready de la gateway (DB + Redis)
	@curl -fsS http://127.0.0.1:8001/health/ready && echo

seed-kb:       ## (Phase 2) Ingère la base de connaissances
	@echo "TODO"
seed-modules:  ## (B0.4) Charge le registre des modules
	@echo "TODO"
create-admin:  ## Crée le premier compte admin (dans le conteneur gateway)
	docker compose run --rm gateway python -m app.admin
reset-admin:   ## Réinitialise le mot de passe admin
	docker compose run --rm gateway python -m app.reset_password
