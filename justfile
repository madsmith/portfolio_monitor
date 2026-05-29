default: dev-live

dev-live:
    portfolio-monitor run --dev-live

install:
    uv tool install . --reinstall