# Children's Story Studio — Multi-Agent Orchestration

<!-- TODO: Add screenshot of the running application here -->
<!-- ![Children's Story Studio](docs/images/app-screenshot.png) -->

**Children's Story Studio** is a full-stack application that uses [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) to orchestrate multiple AI agents that collaboratively generate illustrated children's stories. It is designed to serve three purposes:

1. **Field Seller Demo** — A polished, ready-to-run demonstration of multi-agent AI orchestration that sellers can walk customers through in minutes.
2. **Multi-Agent Orchestration Example** — A real-world reference implementation showing how to build agent workflows with Microsoft Agent Framework, including conditional branching, revision loops, and real-time progress streaming.
3. **Customer Engineering Sandbox** — A well-structured starting point that customer engineers can clone, experiment with, and extend with new agents and multi-modal AI capabilities.

## How It Works

A user fills in story details (characters, setting, moral, etc.) and the application orchestrates **five specialized AI agents** through a coordinated workflow to produce a fully illustrated children's storybook — complete with cover art, per-page illustrations, and narrative text — all streamed to the browser in real time.

```
Orchestrator → StoryArchitect → ArtDirector → StoryReviewer → Decision
    ↑                                                             │
    └──────────── RevisionSignal (max 2 rounds) ─────────────────┘
```

## Quick Start

1. **Set up prerequisites** — [Prerequisites & Environment Setup](docs/01-prerequisites-and-setup.md)
2. **Understand the architecture** — [Architecture Overview](docs/02-architecture-overview.md)
3. **Run the demo** — [Running the Demo](docs/03-running-the-demo.md)

## Guides

These step-by-step walkthroughs guide you through extending the base application with new capabilities using **GitHub Copilot**. Each guide demonstrates a different pattern for expanding multi-agent workflows and integrating additional AI modalities.

| Guide | What You'll Build | Key Concepts |
|---|---|---|
| [Adding Activity Page Agents](docs/04-guide-activity-page-agents.md) | Look & Find activity page + Character Glossary page appended to the storybook | Fan-out / fan-in agent patterns, new agent creation, conditional workflow paths, UI extensions |
| [Adding Text-to-Speech](docs/05-guide-tts.md) | Play button on each page that streams Azure AI Speech narration | Multi-modal AI (text → speech), new API endpoints, streaming audio, `DefaultAzureCredential` |

> **Approach:** Each guide walks you through using GitHub Copilot in **Plan mode** (with Claude Opus, or your preferred model) to design the implementation, then **Agent mode** (with Claude Sonnet, or your preferred model) to execute it. The goal is to experience how an AI engineer would use Copilot to extend an existing agent-based application.

## Reference Branches

The following branches contain working implementations of the guided extensions. They exist as **backup references** — the intended workflow is to generate these features yourself using GitHub Copilot by following the guides above.

| Branch | Description |
|---|---|
| `activity-page-agents` | Look & Find + Character Glossary agents added to the workflow |
| `story-tts` | Text-to-Speech narration on every story page |
| `activity-page-agents-and-tts` | All features combined (activity pages + TTS) |

## Documentation

| Document | Description |
|---|---|
| [Prerequisites & Environment Setup](docs/01-prerequisites-and-setup.md) | Tools, Azure resources, environment configuration, and local setup |
| [Architecture Overview](docs/02-architecture-overview.md) | System design, agent descriptions, workflow graph, SSE streaming, and data flow |
| [Running the Demo](docs/03-running-the-demo.md) | Step-by-step instructions for running the app and demo talking points |
| [Guide: Activity Page Agents](docs/04-guide-activity-page-agents.md) | Extend the workflow with Look & Find and Character Glossary agents |
| [Guide: Text-to-Speech](docs/05-guide-tts.md) | Add Azure AI Speech narration to every story page |

## License

This project is provided as an example for demonstration and experimentation purposes.
