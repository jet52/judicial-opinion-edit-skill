---
name: judicial-opinion-edit
description: "Appellate judicial opinion and bench memo editor and proofreader. Produces a Word document (.docx) with tracked changes showing proposed edits, plus a separate analysis document with explanations. Use when the user provides a draft judicial opinion, court order, bench memo, or legal memorandum for editing, proofreading, or style review. Triggers: edit opinion, proofread opinion, review draft opinion, judicial writing review, court opinion edit, redline opinion, edit draft order, appellate opinion editing, edit memo, edit bench memo, proofread memo, review bench memo. Applies Garner's Redbook, Bluebook citation format, and style preferences drawn from Justice Jerod Tufte (ND Supreme Court), Guberman's Point Taken, and Justices Gorsuch, Kagan, and Thomas."
---

# Judicial Opinion Editor

Edit draft judicial opinions and bench memos to improve grammar, clarity, conciseness, professional tone, citation accuracy, and analytical rigor. Produce a Word document with tracked changes and a companion analysis document.

## Fixed Paths — Do Not Search

All paths are hardcoded. **Do not run `ls`, `find`, or any discovery commands to locate them.**

| Resource | Path |
|----------|------|
| This skill | `~/.claude/skills/judicial-opinion-edit/` |
| Docx skill (plugin) | `~/.claude/plugins/cache/anthropic-agent-skills/document-skills/69c0b1a06741/skills/docx/` |
| Venv python | `~/.claude/skills/judicial-opinion-edit/.venv/bin/python` |
| splitmarks | `~/.claude/skills/judicial-opinion-edit/.venv/bin/splitmarks` |
| Node modules | `~/.claude/skills/judicial-opinion-edit/node_modules/` |
| soffice (LibreOffice) | `/Applications/LibreOffice.app/Contents/MacOS/soffice` |
| ND opinions (markdown) | `$OPINIONS_MD` → `~/cDocs/refs/ndsc_opinions/markdown/` |

The opinions directory contains markdown copies of published ND Supreme Court opinions organized as `<year>/<year>ND<number>.md` (e.g., `2022/2022ND210.md` for *Feickert v. Feickert*, 2022 ND 210). Paragraphs are marked `[¶N]`. Use `$OPINIONS_MD` in commands; fall back to the hardcoded path if the variable is unset.

Use the docx skill path as PYTHONPATH and script root for all docx operations (unpack.py, pack.py, document.py, ooxml.md, etc.).

## Python Environment

This skill has a persistent virtual environment. **Always use this venv python for all Python operations — never create a new venv in the working directory.**

- **Pre-installed packages:** `defusedxml`, `pikepdf`, `splitmarks`

If the venv does not exist or a package is missing, create/repair it:
```bash
uv venv ~/.claude/skills/judicial-opinion-edit/.venv
uv pip install defusedxml pikepdf splitmarks --python ~/.claude/skills/judicial-opinion-edit/.venv/bin/python
```

## Temporary Files

**CRITICAL:** In Step 0, create a uniquely-named temp directory and capture its **absolute path** as a literal string. Use that literal path (no command substitution) in all subsequent `TMPDIR=` prefixes.

**Step 0 temp-dir setup (run once):**
```bash
SKILL_TMPDIR="$PWD/.tmp-$(awk 'BEGIN{srand()}{a[NR]=tolower($0)}END{for(i=1;i<=3;i++)printf "%s%s",(i>1?"-":""),a[int(rand()*NR)+1]}' /usr/share/dict/words)" && mkdir -p "$SKILL_TMPDIR" && echo "$SKILL_TMPDIR"
```
This picks three random dictionary words to form a unique directory name (e.g., `.tmp-apple-walrus-quilt`), preventing collisions between concurrent sessions.

**Capture the output** (the absolute path printed by `echo`) and use it as a literal string in all subsequent commands. For example, if the output is `/path/to/cases/smith/.tmp-apple-walrus-quilt`, then every later command uses:
```
TMPDIR=/path/to/cases/smith/.tmp-apple-walrus-quilt
```
**Never** use `TMPDIR="$(pwd)/.tmp"` — the command substitution triggers unnecessary permission prompts on every invocation.

## Node.js Environment

The `docx` npm package is pre-installed in this skill's directory. **Do not run `npm install` — it is already available.**

When running Node scripts that use `docx`, set `NODE_PATH` so Node can find the package:
```bash
NODE_PATH=~/.claude/skills/judicial-opinion-edit/node_modules node script.js
```

