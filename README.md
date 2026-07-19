<div align="center">

# NovelForge

**An AI-assisted desktop studio for planning, writing, reviewing, and maintaining continuity in Chinese web novels.**

NovelForge turns long-form fiction writing into a structured workflow instead of a sequence of disconnected prompts.

</div>

> [!NOTE]
> NovelForge is under active development. The current interface is primarily in Chinese, and running from source is the recommended way to try it.

## Why NovelForge?

Generating a paragraph is easy. Maintaining a coherent novel across dozens of chapters is not.

Long-form fiction requires the model to remember world rules, character motivations, prior events, unresolved plot threads, narrative style, and what each character knows at a particular point in the story. NovelForge treats these as persistent project data and coordinates multiple writing steps around them.

The goal is to keep the author in control while using AI for the repetitive and context-heavy parts of drafting.

## What you can do

- **Build a novel bible** with worldbuilding, terminology, factions, power systems, style guidance, and character definitions.
- **Plan hierarchically** using a volume → chapter → scene outline.
- **Generate scenes through a multi-step pipeline** for planning, character intent, prose writing, review, fact extraction, and state updates.
- **Review before committing** by approving prose and extracted continuity changes instead of silently accepting model output.
- **Track continuity over time** through canon facts, character state, scene summaries, and revision-aware history.
- **Route different tasks to different models** using Ollama, DeepSeek, or a mixture of both.
- **Keep projects on your computer** and export approved prose to Markdown or EPUB.

## Writing workflow

```text
Novel Bible
    ↓
Volume / Chapter / Scene Outline
    ↓
Scene Planning + Character Intent
    ↓
Draft Generation
    ↓
Review and Author Approval
    ↓
Canon Facts + Character State Update
    ↓
Next Scene
```

A typical session looks like this:

1. Create a project and choose an LLM provider.
2. Define the world, writing style, and main characters in **设定集**.
3. Create volumes, chapters, and scenes in **大纲**.
4. Select a scene and open **写作台**.
5. Generate a draft, inspect the review results, and revise or approve it.
6. Approve extracted facts and state changes so later scenes use the updated story context.
7. Export the approved manuscript when ready.

## Quick start

### Prerequisites

- Python **3.12 or newer**
- Git
- At least one configured LLM provider:
  - [Ollama](https://ollama.com/) for local models
  - [DeepSeek API](https://platform.deepseek.com/) for hosted inference

### 1. Clone the repository

```bash
git clone https://github.com/hzhang092/novel-agent.git
cd novel-agent
```

### 2. Create a virtual environment

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure a model

#### Option A: Ollama

1. Install and start Ollama.
2. Pull a model that is suitable for Chinese long-form writing.
3. In NovelForge, open **文件 → LLM 设置**.
4. Enter the Ollama host and the exact model name installed on your machine.

#### Option B: DeepSeek

1. Create a DeepSeek API key.
2. Open **文件 → LLM 设置 → DeepSeek**.
3. Enter the model, API endpoint, and API key.

The API key is stored through the operating system's credential store rather than in the project files.

You can also use **步骤路由** to assign Ollama or DeepSeek independently to planning, character reasoning, writing, review, fact extraction, and state updates.

### 5. Launch NovelForge

```bash
python -m app.main
```

Then select **文件 → 新建项目** and follow the writing workflow above.

## Main areas of the application

| Area | Purpose |
| --- | --- |
| **总览** | Open a project and view its current progress. |
| **设定集** | Edit world settings, style guidance, and characters. |
| **大纲** | Organize volumes, chapters, and scenes. |
| **写作台** | Generate, compare, review, revise, and approve scene prose. |
| **LLM 设置** | Configure providers and route pipeline steps to different models. |

## How the agent pipeline is organized

NovelForge separates scene generation into focused responsibilities rather than asking one prompt to do everything:

| Step | Responsibility |
| --- | --- |
| **Planner** | Converts the selected outline entry and story context into a scene plan. |
| **Characters** | Determines the goals, knowledge, emotions, and likely actions of participating characters. |
| **Writer** | Produces scene prose using the plan, character intent, style guide, and prior context. |
| **Reviewer** | Checks the draft for quality and continuity problems. |
| **Fact Extractor** | Proposes new canon facts implied by the accepted prose. |
| **State Updater** | Proposes character-state changes for future scenes. |

The approval boundaries are intentional: generated prose and continuity updates remain inspectable before they become part of the active story timeline.

## Project structure

```text
app/
├── application/   # Qt-independent project-editing use cases and composition
├── domain/        # Pure business rules and model transformations
├── pipeline/      # Scene-generation orchestration and context assembly
├── providers/     # Ollama and DeepSeek integrations
├── storage/       # Project models, repositories, timelines, and persistence
├── ui/            # PySide6 desktop interface
├── events/        # Domain events and Qt bridge
└── main.py        # Application entry point

tests/             # Unit and integration tests
docs/              # Design notes, implementation plans, and verification reports
```

## Development

Install the dependencies and run the test suite:

```bash
pip install -r requirements.txt
pytest
```

The repository includes design and verification notes under `docs/` for major changes. When modifying continuity, event-sourcing, or scene-publication behavior, add tests that cover regeneration, retries, and out-of-order scene editing.

## Current status

NovelForge is an early-stage project (`0.1.0`) being developed actively. Core workflows are implemented, but interfaces, storage formats, prompts, and agent boundaries may continue to change.

The most useful next additions to this README are:

- a short product demo GIF;
- screenshots of the novel bible, outline, and writing workspace;
- a tested model-recommendation table with expected hardware requirements;
- packaged desktop releases for users who do not want to run from source.

## Contributing

Bug reports, design feedback, and focused pull requests are welcome. For larger changes, open an issue first and describe the user problem, the proposed workflow, and how the change affects story continuity or project compatibility.

## License

NovelForge is licensed under the [MIT License](LICENSE). Binary distributions also include third-party software under their own terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
