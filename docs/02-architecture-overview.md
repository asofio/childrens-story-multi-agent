# Architecture Overview

[← Back to README](../README.md) | [Prerequisites & Setup](01-prerequisites-and-setup.md)

This document provides a deep dive into the system architecture, agent workflow, data flow, and streaming mechanism that powers Children's Story Studio.

---

## Table of Contents

- [System Overview](#system-overview)
- [High-Level Architecture](#high-level-architecture)
- [Backend Architecture](#backend-architecture)
  - [FastAPI Application](#fastapi-application)
  - [Agent Framework Workflow](#agent-framework-workflow)
  - [Agent Descriptions](#agent-descriptions)
  - [Workflow Graph](#workflow-graph)
  - [Key Concepts](#key-concepts)
- [Frontend Architecture](#frontend-architecture)
  - [Component Tree](#component-tree)
  - [Components](#components)
- [Data Flow](#data-flow)
  - [Data Models](#data-models)
  - [Request-Response Lifecycle](#request-response-lifecycle)
- [SSE Streaming Architecture](#sse-streaming-architecture)
  - [Backend Event Translation](#backend-event-translation)
  - [Frontend Event Consumption](#frontend-event-consumption)
  - [SSE Event Types](#sse-event-types)
- [Project Structure](#project-structure)

---

## System Overview

Children's Story Studio is a three-tier application:

```
┌─────────────────────────────────────────────────────────────────┐
│                       React + Vite Frontend                     │
│  (StoryForm → ProgressTracker → StoryBook)                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │  SSE Stream (POST /api/generate-story)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                            │
│  (main.py → StoryGenerator → EventSourceResponse)               │
└───────────────────────────┬─────────────────────────────────────┘
                            │  Async workflow execution
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              Microsoft Agent Framework Workflow                 │
│  (WorkflowBuilder → Executors → Signals → Events)               │
└───────────────┬───────────────────────────────┬─────────────────┘
                │                               │
                ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────────┐
│  Azure AI Foundry        │    │  Azure OpenAI (Image Gen)    │
│  (GPT-5.2)               │    │  (gpt-image-1.5)             │
└──────────────────────────┘    └──────────────────────────────┘
```

---

## High-Level Architecture

The application follows a clear separation of concerns:

- **Frontend (React + Vite):** Collects user input, displays real-time generation progress, and renders the final storybook. Communicates with the backend via a single SSE-streamed POST request.
- **Backend (FastAPI + Python):** Exposes REST/SSE endpoints, manages the Agent Framework workflow, translates framework events into SSE messages, and coordinates all Azure AI service calls.
- **Agent Framework (Microsoft Agent Framework):** Provides the orchestration layer — defining the workflow graph, managing agent execution order, handling signals (revision loops), and emitting events for progress tracking.
- **Azure AI Services:** GPT-5.2 for text generation (story outlines, narratives, reviews) and gpt-image-1.5 for illustration generation.

---

## Backend Architecture

### FastAPI Application

**Entry point:** `backend/app/main.py`

The backend exposes two endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Health check — returns `{"status": "ok"}` |
| `/api/generate-story` | POST | Accepts a `StoryRequest` body; returns an SSE stream (`EventSourceResponse`) with real-time progress events and the final story |

CORS is configured to allow requests from the frontend dev server (`localhost:5173`, `localhost:5174`, and the configurable `CORS_ORIGIN`).

A single `StoryGenerator` instance is created at module level and shared across requests.

### Agent Framework Workflow

**File:** `backend/app/workflow.py`

The workflow is built using `WorkflowBuilder` from Microsoft Agent Framework. It defines:

- **Linear edges:** Orchestrator → StoryArchitect → ArtDirector
- **Conditional branch:** If `SKIP_STORY_REVIEWER` is `false`, includes ArtDirector → StoryReviewer → Decision. If `true`, routes ArtDirector → Decision directly.
- **Back-edge (revision loop):** Decision → Orchestrator via `RevisionSignal`
- **Terminal:** Decision calls `ctx.yield_output()` when the story is approved or the revision budget is exhausted.
- **Max iterations:** 30 (set on the workflow builder to allow for revision loops)

The workflow is instantiated as a **module-level singleton** (`story_workflow`) at import time.

### Agent Descriptions

| Agent | Executor ID | LLM-Backed? | File | Role |
|---|---|---|---|---|
| **OrchestratorAgent** | `orchestrator` | Yes | `agents/orchestrator.py` | Transforms the user's `StoryRequest` into a structured `StoryOutline` with character descriptions, page breakdowns, and story arc. Has two handlers: one for the initial request and one for revision requests (triggered by `RevisionSignal`). Tracks revision count in shared state. |
| **StoryArchitectAgent** | `story_architect` | Yes | `agents/story_architect.py` | Receives the `StoryOutline` and writes the full narrative text plus detailed DALL-E image prompts for every page. Produces a `StoryDraft`. Emits per-page `page_content` progress events. Ensures age-appropriate vocabulary (5–8 years). |
| **ArtDirectorExecutor** | `art_director` | Yes (image) | `agents/art_director.py` | Receives the `StoryDraft` and generates illustrations using Azure OpenAI image generation. Creates: 1 cover image + N story page images + 1 "The End" image. Uses `asyncio.Semaphore(5)` for concurrent generation (max 5 parallel image requests). All images returned as base64 data URIs (1024×1024, PNG). |
| **StoryReviewerAgent** | `story_reviewer` | Yes | `agents/story_reviewer.py` | Reviews the illustrated `StoryDraft` across 5 categories: character consistency, narrative coherence, age-appropriateness, moral integration, and art-text alignment. Produces a `ReviewResult` (approved/rejected + issues + revision instructions). |
| **DecisionExecutor** | `decision` | No | `agents/decision.py` | Pure routing logic (no LLM calls). If the story is approved or the revision budget (max 2 rounds) is exhausted, assembles the final `StoryResponse` and yields it as output. Otherwise, sends a `RevisionSignal` back to the Orchestrator to trigger another round. |

### Workflow Graph

```
                         StoryRequest (user input)
                              │
                              ▼
                    ┌─────────────────┐
                    │   Orchestrator   │ ◄──── RevisionSignal (max 2 rounds)
                    └────────┬────────┘                    ▲
                             │ StoryOutline                │
                             ▼                             │
                    ┌─────────────────┐                    │
                    │  StoryArchitect  │                    │
                    └────────┬────────┘                    │
                             │ StoryDraft (text only)      │
                             ▼                             │
                    ┌─────────────────┐                    │
                    │   ArtDirector    │                    │
                    └────────┬────────┘                    │
                             │ StoryDraft (with images)    │
                             ▼                             │
                    ┌─────────────────┐                    │
                    │  StoryReviewer   │  (skipped if      │
                    │                  │   SKIP_STORY_      │
                    │                  │   REVIEWER=true)   │
                    └────────┬────────┘                    │
                             │ ReviewResult                │
                             ▼                             │
                    ┌─────────────────┐   if rejected      │
                    │    Decision      │ ──────────────────┘
                    └────────┬────────┘
                             │ if approved or budget exhausted
                             ▼
                      StoryResponse
                    (ctx.yield_output)
```

### Key Concepts

#### WorkflowBuilder

The `WorkflowBuilder` from Microsoft Agent Framework provides a declarative API for defining agent execution graphs. Agents are added as executors, and edges define the execution order. The builder supports:

- **Linear edges** — `A → B → C` sequential execution
- **Conditional edges** — route to different executors based on runtime conditions
- **Fan-out / Fan-in edges** — execute multiple agents in parallel and merge results (used in the Activity Pages extension guide)
- **Back-edges** — loop back to a previous executor (used for the revision cycle)
- **Signals** — typed messages that executors can send to trigger specific handlers on other executors

#### Signals (`RevisionSignal`)

When the `DecisionExecutor` determines the story needs revisions, it sends a `RevisionSignal` containing `revision_instructions` and `revision_round`. The `OrchestratorAgent` has a handler specifically for this signal, which re-generates the `StoryOutline` incorporating the reviewer's feedback.

#### Events (`ProgressDetailEvent`)

The application defines a custom `ProgressDetailEvent` (extending `WorkflowEvent`) that executors emit during execution to provide fine-grained progress updates. Detail types include:

| Detail Type | Description |
|---|---|
| `prompt_sent` | An LLM prompt was dispatched |
| `response_received` | An LLM response was received |
| `page_content` | A story page's text content was generated |
| `image_queued` | An image generation request was queued |
| `image_started` | Image generation began for a specific page |
| `image_completed` | Image generation finished successfully |
| `image_failed` | Image generation failed |
| `executor_started` | An executor began processing |
| `revision_started` | A revision round was initiated |
| `images_batch_started` | The batch image generation process began |
| `auto_approved` | Story was auto-approved (reviewer skipped) |

#### Shared State

Executors use the workflow's shared state (`ctx.shared_state`) to pass data between agents. Key state entries include:

- `original_request` — the user's `StoryRequest`
- `revision_count` — current revision round number
- `illustrated_draft` — the `StoryDraft` with images (set by ArtDirector)

---

## Frontend Architecture

### Component Tree

```
App.jsx
├── "form" view
│   └── StoryForm
├── "generating" view  
│   └── ProgressTracker (mode="full")
└── "storybook" view
    ├── ProgressTracker (mode="sidebar", collapsible)
    └── StoryBook
        ├── CoverPage
        ├── StoryPage (× N)
        └── FinalPage
```

The application has three views, managed by a `view` state variable in `App.jsx`:

1. **`form`** — Initial input screen where the user fills in story details
2. **`generating`** — Full-page progress tracker showing real-time agent progress
3. **`storybook`** — Split layout with a collapsible progress sidebar and the interactive storybook

### Components

| Component | File | Role |
|---|---|---|
| **StoryForm** | `components/StoryForm.jsx` | Form with fields: main character, supporting characters (dynamic add/remove), setting, moral, main problem, and additional details. Pre-populated with whimsical default values for quick demos. |
| **ProgressTracker** | `components/ProgressTracker.jsx` | Displays the 5 workflow steps with animated status icons (pending, in-progress, completed). Includes expandable detail panels showing prompts, responses, page content, and image grids. Supports full-page and sidebar modes. Groups events into rounds for revision display. |
| **StoryBook** | `components/StoryBook.jsx` | Interactive page-by-page flipbook navigator. Pages: Cover → Story Pages → "The End". Navigation via prev/next buttons and dot indicators. Displays revision round count. |
| **StoryPage** | `components/StoryPage.jsx` | Three exported components: `CoverPage` (cover image with title overlay and moral tagline), `FinalPage` ("The End" image or gradient fallback), and default `StoryPage` (illustration + narrative text + character tags). |

**Hook:**

| Hook | File | Role |
|---|---|---|
| **useStoryGeneration** | `hooks/useStoryGeneration.js` | Manages the full generation lifecycle: POST request, SSE stream consumption via `fetch()` + `ReadableStream`, state updates (progress, details, story, error), abort support via `AbortController`, and reset functionality. Pre-seeds the orchestrator as "started" for immediate UI feedback. |

**Styling:**

- **CSS Modules** — Each component has a co-located `.module.css` file for scoped styling
- **Global styles** — `styles/global.css` defines a child-friendly color palette (whimsical purple, strawberry pink, mint aqua)
- **Fonts** — Nunito (body) and Fredoka One (headings) for a playful, storybook feel

---

## Data Flow

### Data Models

The application uses Pydantic models (backend) that define the data passing between agents:

```
StoryRequest (user input)
     │
     ▼
StoryOutline
  ├── title
  ├── target_pages (6-8)
  ├── characters[] (name, role, physical_description, personality_traits)
  ├── setting_details
  ├── moral
  └── pages[] (page_number, scene_description, characters_present, emotional_tone, key_dialogue)
     │
     ▼
StoryDraft
  ├── title
  ├── moral_summary
  ├── pages[] (page_number, text, image_prompt, image_url?)
  ├── cover_image_prompt, cover_image_url?
  └── the_end_image_prompt, the_end_image_url?
     │
     ▼
ReviewResult
  ├── approved (bool)
  ├── issues[] (category, description, severity, page_number?)
  └── revision_instructions?
     │
     ▼
StoryResponse (final output)
  ├── title
  ├── pages[] (page_number, text, image_url)
  ├── moral_summary
  ├── cover_image_url
  ├── the_end_image_url
  ├── review_notes
  └── revision_rounds
```

### Request-Response Lifecycle

1. **User submits form** → `StoryRequest` JSON body is POST'd to `/api/generate-story`
2. **Backend starts workflow** → `StoryGenerator.event_source_response()` creates an SSE stream
3. **Orchestrator** → generates `StoryOutline` from the request
4. **StoryArchitect** → writes narrative text and image prompts → `StoryDraft`
5. **ArtDirector** → generates illustrations concurrently (5 at a time) → `StoryDraft` with images
6. **StoryReviewer** → reviews the illustrated draft → `ReviewResult`
7. **Decision** → approves or triggers revision loop (max 2 rounds)
8. **Final output** → `StoryResponse` is yielded and sent as the `complete` SSE event
9. **Frontend** → transitions from "generating" to "storybook" view, renders the story

---

## SSE Streaming Architecture

The application uses **Server-Sent Events (SSE)** to stream real-time progress from the backend to the frontend. This is what powers the live progress tracker during story generation.

### Backend Event Translation

The `StoryGenerator` class (`story_generator.py`) sits between the Agent Framework and the SSE stream. It iterates over the framework's async event stream (`story_workflow.run_stream()`) and translates framework events into SSE messages:

| Framework Event | SSE Event Type | Content |
|---|---|---|
| `ExecutorInvokedEvent` | `progress` | `{executor_id, status: "started", label, message}` |
| `ExecutorCompletedEvent` | `progress` | `{executor_id, status: "completed", label, message}` |
| `ProgressDetailEvent` | `detail` | `{executor_id, detail_type, data}` |
| `ExecutorInvokedEvent` (orchestrator, round > 1) | `revision` | `{executor_id, revision_round, message}` |
| `WorkflowOutputEvent` | `complete` | `{story: StoryResponse}` |
| `WorkflowFailedEvent` | `error` | `{message}` |

### Frontend Event Consumption

The `useStoryGeneration` hook consumes the SSE stream using the native `fetch()` API with `response.body.getReader()` (not the `EventSource` API, since the request is a POST). It manually parses the SSE wire format — accumulating `event:` and `data:` lines and dispatching on blank-line separators.

### SSE Event Types

| Event Type | Payload | Frontend Action |
|---|---|---|
| `progress` | `{executor_id, status, label, message}` | Updates the step status in the progress tracker |
| `detail` | `{executor_id, detail_type, data}` | Appends detail information (prompts, page content, images) to the expandable panels |
| `revision` | `{executor_id, revision_round, message}` | Shows a revision notification in the progress tracker |
| `complete` | `{story: StoryResponse}` | Transitions to the storybook view and renders the final story |
| `error` | `{message}` | Displays an error message to the user |

---

## Project Structure

```
childrens-story-multi-agent/
├── README.md                          # Landing page with links to all docs
├── docs/                              # Documentation
│   ├── 01-prerequisites-and-setup.md
│   ├── 02-architecture-overview.md    # (this file)
│   ├── 03-running-the-demo.md
│   ├── 04-guide-activity-page-agents.md
│   └── 05-guide-tts.md
├── backend/
│   ├── requirements.txt               # Python dependencies
│   ├── .env.example                   # Environment variable template
│   └── app/
│       ├── main.py                    # FastAPI entry point, endpoints
│       ├── config.py                  # Pydantic settings (reads .env)
│       ├── models.py                  # Pydantic data models
│       ├── prompts.py                 # System prompt strings for each agent
│       ├── signals.py                 # RevisionSignal definition
│       ├── events.py                  # ProgressDetailEvent definition
│       ├── utils.py                   # JSON extraction, message building helpers
│       ├── workflow.py                # WorkflowBuilder graph definition
│       ├── story_generator.py         # SSE event translation layer
│       └── agents/
│           ├── orchestrator.py        # OrchestratorAgent
│           ├── story_architect.py     # StoryArchitectAgent
│           ├── art_director.py        # ArtDirectorExecutor
│           ├── story_reviewer.py      # StoryReviewerAgent
│           └── decision.py            # DecisionExecutor
├── frontend/
│   ├── package.json                   # npm dependencies and scripts
│   ├── vite.config.js                 # Vite config with API proxy
│   ├── index.html                     # HTML entry point
│   └── src/
│       ├── App.jsx                    # Root component, view routing
│       ├── main.jsx                   # React entry point
│       ├── components/
│       │   ├── StoryForm.jsx          # Story input form
│       │   ├── ProgressTracker.jsx    # Real-time progress display
│       │   ├── StoryBook.jsx          # Page flipbook navigator
│       │   └── StoryPage.jsx          # Individual page renderers
│       ├── hooks/
│       │   └── useStoryGeneration.js  # SSE stream consumer hook
│       └── styles/
│           └── global.css             # Global styles and color palette
└── .vscode/
    └── tasks.json                     # Pre-configured dev tasks
```

---

## Next Steps

- [Running the Demo](03-running-the-demo.md) — Start the application and walk through a demo
- [Guide: Activity Page Agents](04-guide-activity-page-agents.md) — Extend the workflow with new agents
- [Guide: Text-to-Speech](05-guide-tts.md) — Add narration capabilities

[← Back to README](../README.md)
