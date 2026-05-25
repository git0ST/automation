#!/usr/bin/env bash
# Run this once when you have internet to finish the LLM setup.
# The conda env 'automation' is already created — this only installs
# the packages that require internet.
#
# Usage:  bash scripts/setup.sh

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CONDA_PYTHON="/Users/shivamthakur/anaconda3/envs/automation/bin/python"
CONDA_PIP="/Users/shivamthakur/anaconda3/envs/automation/bin/pip"

echo "==> 1/3  Installing LLM packages into 'automation' env..."
$CONDA_PIP install \
  "langchain>=0.3" \
  "langchain-community>=0.3" \
  "langchain-anthropic>=0.3" \
  "langchain-openai>=0.3" \
  "langgraph>=0.2" \
  "ollama>=0.4" \
  "anthropic>=0.40" \
  "openai>=1.50" \
  "playwright>=1.48" \
  "loguru>=0.7" \
  "numpy>=1.26" \
  "pandas>=2.1" \
  "scikit-learn>=1.4" \
  "pytest>=8.0" \
  "ruff>=0.6"

echo ""
echo "==> 2/3  Installing Playwright browser (Chromium)..."
$CONDA_PYTHON -m playwright install chromium

echo ""
echo "==> 3/3  Pulling starter model via Ollama..."
echo "    (Ollama must already be installed and running — download from https://ollama.com/download)"
if command -v ollama &>/dev/null; then
  ollama pull phi3:mini
  echo "    Optional: ollama pull llama3.2:3b"
else
  echo "    Ollama not found in PATH. Open Ollama.app first, then run:"
  echo "    ollama pull phi3:mini"
fi

echo ""
echo "✓ Python packages installed in 'automation' conda env."
echo ""
echo "To run the first project:"
echo "  conda activate automation"
echo "  ollama serve            # or just open Ollama.app"
echo "  cd projects/doc_qa"
echo "  python main.py ask 'What is multi-head attention?'"
