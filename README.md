# Automation Workspace

LLM-powered workflow automation projects. Runs locally via Ollama or switches to
cloud APIs (Anthropic / OpenAI / Groq) with a single `.env` change.

## First-time setup (needs internet)

```bash
bash scripts/setup.sh
```

Then:

```bash
cp .env.example .env     # fill in API keys
conda activate automation
ollama serve             # keep this running in a separate terminal tab
```

## Folder structure

```
Automation/
├── projects/            # one folder per automation project
│   └── _template/      # copy this to start a new project
├── shared/
│   ├── utils/          # llm_client.py, prompt_utils.py
│   └── prompts/        # reusable prompt templates (.txt)
├── notebooks/           # Jupyter notebooks for experiments
├── docs/               # model_guide.md, architecture notes
├── scripts/            # setup.sh and other utility scripts
├── environment.yml     # conda env spec — source of truth for deps
├── .env.example        # copy to .env, fill in keys
└── .gitignore
```

## Starting a new project

```bash
cp -r projects/_template projects/my_project
cd projects/my_project
# edit main.py, then:
python main.py
```

## Switching LLM provider

Edit `.env`:
```
LLM_PROVIDER=local    # Ollama (phi3:mini by default)
LLM_PROVIDER=cloud    # Anthropic / OpenAI / Groq
```

Or override per-call in Python:
```python
from shared.utils import get_llm
llm = get_llm(provider="cloud", model="claude-haiku-4-5-20251001")
```

## Moving to SSD / cloud

This folder is fully self-contained. To move:
- **SSD:** `cp -r ~/Desktop/Automation /Volumes/YourSSD/`
- **Cloud VM:** `rsync -av Automation/ user@server:~/Automation/`  
  Then run `bash scripts/setup.sh` on the new machine.

## Key dependencies

| Package | Purpose |
|---------|---------|
| `langchain` | LLM orchestration, chains, agents |
| `langgraph` | Multi-agent / stateful workflows |
| `ollama` | Local model inference |
| `anthropic` / `openai` | Cloud APIs |
| `playwright` | Browser automation |
| `loguru` | Clean structured logging |
| `ruff` | Fast linter & formatter |
