COMPOSE := $(shell podman compose version >/dev/null 2>&1 && echo "podman compose" || echo "docker compose")

.PHONY: local-dev-build
local-dev-build:
	$(COMPOSE) build

.PHONY: local-dev-up
local-dev-up:
	$(COMPOSE) up -d --build

.PHONY: local-dev-down
local-dev-down:
	$(COMPOSE) down
