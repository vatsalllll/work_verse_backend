# WorkVerse AI — Backend Monorepo

> A gamified AI-powered virtual office platform where teams collaborate through avatars, consult AI agents, and stay in sync — all in a 2D pixel-art world.

---

## What is WorkVerse AI?

WorkVerse AI reimagines remote work as a gamified 2D office. Teams interact via pixel-art avatars in a virtual workspace, with AI consulting agents positioned at desks — each trained on your team's actual data (Slack history, GitHub PRs, Notion docs, Jira tickets).

Instead of switching between 10 apps, you walk up to the AI agent for your team and ask it anything. It knows your codebase, your decisions, your team's context.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    WorkVerse AI Platform                     │
├─────────────────┬───────────────────┬───────────────────────┤
│  workverse-ui   │  workverse-api    │  workverse-mobile     │
│  Phaser.js 2D   │  FastAPI + RAG    │  React Native (Expo)  │
│  Web Game       │  LangGraph        │  Mobile Game          │
└────────┬────────┴────────┬──────────┴────────────┬──────────┘
         │                 │                         │
         └─────────────────▼─────────────────────────┘
                     WebSocket + REST API
                    ┌──────────────────┐
                    │  MongoDB Atlas   │  ← Vector Store + Chat History
                    │  Redis           │  ← Presence, Cache, PubSub
                    │  LangGraph       │  ← Agent Workflow Engine
                    │  Groq / OpenAI   │  ← LLM Providers
                    └──────────────────┘
```

---

## Repository Structure

```
work_verse_backend/
├── workverse-api/          # FastAPI backend — RAG pipeline, LangGraph agents, WebSocket
│   ├── src/philoagents/    # Core agent logic
│   │   ├── application/    # LangGraph workflows, agent state, graph builder
│   │   ├── domain/         # Agent models, factories, prompts
│   │   ├── infrastructure/ # MongoDB, embeddings, retrieval, API routes
│   │   └── config/         # Settings, environment
│   ├── data/               # Agent knowledge base documents
│   ├── notebooks/          # Data ingestion and RAG experiments
│   ├── Dockerfile
│   └── pyproject.toml
│
├── workverse-ui/           # Phaser.js 2D web game (web frontend)
│   ├── src/
│   │   ├── scenes/         # Phaser game scenes (Boot, Game, UI)
│   │   ├── classes/        # Character, DialogueManager, GameMap
│   │   └── services/       # WebSocket API service
│   ├── public/             # Game assets (tilesets, sprites, tilemaps)
│   ├── Dockerfile
│   └── package.json
│
├── static/                 # Shared static assets
├── docker-compose.yml      # Full stack local dev environment
├── Makefile                # Developer shortcuts
└── WORKVERSE_ARCHITECTURE.md  # Full system architecture
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Web Game** | Phaser.js 3.x, JavaScript |
| **Mobile Game** | React Native, Expo ([separate repo](https://github.com/vatsalllll/work_verse_mobile)) |
| **Backend API** | FastAPI, Python 3.12 |
| **Agent Orchestration** | LangGraph |
| **RAG Pipeline** | MongoDB Atlas Vector Search, HybridSearch (BM25 + vector) |
| **LLM** | Groq (Llama 3.3 70B, primary) + OpenAI GPT-4o (fallback) |
| **Embeddings** | all-MiniLM-L6-v2 (text) |
| **Database** | MongoDB Atlas |
| **Real-time** | FastAPI WebSockets |
| **Infrastructure** | Docker, docker-compose |
| **Package Manager** | uv (Python), npm (JS) |

---

## AI Agents

WorkVerse ships with pre-built AI consulting agents, each with a distinct personality and knowledge domain:

| Agent | Role | Specialty |
|---|---|---|
| **Socrates** | Philosophy Lead | Critical thinking, questioning assumptions |
| **Aristotle** | Systems Architect | Logic, structure, organization |
| **Plato** | Vision Strategist | Abstract thinking, big-picture planning |
| **Ada Lovelace** | Engineering Lead | Algorithms, computation |
| **Alan Turing** | AI Research Lead | Machine learning, computation theory |
| **Noam Chomsky** | Language Lead | NLP, communication patterns |
| **Descartes** | Problem Solver | Systematic doubt, first principles |

Each agent is powered by a **LangGraph workflow** with:
- **Short-term memory** via conversation history summarization
- **Long-term memory** via MongoDB Atlas Vector Search (RAG)
- **Streaming responses** over WebSocket

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Python 3.12+ with `uv`
- Node.js 18+ with `npm`
- Groq API key (free at [console.groq.com](https://console.groq.com))

### 1. Clone and configure

```bash
git clone https://github.com/vatsalllll/work_verse_backend.git
cd work_verse_backend
cp workverse-api/.env.example workverse-api/.env
# Add your API keys to workverse-api/.env
```

### 2. Start the full stack

```bash
docker compose up -d
```

This starts:
- **MongoDB Atlas Local** on port `27017`
- **WorkVerse API** on port `8000`
- **WorkVerse Web UI** on port `8080`

### 3. Seed agent knowledge

```bash
cd workverse-api
make create-long-term-memory
```

### 4. Open the game

Visit [http://localhost:8080](http://localhost:8080). Walk up to any philosopher agent and press **Space** to start a conversation.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/chat` | Send a message to an agent (HTTP fallback) |
| `WS` | `/ws/chat` | Stream agent responses via WebSocket |
| `POST` | `/reset-memory` | Clear conversation history for an agent |
| `GET` | `/health` | Health check |

### WebSocket Protocol

```json
// Client → Server
{ "philosopher_id": "ada_lovelace", "message": "How do I optimize this algorithm?" }

// Server → Client (streaming)
{ "streaming": true }
{ "chunk": "Let's think about..." }
{ "response": "Full response text", "streaming": false }
```

---

## Mobile App

The mobile frontend (React Native / Expo) is in a **separate repo**:  
👉 **[github.com/vatsalllll/work_verse_mobile](https://github.com/vatsalllll/work_verse_mobile)**

---

## Environment Variables

```env
# workverse-api/.env
GROQ_API_KEY=your_groq_key
OPENAI_API_KEY=your_openai_key          # optional fallback
MONGO_DATABASE_HOST=mongodb://localhost:27017
MONGO_DATABASE_NAME=workverse
```

---

## License

MIT License — see [LICENSE](./workverse-api/LICENSE)
