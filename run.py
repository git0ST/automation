"""
Run any project from the Automation root directory.

Usage:
    python run.py doc_qa ask "your question"
    python run.py doc_qa summarize
    python run.py doc_qa interactive
    python run.py doc_qa ask "question" --file path/to/doc.txt
"""

import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python run.py <project> [args...]")
    print("\nAvailable projects:")
    for p in sorted((Path(__file__).parent / "projects").iterdir()):
        if p.is_dir() and not p.name.startswith("_") and (p / "main.py").exists():
            print(f"  {p.name}")
    sys.exit(0)

project = sys.argv[1]
project_main = Path(__file__).parent / "projects" / project / "main.py"

if not project_main.exists():
    print(f"Error: no project '{project}' found (looked for {project_main})")
    sys.exit(1)

# Rewrite argv so the project's main.py sees its own args
sys.argv = [str(project_main)] + sys.argv[2:]

# Add project dir to path so local packages (sources/, etc.) are importable
project_dir = str(project_main.parent)
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

exec(project_main.read_text(), {"__file__": str(project_main), "__name__": "__main__"})
