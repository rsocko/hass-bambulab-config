# Paperless-AI Setup with Ollama

This directory contains the Docker Compose configuration for setting up [Paperless-AI](https://github.com/clusterzx/paperless-ai) with Ollama for AI-powered document classification and semantic search.

## Overview

**Paperless-AI** is an AI-powered extension for Paperless-ngx that provides:

- 🔄 **Automated Document Processing** - Automatically classifies documents, assigns tags, correspondent, and document type
- 🧠 **RAG-Based AI Chat** - Natural language document search with semantic understanding
- 🏷️ **Smart Tagging** - Intelligent tagging based on document content
- ⚙️ **Manual Processing** - Web interface for manual review and processing

## Architecture

This setup includes two services:

1. **Ollama** - Local LLM runtime for privacy-focused AI processing
2. **Paperless-AI** - Document processing and RAG service that connects to Paperless-ngx

The services are connected via a Docker network, allowing Paperless-AI to communicate with Ollama for document analysis.

## Prerequisites

- Docker and Docker Compose installed
- Paperless-ngx instance running (can be on the same host or remote)
- At least 8GB RAM (16GB recommended for larger models)
- Paperless-ngx API token

## Quick Start

### 1. Configure Environment Variables

Copy the example environment file and configure it:

```bash
cp .env.example .env
nano .env  # or your preferred editor
```

**Required Configuration:**
```env
# Set your Paperless-ngx connection details
PAPERLESS_API_URL=http://your-paperless-host:8000/api
PAPERLESS_API_TOKEN=your_api_token_here
PAPERLESS_USERNAME=your_username
```

**Get Paperless-ngx API Token:**
1. Log in to your Paperless-ngx instance
2. Go to Settings → API Tokens
3. Create a new token or use an existing one

### 2. Start the Services

```bash
docker-compose up -d
```

This will:
- Pull and start the Ollama container
- Pull and start the Paperless-AI container
- Create persistent volumes for data storage
- Download the llama3.2 model (on first run)

### 3. Pull the Ollama Model

After Ollama starts, download your chosen model:

```bash
# Using the default llama3.2
docker exec -it ollama ollama pull llama3.2

# Or choose a different model (see recommended models below)
docker exec -it ollama ollama pull mistral
```

### 4. Access Paperless-AI

Open your browser and navigate to:
```
http://localhost:3000
```

Complete the initial setup through the web interface:
1. Configure your Paperless-ngx connection
2. Select your AI provider (Ollama)
3. Configure processing rules and tags

### 5. Restart to Build RAG Index

After completing the initial setup, restart the container to build the RAG index:

```bash
docker-compose restart paperless-ai
```

## Recommended Ollama Models

Based on community feedback and testing, here are recommended models for document processing:

| Model | Size | RAM Required | Notes |
|-------|------|--------------|-------|
| **llama3.2** | 3B | 8GB | Default, good balance of speed and accuracy |
| **mistral** | 7B | 8GB | Fast and accurate, great for general use |
| **phi3** | 3.8B | 4GB | Lightweight, runs on lower-end hardware |
| **glm4** | 9B | 16GB | Excellent for document handling (highly recommended) |
| **mistral-small:24b** | 24B | 32GB | Best performance, requires more resources |

To switch models:
1. Pull the new model: `docker exec -it ollama ollama pull <model-name>`
2. Update `OLLAMA_MODEL` in your `.env` file
3. Restart: `docker-compose restart paperless-ai`

## Configuration Options

### Document Processing

Control how documents are processed:

```env
# Scan for new documents every 30 minutes
SCAN_INTERVAL=*/30 * * * *

# Only process documents with specific tags
PROCESS_PREDEFINED_DOCUMENTS=yes
TAGS=pre-process

# Add a tag after AI processing
ADD_AI_PROCESSED_TAG=yes
AI_PROCESSED_TAG_NAME=ai-processed
```

### AI Provider Options

While this setup uses Ollama by default, Paperless-AI supports multiple AI providers:

- **Ollama** (default) - Local, privacy-focused
- **OpenAI** - Requires API key
- **Custom APIs** - DeepSeek, OpenRouter, etc.

To switch providers, update the `AI_PROVIDER` variable in `.env`.

## Integration with Existing Paperless Stack

If you already have a Paperless-ngx Docker Compose stack, you have two options:

### Option 1: Separate Stack (Recommended)

Keep this as a separate stack that connects to your existing Paperless-ngx:

1. Ensure Paperless-ngx is accessible from this stack
2. Update `PAPERLESS_API_URL` to point to your Paperless instance
3. If both stacks are on the same host, use `http://host.docker.internal:8000/api` or the actual host IP

### Option 2: Integrate into Existing Stack

Add the services to your existing Paperless docker-compose.yml:

1. Copy the `ollama` and `paperless-ai` service definitions
2. Add them to your existing compose file
3. Adjust network settings to use your existing network
4. Update `PAPERLESS_API_URL` to use service name: `http://paperless:8000/api`

## Usage

### Automatic Processing

Documents tagged with your configured tag (default: `pre-process`) will be automatically analyzed and classified.

### Manual Processing

Access the manual processing interface at:
```
http://localhost:3000/manual
```

This is useful for reviewing or manually processing sensitive documents.

### RAG Chat

Use the chat interface to search your documents using natural language:

```
"When did I sign my rental agreement?"
"What was the amount of the last electricity bill?"
"Which documents mention health insurance?"
```

## Monitoring

### Check Service Status

```bash
docker-compose ps
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f paperless-ai
docker-compose logs -f ollama
```

### Health Checks

Both services include health checks. You can monitor them with:

```bash
docker inspect paperless-ai | grep -A 10 Health
docker inspect ollama | grep -A 10 Health
```

## Troubleshooting

### Services Won't Start

1. Check logs: `docker-compose logs`
2. Verify port availability: `netstat -tuln | grep -E '3000|11434'`
3. Ensure Docker has sufficient resources allocated

### Connection to Paperless-ngx Fails

1. Verify `PAPERLESS_API_URL` is correct
2. Test API token: 
   ```bash
   curl -H "Authorization: Token YOUR_TOKEN" http://your-paperless:8000/api/documents/
   ```
3. Check network connectivity between containers

### Ollama Model Download Fails

1. Check disk space: `df -h`
2. Manually pull model: `docker exec -it ollama ollama pull llama3.2`
3. Try a smaller model like `phi3` if RAM is limited

### RAG Index Issues

After first setup or model change, restart to rebuild RAG index:
```bash
docker-compose restart paperless-ai
```

## Maintenance

### Update Services

```bash
docker-compose pull
docker-compose up -d
```

### Backup Data

Important directories to backup:
- `paperless_ai_data` volume - Contains application data and RAG index
- `ollama_data` volume - Contains downloaded models

```bash
# Backup volumes
docker run --rm -v paperless_ai_data:/data -v $(pwd):/backup alpine tar czf /backup/paperless-ai-backup.tar.gz /data
docker run --rm -v ollama_data:/data -v $(pwd):/backup alpine tar czf /backup/ollama-backup.tar.gz /data
```

### Clean Up

To remove all containers and volumes:
```bash
docker-compose down -v
```

⚠️ **Warning:** This will delete all data including the RAG index and downloaded models.

## Security Considerations

- 🔒 Both services run with `no-new-privileges` security option
- 🔒 Paperless-AI drops all Linux capabilities
- 🔐 Store API tokens securely in `.env` file (never commit to git)
- 🌐 Consider using a reverse proxy with SSL for production
- 🔒 Restrict network access to Ollama (port 11434) if not needed externally
- 👤 Run services with non-root users (PUID/PGID configured)

## Performance Tuning

### For Lower-End Systems

- Use smaller models: `phi3` or `llama3.2`
- Increase `SCAN_INTERVAL` to reduce CPU usage
- Disable RAG if not needed: `RAG_SERVICE_ENABLED=false`

### For High-Performance Systems

- Use larger models: `glm4` or `mistral-small:24b`
- Decrease `SCAN_INTERVAL` for faster processing
- Consider GPU acceleration for Ollama (requires additional Docker configuration)

## Additional Resources

- [Paperless-AI GitHub](https://github.com/clusterzx/paperless-ai)
- [Paperless-AI Wiki](https://github.com/clusterzx/paperless-ai/wiki)
- [Ollama Documentation](https://ollama.com/docs)
- [Ollama Model Library](https://ollama.com/library)
- [Paperless-ngx Documentation](https://docs.paperless-ngx.com/)

## Support

For issues specific to:
- **Paperless-AI**: [GitHub Issues](https://github.com/clusterzx/paperless-ai/issues)
- **Ollama**: [Ollama GitHub](https://github.com/ollama/ollama)
- **This Configuration**: Open an issue in this repository

## License

This configuration is provided as-is. Paperless-AI is licensed under MIT. See respective project repositories for full license details.
