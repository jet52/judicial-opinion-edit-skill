# Judicial Opinion Edit Skill

Appellate judicial opinion editor and proofreader. Produces a Word document (.docx) with tracked changes showing proposed edits, plus a separate analysis document with explanations. Applies Garner's Redbook, Bluebook citation format, and style preferences drawn from Justice Jerod Tufte (ND Supreme Court).

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (CLI) installed
- Python 3.10+
- Node.js 18+
- [LibreOffice](https://www.libreoffice.org/) (for document conversion)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

### Claude Code (CLI)

**Option A: From .zip**

1. Download and extract `judicial-opinion-edit-skill.zip`
2. Run the installer:
   ```bash
   bash install.sh
   ```
   The installer will:
   - Copy skill files to `~/.claude/skills/judicial-opinion-edit/`
   - Create a Python virtual environment with required packages
   - Run `npm install` for the `docx` Node.js package

**Option B: From source**

```bash
git clone https://github.com/jet52/judicial-opinion-edit-skill.git
cd judicial-opinion-edit-skill
make install
```

**Option C: Manual**

```bash
# Copy skill files
mkdir -p ~/.claude/skills/judicial-opinion-edit
cp -a skill/* ~/.claude/skills/judicial-opinion-edit/

# Set up Python venv
cd ~/.claude/skills/judicial-opinion-edit
uv venv .venv
uv pip install defusedxml pikepdf splitmarks --python .venv/bin/python

# Install Node dependencies
npm install
```

### Claude Desktop

1. Open Settings > Features > Claude's Computer Use > Skills directory
2. Set the skills directory to a folder of your choice (e.g., `~/.claude/skills/`)
3. Copy `skill/` contents into `<skills-dir>/judicial-opinion-edit/`
4. Set up the Python venv and Node dependencies manually (see Option C above)

### Claude Projects (web)

1. Open your Claude project
2. Go to Project Knowledge
3. Upload the contents of `skill/SKILL.md` as a project knowledge file

Note: The web version cannot execute scripts, access local files, or produce tracked-changes .docx output. It can still provide editorial analysis as text.

## Usage

Trigger phrases:
- "Edit this opinion"
- "Proofread this opinion"
- "Review this draft opinion"
- "Redline this opinion"
- "Edit this draft order"

Provide a `.docx` draft opinion in the working directory. Optionally include `.pdf` briefs or record materials for fact-checking.

## File Structure

```
judicial-opinion-edit-skill/
├── README.md
├── Makefile
├── install.sh
├── .gitignore
└── skill/
    ├── SKILL.md
    ├── TMPDIR-CONFIGURATION.md
    ├── package.json
    └── references/
        ├── nd-appellate-rules.md
        └── style-guide.md
```

## External Dependencies

| Dependency | Purpose | Required? |
|-----------|---------|-----------|
| Python 3.10+ | PDF/XML processing | Yes |
| Node.js 18+ | DOCX generation | Yes |
| LibreOffice | Document conversion/validation | Yes |
| defusedxml | Safe XML parsing | Yes (installed by installer) |
| pikepdf | PDF manipulation | Yes (installed by installer) |
| splitmarks | PDF bookmark splitting | Yes (installed by installer) |
| docx (npm) | DOCX document creation | Yes (installed by installer) |
