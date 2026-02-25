# JetRedline

Appellate judicial opinion and bench memo editor and proofreader. Produces a Word document (.docx) with tracked changes showing proposed edits, plus a separate analysis document with explanations. Applies Garner's Redbook, Bluebook citation format, and style preferences drawn from Justice Jerod Tufte (ND Supreme Court).

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (CLI) installed
- Python 3.10+
- Node.js 18+
- [LibreOffice](https://www.libreoffice.org/) (for document conversion)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

### Claude Desktop

1. Download [`jetredline-skill.zip`](https://github.com/jet52/jetredline/releases/latest)
2. Open Settings > Features > Claude's Computer Use > Skills directory
3. Set the skills directory to a folder of your choice (e.g., `~/.claude/skills/`)
4. Copy `skill/` contents into `<skills-dir>/jetredline/`
5. Set up the Python venv and Node dependencies manually (see Option C above)

### Claude Projects (web)

1. Download [`jetredline-skill.zip`](https://github.com/jet52/jetredline/releases/latest) from GitHub
2. Open your Claude Project → Project Knowledge
3. Upload `jetredline-skill.zip`
4. Paste opinion text or upload .docx/.pdf files in conversation
5. Use the same trigger phrases ("edit this opinion", "edit this bench memo", etc.)

**Web mode limitations:**
- Produces markdown analysis only (no tracked-changes .docx)
- All passes run inline — no subagent delegation (may hit context limits on very long opinions)
- Citation verification uses web search instead of local opinion corpus (less reliable)
- No PDF splitting for large record packets (upload individual documents)

## Usage

Trigger phrases:

- "Edit this opinion"
- "Proofread this opinion"
- "Review this draft opinion"
- "Redline this opinion"
- "Redline this draft"
- "Redline this memo"
- "Edit this draft order"

Provide a `.docx` draft opinion in the working directory. Optionally include `.pdf` briefs or record materials for fact-checking.

## File Structure

```
jetredline/
├── README.md
├── Makefile
├── install.sh
├── .gitignore
└── skill/
    ├── SKILL.md
    ├── TMPDIR-CONFIGURATION.md
    ├── package.json
    ├── nd_cite_check.py
    ├── readability_metrics.py
    ├── splitmarks.py          # vendored PDF bookmark splitter
    └── references/
        ├── nd-appellate-rules.md
        └── style-guide.md
```

### Claude Code (CLI)

**Option A: From .zip**

1. Download and extract [`jetredline-skill.zip`](https://github.com/jet52/jetredline/releases/latest)
2. Run the installer:
   ```bash
   bash install.sh
   ```
   The installer will:
   - Copy skill files to `~/.claude/skills/jetredline/`
   - Create a Python virtual environment with required packages
   - Run `npm install` for the `docx` Node.js package

**Option B: From source**

```bash
git clone https://github.com/jet52/jetredline.git
cd jetredline
make install
```

**Option C: Manual**

```bash
# Copy skill files
mkdir -p ~/.claude/skills/jetredline
cp -a skill/* ~/.claude/skills/jetredline/

# Set up Python venv
cd ~/.claude/skills/jetredline
uv venv .venv
uv pip install defusedxml pikepdf textstat --python .venv/bin/python

# Install Node dependencies
npm install
```

## External Dependencies

| Dependency   | Purpose                        | Required?                    |
| ------------ | ------------------------------ | ---------------------------- |
| Python 3.10+ | PDF/XML processing             | Yes                          |
| Node.js 18+  | DOCX generation                | Yes                          |
| LibreOffice  | Document conversion/validation | Yes                          |
| defusedxml   | Safe XML parsing               | Yes (installed by installer) |
| pikepdf      | PDF manipulation               | Yes (installed by installer) |
| splitmarks   | PDF bookmark splitting         | Bundled script (no install)  |
| textstat     | Readability metrics            | Yes (installed by installer) |
| docx (npm)   | DOCX document creation         | Yes (installed by installer) |