When running docx skill scripts (always include TMPDIR — use the literal absolute path from Step 0):
```bash
TMPDIR=<TMPDIR> PYTHONPATH=~/.claude/plugins/cache/anthropic-agent-skills/document-skills/69c0b1a06741/skills/docx/ ~/.claude/skills/judicial-opinion-edit/.venv/bin/python script.py
```
where `<TMPDIR>` is the literal path captured in Step 0 (e.g., `/path/to/cases/smith/.tmp-apple-walrus-quilt`).

## LibreOffice (soffice)

On macOS, `soffice` is not on PATH by default. The docx skill's `pack.py` uses it for validation. **Always prepend the LibreOffice path and set TMPDIR when running pack.py or any command that invokes soffice:**

```bash
TMPDIR=<TMPDIR> PATH="/Applications/LibreOffice.app/Contents/MacOS:$PATH" PYTHONPATH=~/.claude/plugins/cache/anthropic-agent-skills/document-skills/69c0b1a06741/skills/docx/ ~/.claude/skills/judicial-opinion-edit/.venv/bin/python ~/.claude/plugins/cache/anthropic-agent-skills/document-skills/69c0b1a06741/skills/docx/ooxml/scripts/pack.py <input_directory> <output.docx>
```
where `<TMPDIR>` is the literal absolute path from Step 0.

Also use this PATH prefix for document-to-image conversion (`soffice --headless --convert-to pdf`) and any other LibreOffice operations.

## Workflow

### Step 0: Initialize and Scan Working Directory

**First, create the temp directory** with a unique random name:
```bash
SKILL_TMPDIR="$PWD/.tmp-$(awk 'BEGIN{srand()}{a[NR]=tolower($0)}END{for(i=1;i<=3;i++)printf "%s%s",(i>1?"-":""),a[int(rand()*NR)+1]}' /usr/share/dict/words)" && mkdir -p "$SKILL_TMPDIR" && echo "$SKILL_TMPDIR"
```
**Capture the absolute path** printed by this command (e.g., `/path/to/cases/smith/.tmp-apple-walrus-quilt`). Use this literal path as `TMPDIR=<path>` in all subsequent commands — never use `$(pwd)` or other command substitution for TMPDIR.

Then scan the current working directory for:
- **`.docx` files** — potential draft opinions, memos, or dissents
- **`.pdf` files** — potential briefs, record packets, or supporting references

If **exactly one `.docx`** is found, use it as the draft document.
If **exactly one `.pdf`** is found, use it as the record/briefs packet for fact-checking.
If **more than one `.docx`** or **more than one `.pdf`** is found, ask the user which file(s) to use and their roles (e.g., majority opinion, dissent, bench memo, briefs packet, supporting reference).
If **no `.docx`** is found, ask the user to provide the document text.

**Preparing PDF packets (do not read into main context):** PDF source materials are used only by the Pass 4 fact-checking subagent. In Step 0, identify and prepare the files but **do not read their contents**.

For large PDF files (typically > 50 MB), use `splitmarks` to split the PDF at its top-level bookmarks into individual documents:
```bash
# Preview what bookmarks exist
~/.claude/skills/judicial-opinion-edit/.venv/bin/splitmarks packet.pdf --dry-run -vv

# Split into individual files in an output directory
~/.claude/skills/judicial-opinion-edit/.venv/bin/splitmarks packet.pdf -o split_output -v
```
Pass the resulting file paths to the fact-checking subagent in Pass 4.

### Step 0.1: Determine Document Type

Classify the document as `DOC_TYPE = opinion` or `DOC_TYPE = memo`. Check in order:

1. **Invocation keywords:** If the user's prompt contains "bench memo", "memo", "law clerk draft", or similar → `memo`
2. **Document content:** If the document contains markers typical of bench memos (e.g., "BENCH MEMORANDUM", "BENCH MEMO", "Issues Presented", "Recommendation", "Staff Attorney" heading patterns) → `memo`
3. **Ambiguous:** If neither signal is present and the document could be either type, ask the user via `AskUserQuestion`:
   - **Question:** "Is this a draft judicial opinion or a bench memo?"
   - **Header:** "Doc type"
   - **Options:**
     1. **Judicial opinion** — Draft opinion, concurrence, or dissent
     2. **Bench memo** — Staff attorney or law clerk memo to the court
4. **Default:** `opinion`

Store `DOC_TYPE` and reference it in conditional sections of Passes 1 and 5 and the analysis document output.

### Step 0.5: Ask Output Preferences

