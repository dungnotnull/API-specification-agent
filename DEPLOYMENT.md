# speckit-enhanced — Deployment Guide

## Quick Start

### Option 1: Docker Compose (Recommended)

```bash
# Copy environment template
cp config/.env.example .env

# Edit .env and add your API keys
# ANTHROPIC_API_KEY=your-key-here
# OPENAI_API_KEY=your-key-here

# Start the services
docker-compose up -d

# Check health
curl http://localhost:8020/health

# View logs
docker-compose logs -f speckit-agent
```

### Option 2: Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export ANTHROPIC_API_KEY=your-key

# Start the server
python -m agent.main serve --start-scheduler

# Or use the CLI
python -m agent.main generate -d "User CRUD API" -o user-api.yaml
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | No* | - | Claude API key (primary LLM) |
| `OPENAI_API_KEY` | No | - | OpenAI API key (fallback) |
| `OLLAMA_BASE_URL` | No | http://localhost:11434 | Ollama endpoint |
| `OLLAMA_MODEL` | No | llama3 | Ollama model to use |
| `PRIVACY_MODE` | No | false | Force Ollama only (no cloud APIs) |
| `DATA_DIR` | No | ./data | SQLite database location |
| `MODELS_DIR` | No | ./models | HF models cache location |
| `HOST` | No | 0.0.0.0 | Server bind address |
| `PORT` | No | 8020 | Server port |
| `LOG_LEVEL` | No | INFO | Logging level |

*At least one LLM API key required unless `PRIVACY_MODE=true`

### Using Ollama (Offline Mode)

```bash
# Start Ollama
docker-compose up -d ollama

# Pull the model
docker exec -it speckit-ollama ollama pull llama3

# Run in privacy mode
export PRIVACY_MODE=true
python -m agent.main serve
```

## Production Deployment

### Security Considerations

1. **API Keys**: Never commit `.env` file. Use secrets management in production
2. **Authentication**: Add authentication middleware for the FastAPI endpoints
3. **Rate Limiting**: Implement rate limiting for API endpoints
4. **TLS**: Use reverse proxy (nginx) with HTTPS in production

### Nginx Reverse Proxy

```nginx
server {
    listen 443 ssl http2;
    server_name speckit.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8020;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: speckit-agent
spec:
  replicas: 2
  selector:
    matchLabels:
      app: speckit-agent
  template:
    metadata:
      labels:
        app: speckit-agent
    spec:
      containers:
      - name: agent
        image: speckit-enhanced:latest
        ports:
        - containerPort: 8020
        env:
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: api-keys
              key: anthropic-key
        - name: DATA_DIR
          value: /app/data
        volumeMounts:
        - name: data
          mountPath: /app/data
        - name: models
          mountPath: /app/models
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: speckit-data
      - name: models
        persistentVolumeClaim:
          claimName: speckit-models
---
apiVersion: v1
kind: Service
metadata:
  name: speckit-agent
spec:
  selector:
    app: speckit-agent
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8020
  type: LoadBalancer
```

## Monitoring

### Health Check

```bash
curl http://localhost:8020/health
# Response: {"status": "ok", "service": "speckit-enhanced", "version": "1.0.0"}
```

### Prometheus Metrics

```bash
curl http://localhost:8020/metrics
# Returns: speckit_generate_requests_total, speckit_validate_requests_total, etc.
```

### Cost Tracking

```bash
# CLI
python -m agent.main cost-report

# API
curl http://localhost:8020/api/v1/cost
```

## Troubleshooting

### Issue: "All providers failed"

**Cause**: No API keys configured or all APIs unreachable

**Fix**:
1. Check `.env` file has valid keys
2. Verify network connectivity
3. Set `PRIVACY_MODE=true` to use Ollama only

### Issue: "CUDA out of memory"

**Cause**: GPU memory exhausted

**Fix**:
1. Set `MODELS_DIR` to location with more space
2. Use CPU-only mode: `torch.cuda.is_available() = False`
3. Reduce model sizes in config

### Issue: "FAISS index not loading"

**Cause**: Index file corrupted or missing

**Fix**:
```bash
rm -f data/pattern_advisor_faiss.index
rm -f data/pattern_advisor_texts.json
# Will rebuild on next run
```

## Backup and Recovery

### Backup

```bash
# Backup database and index
tar -czf speckit-backup-$(date +%Y%m%d).tar.gz \
    data/ \
    models/ \
    SECOND-KNOWLEDGE-BRAIN.md
```

### Recovery

```bash
# Restore
tar -xzf speckit-backup-20240610.tar.gz
```

## Upgrading

```bash
# Pull latest code
git pull

# Rebuild Docker image
docker-compose build

# Restart with data preserved
docker-compose up -d
```

## Support

- Issues: https://github.com/your-org/speckit-enhanced/issues
- Documentation: See `PROJECT-detail.md` and `CLAUDE.md`
