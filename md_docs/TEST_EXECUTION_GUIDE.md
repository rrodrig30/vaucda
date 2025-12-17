# VAUCDA Test Execution Guide

## Quick Start

### Prerequisites

```bash
cd /home/gulab/PythonProjects/VAUCDA/backend

# Ensure Python 3.11+ is active
python --version

# Install all dependencies including test requirements
pip install -r requirements.txt
```

### Run Tests

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=app --cov=calculators --cov=rag --cov-report=html --cov-report=term

# View coverage in browser
xdg-open htmlcov/index.html
```

## Test Categories

### Unit Tests
```bash
pytest tests/ -m unit -v
```

### Integration Tests
```bash
pytest tests/ -m integration -v
```

### Security Tests
```bash
pytest tests/ -m security -v
```

### Calculator Tests
```bash
pytest tests/test_calculators/ -v
```

### API Tests
```bash
pytest tests/test_api/ -v
```

### Performance Tests
```bash
pytest tests/ -m performance -v
```

## Test Markers

- `@pytest.mark.unit` - Fast unit tests
- `@pytest.mark.integration` - Integration tests requiring services
- `@pytest.mark.e2e` - End-to-end workflow tests
- `@pytest.mark.security` - Security and HIPAA tests
- `@pytest.mark.performance` - Performance benchmarks
- `@pytest.mark.calculator` - Calculator accuracy tests
- `@pytest.mark.slow` - Tests taking > 1 second
- `@pytest.mark.api` - API endpoint tests
- `@pytest.mark.rag` - RAG pipeline tests
- `@pytest.mark.critical` - Critical path tests

## Continuous Integration

### Pre-commit Hook

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
echo "Running tests before commit..."
pytest tests/ -v --tb=short
if [ $? -ne 0 ]; then
    echo "Tests failed. Commit aborted."
    exit 1
fi
echo "All tests passed!"
```

### GitHub Actions

Create `.github/workflows/test.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r backend/requirements.txt
      - name: Run tests
        run: |
          cd backend
          pytest tests/ --cov=app --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Test Results Interpretation

### Success
```
======================== test session starts =========================
collected 150 items

tests/test_api/test_auth.py::TestAuthRegistration::test_register_new_user PASSED
tests/test_api/test_auth.py::TestAuthLogin::test_login_success PASSED
...
======================== 150 passed in 45.23s ========================
```

### Failure
```
FAILED tests/test_calculators/test_psa_kinetics.py::test_psav_calculation
```
- Review traceback
- Fix implementation or test
- Re-run: `pytest tests/test_calculators/test_psa_kinetics.py::test_psav_calculation -v`

### Coverage Report
```
Name                                 Stmts   Miss  Cover
--------------------------------------------------------
app/api/v1/auth.py                     125      5    96%
app/api/v1/calculators.py              98      8    92%
calculators/prostate/psa_kinetics.py   67      0   100%
--------------------------------------------------------
TOTAL                                 5234    423    92%
```

## Troubleshooting

### Import Errors
```bash
# Add backend to PYTHONPATH
export PYTHONPATH="/home/gulab/PythonProjects/VAUCDA/backend:$PYTHONPATH"
pytest tests/ -v
```

### Database Errors
```bash
# Ensure test database is clean
rm -f test.db
pytest tests/ -v
```

### Async Errors
```bash
# Ensure pytest-asyncio is installed
pip install pytest-asyncio
pytest tests/ --asyncio-mode=auto -v
```

## Best Practices

1. **Run tests frequently** - After every significant change
2. **Write tests first** - TDD approach for new features
3. **Keep tests fast** - Unit tests should be < 100ms
4. **Mock external services** - Use fixtures for LLMs, databases
5. **Test edge cases** - Boundary values, nulls, errors
6. **Document expected behavior** - Clear test names and docstrings
7. **Maintain high coverage** - Aim for 80%+ overall, 100% for critical paths
