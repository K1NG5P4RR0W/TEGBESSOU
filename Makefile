# Raccourcis (les cibles seront étoffées à mesure que le code arrive)
.PHONY: up migrate seed-kb seed-modules create-admin healthcheck lint test

up:            ## Démarre la stack de dev
	docker compose up -d
migrate:       ## Applique les migrations
	@echo "TODO: docker compose run --rm gateway alembic upgrade head"
seed-kb:       ## Ingère la base de connaissances
	@echo "TODO: ingestion RAG"
seed-modules:  ## Charge le registre des modules
	@echo "TODO: seed module_registry"
create-admin:  ## Crée le premier compte admin + MFA
	@echo "TODO: création admin"
healthcheck:   ## Vérifie l'état des composants
	@echo "TODO: DB / Redis / Gateway / mTLS / worker / proxy"
lint:
	@echo "TODO: ruff + eslint"
test:
	@echo "TODO: pytest + tests front"
