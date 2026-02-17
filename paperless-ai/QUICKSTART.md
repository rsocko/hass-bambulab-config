# Paperless-AI Quick Start

Get up and running with Paperless-AI and Ollama in 5 minutes.

## Prerequisites Check

✅ Docker and Docker Compose installed  
✅ Paperless-ngx running (local or remote)  
✅ 8GB+ RAM available  
✅ Paperless-ngx API token ready  

## Installation Steps

### 1. Clone and Configure (2 minutes)

```bash
cd paperless-ai
cp .env.example .env
```

Edit `.env` and set these **required** values:
```env
PAPERLESS_API_URL=http://YOUR_PAPERLESS_HOST:8000/api
PAPERLESS_API_TOKEN=your_token_from_paperless
PAPERLESS_USERNAME=your_username
```

### 2. Start Services (1 minute)

```bash
docker-compose up -d
```

Wait for services to start (check with `docker-compose ps`).

### 3. Download Model (1-2 minutes)

```bash
docker exec -it ollama ollama pull llama3.2
```

This downloads the default AI model (~2GB).

### 4. Access & Configure (1 minute)

Open http://localhost:3000 in your browser.

Complete the initial setup wizard:
1. Confirm Paperless-ngx connection
2. Verify Ollama is detected
3. Set document processing preferences

### 5. Build RAG Index

After completing setup, restart to build the RAG index:
```bash
docker-compose restart paperless-ai
```

## Verification

✅ Check services are running:
```bash
docker-compose ps
```

Both should show "Up" status with "(healthy)" indicator.

✅ Test document processing:
1. Tag a document in Paperless-ngx with `pre-process`
2. Wait 30 minutes or trigger manual processing at http://localhost:3000/manual
3. Check if document gets auto-tagged and titled

✅ Test RAG chat:
1. Open http://localhost:3000
2. Try asking: "What documents do I have?"

## Next Steps

- **Change Model**: See [README.md](README.md#recommended-ollama-models) for model options
- **Customize Tags**: Edit `TAGS` in `.env` to control which documents are processed
- **Tune Performance**: Adjust `SCAN_INTERVAL` based on your needs
- **Enable Auto-tagging**: Set `ADD_AI_PROCESSED_TAG=yes` to track processed documents

## Common Issues

**"Cannot connect to Paperless"**
→ Check `PAPERLESS_API_URL` and `PAPERLESS_API_TOKEN` in `.env`

**"Ollama not responding"**
→ Wait for model download: `docker logs ollama -f`

**"Port already in use"**
→ Change `PAPERLESS_AI_PORT` in `.env` or stop conflicting service

## Getting Help

- Full documentation: [README.md](README.md)
- Paperless-AI issues: https://github.com/clusterzx/paperless-ai/issues
- Configuration questions: Check the troubleshooting section in README.md

---

**Time to first document processed: ~5-35 minutes** (setup + first scan interval)
