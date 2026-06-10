# speckit-enhanced Integration Guide

This guide explains how to integrate speckit-enhanced with your existing tools, agents, and workflows.

## Table of Contents

- [REST API Integration](#rest-api-integration)
- [CLI Integration](#cli-integration)
- [Python SDK Integration](#python-sdk-integration)
- [Cross-Agent Integration](#cross-agent-integration)
- [CI/CD Integration](#cicd-integration)
- [Monitoring Integration](#monitoring-integration)

## REST API Integration

### Basic Usage

The FastAPI server exposes endpoints for all major operations:

```python
import requests

BASE_URL = "http://localhost:8020"

# Generate spec from NL
response = requests.post(f"{BASE_URL}/api/v1/generate", json={
    "description": "User management API with JWT authentication",
    "base_url": "https://api.example.com/v1",
    "api_version": "1.0.0"
})
spec = response.json()
print(spec["spec_yaml"])
```

### Advanced: Streaming Generation

```python
import requests
import json

response = requests.post(
    f"{BASE_URL}/api/v1/generate",
    json={"description": "E-commerce API"},
    stream=True
)

for chunk in response.iter_content(chunk_size=20):
    print(chunk.decode(), end="", flush=True)
```

### Validate and Fix Specs

```python
# Validate spec
response = requests.post(f"{BASE_URL}/api/v1/validate", json={
    "spec_yaml": open("my-api.yaml").read()
})
result = response.json()

print(f"Score: {result['score']}")
print(f"Issues: {len(result['issues'])}")

# Generate test stubs only if score is acceptable
if result["score"] >= 0.7:
    stubs = requests.post(f"{BASE_URL}/api/v1/test-stubs", json={
        "spec_yaml": open("my-api.yaml").read(),
        "framework": "pytest"
    })
    print(stubs.json()["pytest_stubs"])
```

## CLI Integration

### Shell Scripts

```bash
#!/bin/bash
# auto-spec.sh - Generate spec from description

DESCRIPTION="$1"
OUTPUT="${2:-spec.yaml}"

python -m agent.main generate \
  --description "$DESCRIPTION" \
  --output "$OUTPUT" \
  --base-url "https://api.example.com/v1"

echo "Generated spec: $OUTPUT"
```

### Makefile Integration

```makefile
# Makefile for API spec management

.PHONY: spec validate test clean

spec: src/api_description.txt
	python -m agent.main generate \
		--description-file $< \
		--output openapi.yaml

validate: openapi.yaml
	python -m agent.main validate openapi.yaml

test: openapi.yaml
	python -m agent.main test-stubs openapi.yaml --framework both

clean:
	rm -f openapi.yaml tests/test_*.py tests/*.test.js
```

## Python SDK Integration

### Direct Module Import

```python
from agent.orchestrator import SpecKitOrchestrator
import asyncio

async def generate_spec():
    orchestrator = SpecKitOrchestrator()

    result = await orchestrator.generate_from_nl(
        description="User profile API with CRUD operations",
        base_url="https://api.example.com/v1",
        api_version="1.0.0"
    )

    print(f"Confidence: {result['confidence']:.2f}")
    print(f"Validation Score: {result['validation_score']:.2f}")
    print(result['spec_yaml'])

asyncio.run(generate_spec())
```

### Custom Workflow

```python
from agent.orchestrator import SpecKitOrchestrator
from agent.modules.spec_validator import SpecValidator
import asyncio
import yaml

async def custom_workflow():
    # Step 1: Generate spec
    orch = SpecKitOrchestrator()
    result = await orch.generate_from_nl(
        description="Real-time chat API",
        base_url="https://api.example.com/v1"
    )

    # Step 2: Check if AsyncAPI is recommended
    advisor_result = await orch.advise_pattern(
        use_case="Real-time chat with online status"
    )

    if advisor_result["recommendation"] == "AsyncAPI":
        print("Consider using AsyncAPI for real-time features")
        print(advisor_result["rationale"])

    # Step 3: Generate with explanations
    validator = SpecValidator()
    spec = yaml.safe_load(result["spec_yaml"])
    validation = await validator.validate(spec, generate_explanations=True)

    for issue in validation["issues"]:
        if issue["severity"] == "ERROR":
            print(f"Issue: {issue['message']}")
            print(f"Suggestion: {issue['suggestion']}")

asyncio.run(custom_workflow())
```

## Cross-Agent Integration

### With academic-research-enhanced

```python
"""
speckit-enhanced integration with academic-research-enhanced agent.
Automatically fetches latest API design papers for spec generation.
"""

from agent.orchestrator import SpecKitOrchestrator
from tools.knowledge_updater import KnowledgeUpdater
import asyncio

async def research_guided_generation():
    # Update knowledge from latest research
    updater = KnowledgeUpdater()
    update_result = await updater.run_update()
    print(f"Knowledge updated: {update_result['entries_added']} new papers")

    # Generate spec with latest research insights
    orch = SpecKitOrchestrator()
    result = await orch.generate_from_nl(
        description="GraphQL API for social network",
        base_url="https://api.example.com/v1"
    )

    return result

asyncio.run(research_guided_generation())
```

### With ai-benchmark-agent

```python
"""
Integration with ai-benchmark-agent for LLM performance tracking.
"""

from agent.orchestrator import SpecKitOrchestrator
import time
import asyncio

async def benchmark_generation():
    orch = SpecKitOrchestrator()

    descriptions = [
        "User CRUD API",
        "E-commerce catalog API",
        "Real-time chat API"
    ]

    results = []
    for desc in descriptions:
        start = time.time()
        result = await orch.generate_from_nl(description=desc)
        elapsed = time.time() - start

        results.append({
            "description": desc,
            "time_seconds": elapsed,
            "confidence": result["confidence"],
            "validation_score": result["validation_score"]
        })

    # Report to benchmark agent
    print("Benchmark Results:")
    for r in results:
        print(f"{r['description']}: {r['time_seconds']:.2f}s, score: {r['validation_score']:.2f}")

    return results

asyncio.run(benchmark_generation())
```

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/spec-validation.yml

name: API Spec Validation

on:
  pull_request:
    paths:
      - 'specs/**.yaml'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Validate specs
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          for spec in specs/*.yaml; do
            python -m agent.main validate "$spec"
          done

      - name: Generate test stubs
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          python -m agent.main test-stubs specs/api.yaml --framework pytest
```

### GitLab CI

```yaml
# .gitlab-ci.yml

stages:
  - validate
  - test

validate_specs:
  stage: validate
  script:
    - pip install -r requirements.txt
    - python -m agent.main validate specs/api.yaml
  only:
    changes:
      - specs/**/*.yaml

generate_tests:
  stage: test
  script:
    - pip install -r requirements.txt
    - python -m agent.main test-stubs specs/api.yaml
    - mv tests/test_api.yaml.py test_suite/
  artifacts:
    paths:
      - test_suite/
```

## Monitoring Integration

### Prometheus Metrics

The `/metrics` endpoint exports metrics in Prometheus format:

```prometheus
# HELP speckit_generate_requests_total Total number of spec generation requests
# TYPE speckit_generate_requests_total counter
speckit_generate_requests_total 42

# HELP speckit_validate_requests_total Total number of validation requests
# TYPE speckit_validate_requests_total counter
speckit_validate_requests_total 156
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "speckit-enhanced Metrics",
    "panels": [
      {
        "title": "Generation Requests",
        "targets": [
          {
            "expr": "rate(speckit_generate_requests_total[5m])"
          }
        ]
      },
      {
        "title": "Average Confidence Score",
        "targets": [
          {
            "expr": "avg(speckit_generation_confidence)"
          }
        ]
      }
    ]
  }
}
```

### Custom Metrics

```python
from agent.orchestrator import SpecKitOrchestrator

orch = SpecKitOrchestrator()
metrics = orch.get_prometheus_metrics()

# Send to your monitoring system
# requests.post("https://metrics.example.com/prometheus", data=metrics)
```

## Webhook Integration

### Slack Notifications

```python
import requests
import asyncio
from agent.orchestrator import SpecKitOrchestrator

SLACK_WEBHOOK = "https://hooks.slack.com/services/..."

def notify_slack(message):
    requests.post(SLACK_WEBHOOK, json={"text": message})

async def monitored_generation():
    orch = SpecKitOrchestrator()

    result = await orch.generate_from_nl(
        description="Payment processing API"
    )

    if result["validation_score"] < 0.7:
        notify_slack(f"⚠️ Low validation score: {result['validation_score']:.2f}")

    if result["confidence"] < 0.7:
        notify_slack(f"⚠️ Low generation confidence: {result['confidence']:.2f}")

    notify_slack(f"✅ Spec generated: {result['validation_score']:.2f} score")

asyncio.run(monitored_generation())
```

## Environment-Specific Configuration

### Development

```bash
# .env.development
ANTHROPIC_API_KEY=sk-dev-key
LOG_LEVEL=DEBUG
HOST=127.0.0.1
PORT=8020
```

### Production

```bash
# .env.production
ANTHROPIC_API_KEY=sk-prod-key
LOG_LEVEL=WARNING
HOST=0.0.0.0
PORT=8020
PRIVACY_MODE=false
```

### Testing

```bash
# .env.test
PRIVACY_MODE=true
OLLAMA_BASE_URL=http://localhost:11434
DATA_DIR=./test_data
MODELS_DIR=./test_models
```

## Troubleshooting Integration Issues

### Import Errors

If you encounter import errors:

```python
import sys
sys.path.insert(0, "/path/to/speckit-enhanced")

from agent.orchestrator import SpecKitOrchestrator
```

### Configuration Loading

```python
from agent.config import Config, set_config_path

# Load custom config
config = set_config_path("/path/to/custom_config.yaml")
```

### Async Context Management

```python
import asyncio
from agent.orchestrator import SpecKitOrchestrator

async def main():
    orch = SpecKitOrchestrator()
    try:
        result = await orch.generate_from_nl(description="My API")
        return result
    finally:
        # Cleanup if needed
        pass

asyncio.run(main())
```

## Support

For integration questions or issues:
- 📖 See [DEPLOYMENT.md](DEPLOYMENT.md) for deployment details
- 🐛 Report issues: [GitHub Issues](https://github.com/your-org/speckit-enhanced/issues)
- 💡 Discussions: [GitHub Discussions](https://github.com/your-org/speckit-enhanced/discussions)