**Ask the user which outputs they want:**

Use the AskUserQuestion tool to present these options:

**Question:** "Which output(s) would you like me to produce?"
**Header:** "Output type"
**Options:**
1. **Both documents** — Tracked-changes .docx + analysis document (full editing service)
2. **Tracked-changes .docx only** — Just the edited opinion with markup (saves tokens, no analysis)
3. **Analysis document only** — Research and findings without producing edited .docx (saves time on OOXML assembly)

Store the user's choice and adjust the workflow accordingly:
- If **both**: Follow the full workflow through Step 10
- If **tracked-changes only**: Complete all editing passes, produce the .docx in Step 9, skip Step 10 (analysis document)
- If **analysis only**: Complete all editing passes and collect findings, produce only the analysis document in Step 10, skip Step 9 (.docx creation)

**Note:** Even when producing analysis only, you must still perform all editing passes (1–5) to identify issues and generate findings for the analysis. You simply skip the final .docx assembly step.

### Steps 1–10: Core Workflow
1. Read `references/style-guide.md`
2. Read the docx skill: **only** `SKILL.md` and `ooxml.md` from the docx skill directory. **Do not** read `docx-js.md`, `document.py`, or other files — they are executed by scripts and not needed in context.
3. Read the draft opinion (from Step 0 or user-provided file/pasted text). **Count paragraphs** (¶ markers or logical paragraphs) to determine opinion length.
4. **Delegate Pass 1** (jurisdictional check) to a subagent — see Pass 1 below
5. **Delegate Pass 3** (citation verification) to a subagent — see Pass 3 below
6. **Delegate Pass 4** (fact-checking) to a subagent if PDF materials were identified in Step 0 — see Pass 4 below
7. **Pass 2 routing:** If the opinion has **more than 30 paragraphs**, delegate Pass 2 to a subagent — see "Delegated Pass 2" below. Otherwise, perform Pass 2 in main context. **Pass 5** (analytical rigor) is always performed in main context. Pass 2 (when not delegated) and Pass 5 can proceed in parallel with subagents.
8. Collect subagent results from Passes 1, 3, 4, and (if delegated) Pass 2 — **use the `TaskOutput` tool**, not Bash `tail`
9. **If user requested tracked-changes .docx** (both or tracked-changes only): Produce tracked-changes .docx output using the docx skill's editing workflow
10. **If user requested analysis document** (both or analysis only): Produce the companion analysis document (incorporating all subagent results). If also producing .docx, create both outputs in the same response

**If the opinion is a .docx file:** use the docx skill's unpack → edit XML → repack workflow to add tracked changes and comments directly to the original document.

**If the opinion is plain text or another format:** create a new .docx using the docx skill, with tracked-change markup showing all edits.

## Editing Instructions

Adopt the persona of an experienced appellate attorney working for a state supreme court. Be careful and precise.

### Pass 1: Jurisdictional Check (Delegated to Subagent)

**Do not** read `references/nd-appellate-rules.md` into the main context. Delegate this pass to a subagent using the Task tool (subagent_type: `general-purpose`) with instructions that vary by `DOC_TYPE`.

#### If DOC_TYPE is `opinion` (default)

Provide the subagent with these instructions:

- Read `~/.claude/skills/judicial-opinion-edit/references/nd-appellate-rules.md`
- Read the draft opinion file (provide the path) — focus on the procedural-posture and standard-of-review sections
- Verify: Was there a timely appeal under N.D.R.App.P. Rules 2.1, 2.2, 3, and 4?
- Verify: Does the opinion correctly identify the procedural posture and standard of review?
- Verify: Are court rules cited accurately? Check against https://www.ndcourts.gov/legal-resources/rules
- Return **only** a concise summary of findings: any jurisdictional issues, procedural-posture errors, or standard-of-review problems. If no issues found, state that explicitly.

#### If DOC_TYPE is `memo`

Provide the subagent with these instructions:

- Read `~/.claude/skills/judicial-opinion-edit/references/nd-appellate-rules.md`
- Read the draft memo file (provide the path)
- Check whether the memo addresses appealability: timeliness, subject-matter jurisdiction, and procedural prerequisites (e.g., OMB notification for claims against the state under N.D.C.C. § 32-12.2-04)
- Check whether the parties' briefs (if available in the working directory) raise jurisdictional issues
- If **neither** the memo nor the parties address appealability at all → return a **warning** that the memo should confirm appellate jurisdiction
- If the memo does address appealability → verify the analysis against `nd-appellate-rules.md` as with opinions
- Return a concise summary: any jurisdictional concerns or warnings. If the memo adequately addresses jurisdiction, state that explicitly.

