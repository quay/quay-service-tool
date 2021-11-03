.PHONY: local-dev-clean
local-dev-clean:
	./clean.sh

.PHONY: local-dev-build-frontend
local-dev-build-frontend:
	cd frontend; npm install --quiet --no-progress --ignore-engines --no-save

.PHONY: local-dev-build
local-dev-build:
	docker-compose build

.PHONY: local-dev-up
local-dev-up:
	make local-dev-clean
	make local-dev-build-frontend
	docker-compose up -d

.PHONY: local-dev-down
local-dev-down:
	docker-compose down
