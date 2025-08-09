## Quickstart (template)

```bash
# 1) Create venv and install
make setup
make install

# 2) Run lint & tests
make lint
make test

# 3) (Optional) Start Postgres locally
make docker-up

# 4) Run the app (example)
python tools/run_pipeline_cli.py --symbol BTCUSDT --timeframe 1h --days-back 3 --store-db
```

> Note: This repository uses a minimal CI (GitHub Actions) that runs ruff, black and pytest on PRs.
