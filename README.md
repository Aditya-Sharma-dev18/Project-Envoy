# Project Envoy 🏛️

**Autonomous Alumni Intelligence & Relational Sync Engine**

Project Envoy is a production-grade backend architecture that autonomously reconciles stale alumni database records by dispatching rate-calibrated outreach messages and parsing unstructured human replies into verified structured data using Large Language Models (LLMs).

## Architecture Highlights
- **Rate-Limited Dispatch:** Uses Celery + Redis Token Buckets to strictly enforce a maximum of 20 outbound messages per 24-hour cycle, neutralizing bot-detection bans.
- **Deterministic LLM Extraction:** Leverages `gpt-4o-mini` with Pydantic + Instructor to convert messy chat replies into strictly typed Postgres JSONB schemas.
- **Anti-Injection Security:** Inbound webhooks pass through a regex heuristic engine to block prompt injections before LLM inference.
- **Hybrid Async Workflows:** FastAPI handles immediate webhook handshakes (HTTP 202), offloading the heavy DB and LLM IO to background workers.

## Tech Stack
- **API Engine:** FastAPI, Uvicorn
- **Task Queue:** Celery, Redis
- **Database:** PostgreSQL (asyncpg pool)
- **AI & Parsing:** OpenAI, Instructor, Pydantic
- **Infrastructure:** Docker Compose

## Quickstart (Local Development)

1. Rename `.env.example` to `.env` and insert your Unipile and OpenAI keys.
2. Spin up the entire infrastructure:
   ```bash
   docker-compose up --build -d