### Pass 2: Style and Grammar
Apply in priority order. Full details in `references/style-guide.md`.

**Hard rules (always apply):**
- Active voice unless passive genuinely improves readability
- Never use plural pronouns as gender-neutral singular — use he, she, it, or rephrase
- Never use "and/or"
- Never use legalese: herein, wherefore, aforementioned, said/such/same as pronouns
- Never use Latin-derived words when plain English carries equal precision
- Always use the Oxford comma
- Constitutions protect, guarantee, or preserve rights — never "create" or "grant" (unless the text clearly declares a new right)
- Replace any ordinary space following a paragraph symbol (¶) or section symbol (§) with a nonbreaking space (Unicode U+00A0). In OOXML, use `&#160;` in the XML text. Apply as tracked changes in the output.

**Style preferences (apply with judgment):**
- Lead with the point; conclusion before reasoning
- Short sentences for holdings; vary length elsewhere
- Cut throat-clearing ("It is well settled that," "It should be noted that")
- Cut nominalizations; prefer verb forms
- Keep subject and verb close
- One idea per sentence when practical
- Short paragraphs (under 200 words) in analytical sections

#### Delegated Pass 2 (opinions over 30 paragraphs)

When the opinion exceeds 30 paragraphs, delegate Pass 2 to a Task subagent (subagent_type: `general-purpose`) to keep main-context output tokens manageable. Provide the subagent with:

- The path to `references/style-guide.md` (instruct it to read this file)
- The path to the draft opinion file (instruct it to read it)
- The hard rules and style preferences listed above (copy them into the prompt so the subagent has them without needing additional context)

**Subagent instructions:**

> **Style and Grammar Edit — Pass 2**
>
> Read the style guide at `~/.claude/skills/judicial-opinion-edit/references/style-guide.md` and the draft opinion at `[path]`.
>
> Apply the style and grammar rules to the entire opinion. For each proposed edit, produce a structured entry:
>
> ```
> ¶ [paragraph number]
> OLD: [exact original text — enough context to locate uniquely, typically the full sentence]
> NEW: [replacement text]
> REASON: [brief explanation — which rule applies]
> ```
>
> Group entries by paragraph order. Include only changes that improve the text — do not rewrite clear passages. Preserve the court's voice.
>
> For issues that warrant a comment rather than a direct edit (e.g., possible restructuring, ambiguous meaning), use:
>
> ```
> ¶ [paragraph number]
> COMMENT: [the note to attach as a comment in the document]
> ANCHOR: [the word or phrase the comment should attach to]
> ```
>
> Return all entries as a single structured list. Do not produce any other output.

**In main context after collection:** Apply the returned edits mechanically when building the tracked-changes OOXML in step 9. Each `OLD`/`NEW` pair becomes a tracked deletion + tracked insertion. Each `COMMENT` entry becomes a document comment anchored to the specified text.

### Pass 3: Citation Check (Delegated to Subagent)

Pass 3 has two parts: (A) Bluebook format checking, done in the main context, and (B) substantive citation verification against local ND opinion files, delegated to a subagent.

#### Part A: Format Check (Main Context)

Perform these checks in main context as part of Passes 2/5 work:
- Verify Bluebook format for all citations
- Check ND-specific conventions (formats in `references/style-guide.md`)
- Verify pinpoint citations include paragraph or page numbers
- Check signal usage (see, see also, cf., but see, accord)
- Confirm case names are italicized

#### Part B: Substantive Citation Verification (Delegated to Subagent)

**Preparation (in main context):** After reading the opinion, extract a numbered list of every citation to a North Dakota Supreme Court case. For each, record:
- The paragraph (¶) where the citation appears
- The full citation (case name, year ND number, pinpoint ¶)
- The proposition the citation is used to support (the sentence or clause preceding the citation)
- Whether the opinion quotes the case (and if so, the exact quoted text)
- The signal used (none, *See*, *see also*, *cf.*, *but see*, *accord*, etc.)

**Delegation:** Launch a Task subagent (subagent_type: `general-purpose`) with the extracted citation list and the following instructions:

