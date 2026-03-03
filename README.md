# Children's Story Studio — Multi-Agent Orchestration

A full-stack application that uses **Microsoft Agent Framework** to orchestrate
multiple AI agents for generating illustrated children's stories.

## Architecture

```
React + Vite (frontend)
        ↕  SSE stream  ↕
    FastAPI (backend)
        ↕  workflow  ↕
   Agent Framework WorkflowBuilder
        │
        ├── OrchestratorAgent    — Creates the story outline
        ├── StoryArchitectAgent  — Writes page text & image prompts
        ├── ArtDirectorAgent     — Generates illustrations per page
        ├── StoryReviewerAgent   — Quality-checks the complete story
        └── DecisionExecutor     — Approves or loops for revisions
```

**Workflow graph:**

```
StoryRequest
     ↓
Orchestrator → StoryArchitect → ArtDirector → StoryReviewer → Decision
    ↑                                                             │
    └──────────── RevisionSignal (max 2 rounds) ─────────────────┘
                                                                  │
                                              yield_output → StoryResponse
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- An **Azure AI Foundry** project with:
  - A chat model deployment (e.g., `gpt-4o`)
  - An image generation deployment (e.g., `dall-e-3`)
- Azure CLI installed and logged in (`az login`) for `DefaultAzureCredential`

## Setup

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and fill in your Azure AI Foundry values
```

### 2. Frontend

```bash
cd frontend
npm install
```

## Running

**Terminal 1 — Backend:**
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

Or use the **"Full Stack"** compound launch configuration in VS Code (F5).

## Environment Variables

| Variable | Description |
|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Azure AI Foundry project endpoint URL |
| `FOUNDRY_MODEL_DEPLOYMENT_NAME` | Chat model deployment name (e.g., `gpt-4o`) |
| `FOUNDRY_IMAGE_MODEL_DEPLOYMENT_NAME` | Image generation deployment (e.g., `dall-e-3`) |
| `CORS_ORIGIN` | React dev server origin (default: `http://localhost:5173`) |

## Agent Descriptions

| Agent | Role |
|---|---|
| **OrchestratorAgent** | Transforms user input into a structured `StoryOutline` with character descriptions, page breakdowns, and the story arc. Handles revision requests from the reviewer. |
| **StoryArchitectAgent** | Writes the full narrative text and DALL-E image prompts for every page based on the outline. Ensures age-appropriate vocabulary (5–8 years). |
| **ArtDirectorAgent** | Calls the Azure OpenAI image generation API to produce one illustration per page. Embeds character descriptions for visual consistency. |
| **StoryReviewerAgent** | Reviews the complete illustrated story for character consistency, narrative coherence, age-appropriateness, moral integration, and art-text alignment. |
| **DecisionExecutor** | Routing logic — approves the story (yield output) or sends a `RevisionSignal` back to the Orchestrator (max 2 revision rounds). |
