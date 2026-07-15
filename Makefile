COMPOSE := $(shell podman compose version >/dev/null 2>&1 && echo "podman compose" || echo "docker compose")
SPAM_DEMO_SCRIPT := ./scripts/spam-ingress-local-demo.sh

.PHONY: local-dev-build
local-dev-build:
	$(COMPOSE) build

.PHONY: local-dev-up
local-dev-up:
	$(COMPOSE) up -d --build

.PHONY: local-dev-down
local-dev-down:
	$(COMPOSE) down

.PHONY: spam-demo-check spam-demo spam-demo-status spam-demo-down spam-demo-clean
spam-demo-check:
	$(SPAM_DEMO_SCRIPT) check

spam-demo:
	$(SPAM_DEMO_SCRIPT) demo

spam-demo-status:
	$(SPAM_DEMO_SCRIPT) status

spam-demo-down:
	$(SPAM_DEMO_SCRIPT) down

spam-demo-clean:
	$(SPAM_DEMO_SCRIPT) clean
