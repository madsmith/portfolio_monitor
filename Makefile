.PHONY: install-dev frontend dev dev-live run clean build

install-dev: frontend/node_modules
	uv pip install -e '.[dev]'

build: install-dev frontend


frontend: frontend/node_modules
	cd frontend && pnpm build

frontend/node_modules: frontend/package.json
	cd frontend && pnpm install

dev: frontend/node_modules
	portfolio-monitor run --dev

dev-live: frontend/node_modules
	portfolio-monitor run --dev-live

run: frontend
	portfolio-monitor

clean:
	rm -rf frontend/dist frontend/node_modules