> **ND Opinion Citation Verification**
>
> You have a list of ND Supreme Court citations from a draft opinion. For each citation, verify it against the local markdown opinion files.
>
> **File location:** `$OPINIONS_MD` (fallback: `~/cDocs/refs/ndsc_opinions/markdown/`). Files are organized as `<year>/<year>ND<number>.md`. For example, `2022 ND 210` → `$OPINIONS_MD/2022/2022ND210.md`. Paragraphs are marked `[¶N]` in the markdown.
>
> **For each citation:**
>
> 1. **Locate the file.** Map the citation (e.g., `2014 ND 192`) to its file path (e.g., `$OPINIONS_MD/2014/2014ND192.md`). If the file does not exist, mark the citation as "File not found" and move on.
>
> 2. **Read the cited paragraph.** Use the Read tool to read the file, then locate the pinpoint paragraph (`[¶N]`). If no pinpoint is given, read the full opinion. Read enough surrounding context (the cited ¶ plus 1–2 paragraphs before and after) to understand the point.
>
> 3. **If the opinion quotes the cited case:**
>    - Compare the quoted text against the source paragraph **character by character**.
>    - Flag any discrepancies (missing words, changed words, transpositions).
>    - Identify any bracketed alterations (`[word]`, `[W]ord` for capitalization changes, ellipses `...` or `. . .` for omissions).
>    - For each alteration, note whether the opinion includes an appropriate parenthetical (e.g., "(alteration in original)", "(cleaned up)", "(emphasis added)", "(omission)", "(quoting [Source])"). Under Bluebook Rule 5.2, alterations to quoted material must be indicated, and the parenthetical should appear after the citation.
>    - Report the result as: **Quote verified** (exact match), **Quote verified with noted alterations** (brackets/ellipses present and properly parentheticized), or **Quote discrepancy** (unexplained differences).
>
> 4. **Substantive support check.** Read the cited paragraph in context and assess whether it supports the proposition for which it is cited. Consider:
>    - Does the cited paragraph actually state or hold the legal principle attributed to it?
>    - Is the signal appropriate? (No signal = direct support; *See* = clearly supports; *see also* = additional support; *cf.* = analogous; *but see* = contrary)
>    - Is the proposition a fair characterization, or does it overstate/understate/distort the source?
>    - Report: **Supports** (the cite supports the proposition), **Partially supports** (some nuance lost or overstated), or **Does not support** (the cite does not stand for the stated proposition).
>
> 5. **Build the results table:**
>
> | ¶ | Citation | Quote Check | Alterations | Parenthetical OK? | Supports Proposition? | Notes |
> |---|----------|-------------|-------------|--------------------|-----------------------|-------|
> | [¶] | [Case, cite] | Verified / Verified w/ alterations / Discrepancy / No quote / File not found | [List any brackets, ellipses, emphasis changes] | Yes / No / N/A | Supports / Partially / Does not support | [Explanation] |
>
> 6. **Return** the completed table and a summary: [X] ND citations checked. [Y] quotes verified. [Z] quote discrepancies. [W] files not found. [V] citations that may not support the stated proposition.

### Pass 4: Fact Check (Delegated to Subagent)

When the user provides briefs, record documents, or other source materials alongside the draft opinion, **do not** read the PDF materials into the main context. Delegate fact-checking to a subagent to keep potentially large PDF content out of the main context window.

**Preparation (in main context):** After reading the opinion, extract a numbered list of verifiable factual claims with paragraph references. Include:
- Dates, names, places, and sequences of events
- Procedural history (filings, motions, rulings, verdicts, sentences)
- Descriptions of testimony or evidence
- Characterizations of parties' arguments
- Statements about the record (e.g., "Davis did not object," "the jury was instructed")

Do **not** include: legal standards and rules (checked in Passes 1 and 3), the court's own reasoning and conclusions, or general statements of law from cited cases.

**Delegation:** Launch a Task subagent (subagent_type: `general-purpose`) with the following instructions and the extracted claims list:

- For each PDF source file, extract text locally: `pdftotext <file>.pdf <file>.txt`
- Use Grep to search the extracted `.txt` files for passages relevant to each claim — **do not** read entire documents into context
- For each claim, build a row:

| ¶ | Claim | Source Document(s) | Result | Notes |
|---|-------|-------------------|--------|-------|
| [¶ ref] | [Factual assertion] | [Source with pinpoint cite] | Verified / Unverified / Discrepancy | [Explanation] |

- Return the completed table with a summary line: [X] facts checked, [Y] verified, [Z] discrepancies, [W] unverified.

**No source materials:** If the user does not provide source materials, skip delegation. Note this limitation in the analysis and flag any factual assertions that cannot be independently verified.

### Pass 5: Analytical Rigor

