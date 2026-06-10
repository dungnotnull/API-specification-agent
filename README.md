# speckit-enhanced

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AI-Powered API Specification Agent**

Describe an API in plain English → get a production-ready OpenAPI 3.0 spec, validated, with test stubs — in seconds.

## Features

- 🚀 **NL → OpenAPI Generation**: Describe your API in plain English, get valid OpenAPI 3.0 YAML
- ✅ **7-Gate Completeness Validator**: Ensures your spec meets production standards
- 🧪 **Auto Test Stubs**: Generate pytest and Jest test stubs with edge cases
- 🎯 **Pattern Advisor**: Get REST vs GraphQL vs AsyncAPI recommendations with rationale
- 🔁 **Code → Spec**: Reverse-engineer OpenAPI specs from existing code (CodeT5+)
- 📚 **Self-Learning**: Knowledge base auto-updates from ArXiv, Semantic Scholar, and GitHub

## Quick Start

### Docker (Recommended)

```bash
# Clone and setup
git clone https://github.com/your-org/speckit-enhanced.git
cd speckit-enhanced

# Configure
cp config/.env.example .env
# Edit .env with your API keys

# Start
docker-compose up -d

# Generate your first spec
python -m agent.main generate -d "User CRUD API with JWT auth" -o user-api.yaml
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Configure
export ANTHROPIC_API_KEY=your-key-here

# Generate spec
python -m agent.main generate -d "User CRUD API with JWT auth" -o user-api.yaml

# Validate existing spec
python -m agent.main validate user-api.yaml

# Generate test stubs
python -m agent.main test-stubs user-api.yaml
```

## CLI Commands

```bash
# Generate spec from natural language
speckit generate -d "E-commerce product catalog API" -o catalog.yaml

# Generate spec from code
speckit reverse app.py --language python

# Validate spec
speckit validate catalog.yaml

# Generate test stubs
speckit test-stubs catalog.yaml --framework both

# Get pattern advice
speckit advise -u "Real-time analytics dashboard"

# Start API server
speckit serve --start-scheduler
```

## REST API

Start the server:

```bash
python -m agent.main serve
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/generate` | Generate OpenAPI from NL |
| POST | `/api/v1/generate-from-code` | Reverse-engineer spec from code |
| POST | `/api/v1/validate` | Validate spec (7-gate check) |
| POST | `/api/v1/test-stubs` | Generate test stubs |
| POST | `/api/v1/advise` | Get pattern recommendation |
| POST | `/api/v1/knowledge/update` | Trigger knowledge update |
| GET | `/api/v1/cost` | View LLM API costs |
| GET | `/metrics` | Prometheus metrics |

### Example: Generate Spec

```bash
curl -X POST http://localhost:8020/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{
    "description": "User profile CRUD API with JWT authentication",
    "base_url": "https://api.example.com/v1",
    "api_version": "1.0.0"
  }'
```

## Architecture

```
User Input → SpecKitOrchestrator → Modules → Output

Modules:
├── nl_spec_generator.py    — NL → OpenAPI + CodeT5+ reverse
├── spec_validator.py       — 7-gate completeness check
├── test_stub_generator.py  — pytest + Jest stubs
└── pattern_advisor.py      — REST/GraphQL/AsyncAPI advisor

Tools:
├── llm_client.py           — Claude/OpenAI/Ollama with fallback
├── hf_model_manager.py     — CodeT5+, BGE-large, MiniLM, Reranker
└── knowledge_updater.py   — ArXiv/Semantic Scholar/GitHub crawler
```

## 7-Gate Validator

| Gate | Severity | Description |
|------|----------|-------------|
| STATUS_CODES | ERROR | All operations have 2xx + 4xx responses |
| ERROR_SCHEMAS | ERROR | Error responses use reusable schema |
| AUTH_COVERAGE | ERROR | Security scheme defined |
| DESCRIPTIONS | WARN | All paths/operations have descriptions |
| EXAMPLES | WARN | At least one example per operation |
| VERSIONING | ERROR | API version declared |
| SECURITY_SCHEMES | ERROR | Security schemes match definitions |

## Configuration

See `config/.env.example` for all configuration options:

```bash
# LLM APIs (primary: Claude, fallback: OpenAI, offline: Ollama)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Offline mode
PRIVACY_MODE=false
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3

# Data directories
DATA_DIR=./data
MODELS_DIR=./models
```

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/your-org/speckit-enhanced.git
cd speckit-enhanced

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v
```

### Project Structure

```
speckit-enhanced/
├── agent/               # Core agent code
│   ├── main.py          # CLI entry point
│   ├── orchestrator.py  # Decision loop
│   ├── modules/         # Domain modules
│   ├── memory/          # SQLite persistence
│   └── config.py        # Configuration
├── tools/               # LLM + HF integration
├── config/              # Configuration files
├── docker/              # Docker setup
├── tests/               # Test suite
├── data/                # Runtime data (SQLite, models)
└── docs/                # Documentation
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Acknowledgments

- **Spec Kit**: Forked from [Spec Kit](https://github.com/stoplightio/spectral) (v6.11.1)
- **HuggingFace**: CodeT5+, BGE-large, MiniLM models
- **Claude**: Anthropic's Claude API for primary LLM
- **OpenAI**: GPT-4o fallback

## Support

- 📖 Documentation: [DEPLOYMENT.md](DEPLOYMENT.md), [PROJECT-detail.md](PROJECT-detail.md)
- 🐛 Issues: [GitHub Issues](https://github.com/your-org/speckit-enhanced/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/your-org/speckit-enhanced/discussions)

---

**Built with ❤️ by the speckit-enhanced team**
