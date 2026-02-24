# Temporary File Configuration

## Problem Statement

The judicial-opinion-edit skill was creating temporary files in system-wide locations (`/tmp` or `~/tmp`), which caused:

1. **Permission prompts**: Numerous requests for access to tmp/ during skill execution
2. **Collision risk**: If the skill ran on two different cases simultaneously, temp files could collide
3. **Lack of isolation**: Case files scattered across system rather than kept together

## Solution

**Use working-directory-relative temp files** via the `TMPDIR` environment variable.

### How It Works

Python's `tempfile` module (used by the docx skill) respects the `TMPDIR` environment variable. When set, all temporary files are created in that location instead of the system default.

In Step 0, a uniquely-named temp directory is created using three random dictionary words (e.g., `.tmp-apple-walrus-quilt`). The absolute path is captured and used as a literal `TMPDIR=<path>` prefix — no `$(pwd)` command substitution, which eliminates repeated permission prompts.

This ensures:
- ✅ All temp files for a case go into `<case-directory>/.tmp-<random>/`
- ✅ No collisions between concurrent runs (unique name per session)
- ✅ All case-related files stay together
- ✅ Easy cleanup (just delete the `.tmp-*` directory when done)
- ✅ No repeated command-substitution permission prompts

### Implementation

#### 1. Skill Documentation Updated

The `SKILL.md` file now documents that:
- A uniquely-named `.tmp-<word1>-<word2>-<word3>` directory is created in Step 0
- The absolute path is captured once and used as a literal `TMPDIR=<path>` prefix in all commands
- No `$(pwd)` command substitution is used, avoiding repeated permission prompts

#### 2. Settings Permissions Updated

Added pre-authorization in `~/.claude/settings.json` for:
```json
"Read(**/.tmp/**)",
"Write(**/.tmp/**)",
"Glob(**/.tmp/**)",
"Grep(**/.tmp/**)"
```

These permissions authorize read/write access to any `.tmp/` directory in any working directory, eliminating permission prompts.

#### 3. Workflow Updated

Step 0 of the workflow now includes creating the `.tmp/` directory:
```bash
mkdir -p .tmp
```

This ensures the directory exists before any Python scripts try to create temp files.

### Usage Pattern

In Step 0, run once to create a unique temp dir and capture the path:
```bash
SKILL_TMPDIR="$PWD/.tmp-$(awk 'BEGIN{srand()}{a[NR]=tolower($0)}END{for(i=1;i<=3;i++)printf "%s%s",(i>1?"-":""),a[int(rand()*NR)+1]}' /usr/share/dict/words)" && mkdir -p "$SKILL_TMPDIR" && echo "$SKILL_TMPDIR"
```

Then use the literal output path in all subsequent commands:
```bash
TMPDIR=/path/to/cases/smith/.tmp-apple-walrus-quilt PYTHONPATH=/path/to/docx/ /path/to/python script.py
```

### Benefits

1. **No more permission prompts**: Pre-authorized access to `.tmp/` directories
2. **Isolation**: Each case has its own temp space
3. **No collisions**: Multiple concurrent skill runs don't interfere
4. **Organization**: All case files in one directory tree
5. **Easy cleanup**: `rm -rf .tmp/` removes all temporary files

### Testing

To verify the configuration is working:

1. Navigate to a case directory
2. Run the skill on a draft opinion
3. Check that temp files appear in `./.tmp/` (not `/tmp` or `~/tmp`)
4. Verify you receive no permission prompts for temp file access

### Cleanup

The `.tmp-*` directory can be safely deleted after processing:
```bash
rm -rf .tmp-*/
```

You may want to add `.tmp-*` to your `.gitignore` if the working directories are git repositories.

## Technical Details

### Where the Issue Originated

The docx skill's `document.py` (line 640) uses:
```python
self.temp_dir = tempfile.mkdtemp(prefix="docx_")
```

Without `TMPDIR` set, Python uses:
- macOS/Linux: `/tmp/` or `/var/tmp/`
- Or `~/tmp/` if configured via `TMPDIR` in shell profile

### Why TMPDIR Works

From Python's tempfile documentation:
> The default directory is chosen from a platform-dependent list, but the user may control the directory location by setting the TMPDIR, TEMP or TMP environment variables.

By setting `TMPDIR` in the command environment, we override Python's default temp location for just that command execution.

### Why Not Modify the Plugin Code?

The docx skill is part of the `document-skills` plugin maintained by Anthropic. Modifying plugin code would:
- Get overwritten on plugin updates
- Break compatibility with other skills using the same plugin
- Require maintaining a fork of the plugin

Using `TMPDIR` is the standard, non-invasive solution that works with any tool using Python's tempfile module.