Checks vary by `DOC_TYPE`. Full details for both document types are in `references/style-guide.md`.

#### If DOC_TYPE is `opinion` (default)

- Flag potential dicta (statements unnecessary to the holding)
- Flag unnecessary alternative rationales
- Identify logical fallacies
- Identify ambiguities — especially passages easily quoted out of context
- Read from the losing party's perspective: what would a critic seize on?
- Flag holdings broader than necessary
- Flag vague standards lacking guidance for future application

#### If DOC_TYPE is `memo`

- **Issue completeness:** Did the memo identify all issues raised on appeal? Are there issues the parties didn't raise but the court should consider (e.g., plain error, jurisdictional defects)?
- **Balanced presentation:** Does the memo fairly state each side's strongest arguments? Does it steelman the weaker position or dismiss it too quickly?
- **Recommendation quality:** Are recommendations clearly stated? Is each recommendation supported by the analysis? Are alternative outcomes acknowledged?
- **Analytical gaps:** Are there unstated assumptions? Logical fallacies? Missing steps in the reasoning chain?
- **Standard of review:** Does the memo correctly identify and consistently apply the appropriate standard of review for each issue?

## Output Format

Produce the outputs requested by the user in Step 0.5.

### Tracked-changes .docx (if requested)
Use the docx skill to produce a .docx with:
- Deletions as tracked deletions (author: "Claude")
- Insertions as tracked insertions (author: "Claude")
- Comments (via comment.py) for substantive notes — explaining a change or flagging an issue

### Analysis document (if requested)
Produce a document structured as below. The **Substantive Concerns** section varies by `DOC_TYPE`.

```
–Begin Analysis–

## Jurisdictional Notes
[Issues with timeliness of appeal, procedural posture, or standard of review]
[If DOC_TYPE is memo and jurisdiction was not addressed: include warning here]

## Summary of Edits
[Brief overview of the types and volume of changes]

## Fact Check

| ¶ | Claim | Source Document(s) | Result | Notes |
|---|-------|-------------------|--------|-------|
| [¶ ref] | [Factual assertion from document] | [Record doc, brief, or transcript with pinpoint cite] | Verified / Unverified / Discrepancy | [Explanation if discrepancy or unverified] |

**Summary:** [X] facts checked. [Y] verified. [Z] discrepancies. [W] unverified.
```

**If DOC_TYPE is `opinion`:**

```
## Substantive Concerns

### Potential Dicta
[List with paragraph references]

### Alternative Rationales
[Whether each ground is fully developed]

### Ambiguity and Vulnerability
[Passages quotable out of context; vague standards; overly broad holdings]

### Logical Issues
[Logical fallacies or unstated assumptions]
```

**If DOC_TYPE is `memo`:**

```
## Memo Analysis

### Issue Completeness
[Issues raised on appeal; issues not raised but potentially relevant (plain error, jurisdictional defects)]

### Balance of Presentation
[Whether each side's strongest arguments are fairly stated; steelmanning assessment]

### Recommendation Assessment
[Clarity and support for each recommendation; alternative outcomes acknowledged]

### Analytical Gaps
[Unstated assumptions, logical fallacies, missing reasoning steps]

### Standard of Review Application
[Whether the memo correctly identifies and consistently applies the standard of review for each issue]
```

**Both document types continue with:**

```
## Citation Verification

| ¶ | Citation | Quote Check | Alterations | Parenthetical OK? | Supports Proposition? | Notes |
|---|----------|-------------|-------------|--------------------|-----------------------|-------|
| [¶] | [Case, cite] | Verified / Verified w/ alterations / Discrepancy / No quote / File not found | [Brackets, ellipses, emphasis changes] | Yes / No / N/A | Supports / Partially / Does not support | [Explanation] |

**Summary:** [X] ND citations checked. [Y] quotes verified. [Z] quote discrepancies. [W] files not found. [V] unsupported propositions.

## Citation Format Issues
[Citation-format corrections with explanations]

## Style Notes
[Significant style changes by category]

---
*Generated by judicial-opinion-edit v1.0 (2026-02-24)*
*Claude Opus 4.6 · Justice Jerod Tufte, North Dakota Supreme Court*

–End Analysis–
```

## Key Reminders

- Minimal edits: change only what improves the text. Do not rewrite clear passages.
- Preserve the court's voice. Polish, do not impose a different style.
- When uncertain, use a comment rather than a tracked change.
- For complex restructuring, describe the proposal in a comment.
- Bold changed words in the analysis to distinguish from unchanged text.
