# Testing Guide - Linux Game Benchmark

This document describes how to run tests and the testing requirements for new features.

## Test Structure

```
tests/
├── conftest.py           # Shared pytest fixtures
├── e2e/                  # End-to-end UI tests
│   ├── __init__.py
│   └── test_overview_ui.py
└── unit/                 # Unit tests (future)
```

## Running Tests

### Prerequisites

1. Install dev dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

2. Install Playwright browsers:
   ```bash
   playwright install chromium
   ```

### Run All Tests

```bash
pytest
```

### Run Only E2E Tests

```bash
pytest tests/e2e/
```

### Run Specific Test File

```bash
pytest tests/e2e/test_overview_ui.py
```

### Run Tests with Verbose Output

```bash
pytest -v
```

### Run Tests with Coverage

```bash
pytest --cov=src/linux_game_benchmark --cov-report=html
```

### Run Tests in Headed Mode (see browser)

```bash
pytest --headed
```

### Run Tests with Slow Motion (for debugging)

```bash
pytest --slowmo=500
```

## Test Categories

### E2E Tests (tests/e2e/)

End-to-end tests use Playwright to test the generated HTML reports in a real browser.

Current test coverage:

| Test Class | Description |
|------------|-------------|
| `TestOverviewPageStructure` | Basic page elements (title, header, filters, table) |
| `TestFilterFunctionality` | Filter dropdowns and filtering logic |
| `TestFilterTags` | Active filter tags display and removal |
| `TestTableSorting` | Table column sorting |
| `TestDetailsPanel` | Expandable details panel |
| `TestTooltips` | Metric explanation tooltips |
| `TestResponsiveDesign` | Mobile/responsive layout |
| `TestNoDuplicateEntries` | Duplicate entry prevention |

## Writing New Tests

### Requirement: Tests for Every New Feature

**Every new feature MUST include corresponding tests.** This ensures:
- Features work as expected
- Regressions are caught early
- Documentation through test cases

### Test Naming Convention

- Test files: `test_<feature>.py`
- Test classes: `Test<Feature>`
- Test methods: `test_<specific_behavior>`

### Example: Adding Tests for a New Feature

If you add a new feature like "Export to CSV", create tests like this:

```python
# tests/e2e/test_export.py

class TestExportFeature:
    """Tests for the CSV export feature."""

    def test_export_button_visible(self, page: Page, overview_report_url: str):
        """Export button should be visible on the page."""
        page.goto(overview_report_url)
        export_btn = page.get_by_role("button", name="Export CSV")
        expect(export_btn).to_be_visible()

    def test_export_downloads_file(self, page: Page, overview_report_url: str):
        """Clicking export should download a CSV file."""
        page.goto(overview_report_url)

        with page.expect_download() as download_info:
            page.get_by_role("button", name="Export CSV").click()

        download = download_info.value
        assert download.suggested_filename.endswith(".csv")
```

### Test Checklist for New Features

Before submitting a new feature, ensure:

- [ ] Unit tests for new Python functions (if applicable)
- [ ] E2E tests for new UI elements
- [ ] Tests for happy path (normal usage)
- [ ] Tests for edge cases (empty data, invalid input)
- [ ] Tests for error handling
- [ ] All existing tests still pass

### Fixtures Available

| Fixture | Description |
|---------|-------------|
| `benchmark_results_dir` | Path to benchmark results directory |
| `overview_report_path` | Path to index.html |
| `overview_report_url` | file:// URL for browser testing |
| `page` | Playwright Page object (from pytest-playwright) |

## Continuous Integration

Tests should be run:
- Before every commit (locally)
- On every pull request (CI/CD)
- After regenerating reports

### Pre-commit Hook (Recommended)

Add to `.git/hooks/pre-commit`:

```bash
#!/bin/bash
pytest tests/e2e/ -x --tb=short
```

## Debugging Failed Tests

### Screenshot on Failure

Playwright automatically captures screenshots on test failure. Find them in:
```
test-results/
```

### Trace Viewer

For detailed debugging, run with tracing:

```bash
pytest --tracing=on
```

Then view traces:

```bash
playwright show-trace test-results/trace.zip
```

### Common Issues

1. **Browser not installed**: Run `playwright install chromium`
2. **Report not found**: Regenerate with `lgb report`
3. **Timeout errors**: Increase timeout or check if element exists

## Test Maintenance

- Review tests when changing features
- Update tests when UI changes
- Remove tests for removed features
- Keep tests focused and independent

---

## Manual Testing - Auth & Email

### Test-Szenarien

#### 1. Account Registration
- [ ] Email kommt an
- [ ] Verification Link funktioniert
- [ ] Account ist nach Verification aktiv

#### 2. Password Reset
- [ ] Reset-Email kommt an
- [ ] Reset-Link funktioniert
- [ ] Neues Passwort kann gesetzt werden
- [ ] Alte Sessions werden invalidiert

#### 3. Login Flow (CLI)
- [ ] Login erfolgreich
- [ ] Token wird gespeichert
- [ ] `lgb status` zeigt korrekten User

#### 4. Session Expiry
- [ ] Nach Token-Ablauf wird Login angeboten
- [ ] Upload funktioniert nach Re-Login

### Test Account

See `TESTING_SECRETS.md` (not in git) for test email credentials.
