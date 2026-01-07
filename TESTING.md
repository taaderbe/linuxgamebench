# Testing Guide

## Overview

Tests are split between two repositories:
- **Client repo (linuxgamebench):** Unit tests only
- **Server repo (linuxgamebenchserver):** Integration and E2E tests

## Running Tests

### Unit Tests (Client)

```bash
cd /path/to/linuxgamebench
source .venv/bin/activate
pytest tests/unit/ -v
```

### Integration/E2E Tests (Server)

```bash
cd /path/to/linuxgamebenchserver
source venv/bin/activate
TEST_STAGE=rc pytest tests/ -v
```

## Test Structure

### Client Repo
```
tests/
├── conftest.py       # Unit test fixtures
└── unit/             # Unit tests
    ├── test_auth.py
    ├── test_cli.py
    └── test_validation.py
```

### Server Repo
```
tests/
├── conftest.py           # Server fixtures (stage, auth)
├── e2e/                  # Playwright browser tests
│   ├── test_login_page.py
│   ├── test_main_page.py
│   └── ...
└── integration/          # API tests
    ├── test_api_auth.py
    ├── test_api_benchmarks.py
    └── test_my_benchmarks.py
```

## Test Stages

| Stage | IP | Use |
|-------|-----|-----|
| rc | 192.168.0.70 | **Default for tests** |
| dev | 192.168.0.126 | Development testing |
| preprod | 192.168.0.112 | Manual only |
| prod | - | **Never test here!** |

## Quick Reference

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/test_auth.py -v

# Run tests with coverage
pytest --cov=src/linux_game_benchmark --cov-report=html

# Run E2E tests in headed mode (see browser)
pytest tests/e2e/ --headed
```

## More Information

For detailed testing documentation, see:
- `.claude/docs/TESTING.md` (development docs)
- `TESTING_SECRETS.md` (test credentials - not in git)
