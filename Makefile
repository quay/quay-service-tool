COMPOSE := $(shell podman compose version >/dev/null 2>&1 && echo "podman compose" || echo "docker compose")

.PHONY: local-dev-clean
local-dev-clean:
	./clean.sh

.PHONY: local-dev-build-frontend
local-dev-build-frontend:
	cd frontend; npm install --quiet --no-progress --ignore-engines --no-save

.PHONY: local-dev-build
local-dev-build:
	$(COMPOSE) build

.PHONY: local-dev-up
local-dev-up:
	make local-dev-clean
	make local-dev-build-frontend
	$(COMPOSE) up -d

.PHONY: local-dev-down
local-dev-down:
	$(COMPOSE) down
