# Paperless-AI Deployment Decision

## Issue Requirements

The issue asked to:
1. Setup and connect paperless-ai (https://github.com/clusterzx/paperless-ai)
2. Consider if this should go in its own stack or be part of the paperless stack
3. Connect to ollama

## Decision: Standalone Stack

**We chose to implement paperless-ai as a standalone stack.**

### Rationale

1. **Repository Context**: This is a Home Assistant configuration repository, not a Paperless-ngx deployment repository. There is no existing Paperless docker-compose stack in this repo.

2. **Flexibility**: A standalone stack can:
   - Be deployed independently on any host
   - Connect to Paperless-ngx regardless of how it's deployed
   - Be started/stopped without affecting Paperless
   - Be upgraded independently

3. **Clean Separation**: Keeps the AI processing layer separate from the document management layer, following microservices principles.

4. **Easy Integration**: Can still be integrated with an existing Paperless stack later if needed (see ADVANCED.md for instructions).

## What Was Implemented

### Directory Structure
```
paperless-ai/
├── docker-compose.yml     # Service definitions for ollama + paperless-ai
├── .env.example           # Configuration template
├── .gitignore            # Exclude sensitive data
├── README.md             # Complete setup guide
├── QUICKSTART.md         # 5-minute quick start
└── ADVANCED.md           # Advanced configuration scenarios
```

### Services Included

1. **Ollama** (port 11434)
   - Local LLM runtime
   - Runs AI models for document processing
   - Persistent volume for model storage
   - Health checks configured

2. **Paperless-AI** (port 3000)
   - Document classification service
   - RAG-based semantic search
   - Web interface for manual processing
   - Connects to Ollama for AI inference
   - Connects to Paperless-ngx for document access

### Network Architecture

```
┌─────────────────────────────────────┐
│   Paperless-AI Stack                │
│                                     │
│  ┌──────────────┐  ┌─────────────┐ │
│  │   Ollama     │←─│ Paperless-AI│ │
│  │  (port 11434)│  │ (port 3000) │ │
│  └──────────────┘  └──────┬──────┘ │
│                           │         │
└───────────────────────────┼─────────┘
                            │
                            ↓ (API)
                   ┌─────────────────┐
                   │  Paperless-ngx  │
                   │  (port 8000)    │
                   └─────────────────┘
                   (Existing instance)
```

## Connection to Ollama

✅ **Fully Implemented**

The docker-compose.yml includes:
- Ollama service with persistent storage
- Paperless-AI configured to connect to Ollama via `OLLAMA_API_URL=http://ollama:11434`
- Docker network allowing services to communicate
- Health checks for both services

### Default Model: llama3.2

We selected llama3.2 (3B) as the default model because:
- Good balance of speed and accuracy for document processing
- Runs on 8GB RAM (accessible to most users)
- Recommended by the paperless-ai community
- Supports multiple languages

Note: The issue mentioned "carver-mini" but this model doesn't exist in the Ollama ecosystem. We interpreted this as a request for a compact/mini model and chose llama3.2 which fits that description.

### Alternative Models Documented

The documentation includes instructions for:
- **mistral** (7B) - Fast and accurate
- **phi3** (3.8B) - Lightweight for low-end systems
- **glm4** (9B) - Best accuracy, highly recommended by users
- **mistral-small:24b** (24B) - Enterprise-grade

## How to Deploy

### Quick Start (5 minutes)
```bash
cd paperless-ai
cp .env.example .env
# Edit .env with your Paperless-ngx API details
docker-compose up -d
docker exec -it ollama ollama pull llama3.2
```

Open http://localhost:3000 and complete the setup wizard.

### Full Documentation

- **README.md** - Complete setup, configuration, troubleshooting
- **QUICKSTART.md** - Rapid deployment guide
- **ADVANCED.md** - Integration scenarios, model selection, performance tuning

## Integration Options

While deployed as standalone, the documentation includes instructions for:

1. **Standalone Deployment** (default)
   - Connect to remote Paperless-ngx
   - Minimal changes to existing setup

2. **Integrated Deployment** (optional)
   - Add services to existing Paperless docker-compose
   - Shared network for faster communication
   - See ADVANCED.md for detailed instructions

## Features

✅ Automatic document classification  
✅ Smart tagging based on content  
✅ Correspondent extraction  
✅ Document date extraction  
✅ RAG-based semantic search  
✅ Natural language queries  
✅ Manual processing interface  
✅ Multiple AI provider support  
✅ Security hardening  
✅ Health monitoring  

## Deployment Flexibility

This implementation provides maximum flexibility:

- Can be deployed on the same host as Paperless-ngx
- Can be deployed on a separate host
- Can be integrated into existing Paperless stack later
- Can be upgraded/modified without affecting Paperless
- Can switch AI models without downtime

## Security

The implementation includes:
- Non-root user execution (PUID/PGID)
- Dropped Linux capabilities
- no-new-privileges security option
- .gitignore for sensitive files
- Environment-based secrets management
- Health check monitoring

## Next Steps

1. User reviews the implementation
2. User configures .env with their Paperless-ngx credentials
3. User deploys the stack
4. User tests document processing
5. User tunes model selection and processing rules based on their needs

## Summary

We successfully implemented paperless-ai as a **standalone stack** with:
- Complete ollama integration
- Comprehensive documentation
- Flexible deployment options
- Security best practices
- Multiple configuration scenarios

The standalone approach provides the most flexibility while keeping the option open to integrate with an existing Paperless stack if needed.
