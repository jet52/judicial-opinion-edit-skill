#!/usr/bin/env python3
"""Batch edit helper for JetRedline.

Applies a JSON array of edits (tracked deletions + insertions + comments) to an
unpacked .docx directory using the docx plugin's Document API, then runs
ooxml_fixup.py and ooxml_validate.py.

Usage:
    python apply_edits.py --input <unpacked_dir> --edits <edits.json> \
        [--author "Claude"] [--output <output.docx>]

Edits JSON format:
    [
        {
            "type": "replace",
            "para": 3,
            "old": "exact text to delete",
            "new": "replacement text",
            "comment": "optional explanation"
        },
        {
            "type": "comment",
            "para": 5,
            "anchor": "text to attach comment to",
            "comment": "the comment text"
        }
    ]

For "replace" edits:
    - "para" is the 1-indexed paragraph number (¶) for disambiguation.
      If omitted, searches all paragraphs.
    - "old" is the exact text to find and mark as deleted.
    - "new" is the replacement text to insert.
    - "comment" is an optional explanation attached to the change.

For "comment" edits:
    - "para" is the paragraph number.
    - "anchor" is the text the comment attaches to.
    - "comment" is the comment text.

Exit codes:
    0  — success
    1  — one or more edits failed to apply (error JSON on stdout)
    2  — argument/setup error
"""

import argparse
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve docx plugin path from PYTHONPATH or known location
# ---------------------------------------------------------------------------
DOCX_PLUGIN_PATH = Path(os.environ.get(
    "DOCX_PLUGIN_PATH",
    os.path.expanduser(
        "~/.claude/plugins/cache/anthropic-agent-skills/"
        "document-skills/69c0b1a06741/skills/docx"
    ),
))
SKILL_DIR = Path(__file__).parent


def setup_python_path():
    """Add docx plugin to sys.path so we can import Document."""
    plugin_path = str(DOCX_PLUGIN_PATH)
    if plugin_path not in sys.path:
        sys.path.insert(0, plugin_path)
    # Also add parent for ooxml imports
    parent = str(DOCX_PLUGIN_PATH.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def get_paragraph_text(para_elem):
    """Extract concatenated text from all w:t and w:delText elements in a paragraph."""
    texts = []
    for tag_name in ("w:t", "w:delText"):
        for t in para_elem.getElementsByTagName(tag_name):
            for child in t.childNodes:
                if child.nodeType == child.TEXT_NODE:
                    texts.append(child.data)
    return "".join(texts)


def get_run_text(run_elem):
    """Extract text from w:t elements in a single run."""
    texts = []
    for t in run_elem.getElementsByTagName("w:t"):
        for child in t.childNodes:
            if child.nodeType == child.TEXT_NODE:
                texts.append(child.data)
    return "".join(texts)


def find_paragraph_by_number(editor, para_num):
    """Find the para_num-th w:p element (1-indexed) in the document body."""
    body = editor.dom.getElementsByTagName("w:body")
    if not body:
        return None
    paragraphs = body[0].getElementsByTagName("w:p")
    if para_num < 1 or para_num > len(paragraphs):
        return None
    return paragraphs[para_num - 1]


def find_paragraph_containing(editor, text, para_num=None):
    """Find a paragraph containing the given text.

    If para_num is provided, search only that paragraph first, then fall back
    to scanning all paragraphs.
    """
    body = editor.dom.getElementsByTagName("w:body")
    if not body:
        return None
    paragraphs = list(body[0].getElementsByTagName("w:p"))

    # Try the specified paragraph first
    if para_num is not None and 1 <= para_num <= len(paragraphs):
        p = paragraphs[para_num - 1]
        if text in get_paragraph_text(p):
            return p

    # Fall back to scanning all paragraphs
    for p in paragraphs:
        if text in get_paragraph_text(p):
            return p
    return None


# ---------------------------------------------------------------------------
# Tracked-change application
# ---------------------------------------------------------------------------

def apply_replace(doc, editor, edit, edit_index):
    """Apply a replace edit: mark old text as deleted, insert new text.

    Strategy:
    1. Find the paragraph containing old text
    2. Walk runs to find which ones contain the old text
    3. Split runs at text boundaries if needed
    4. Wrap the old-text runs in <w:del>, insert <w:ins> with new text after

    Returns dict with status info.
    """
    old_text = edit["old"]
    new_text = edit["new"]
    para_num = edit.get("para")
    comment_text = edit.get("comment")

    # Find the target paragraph
    para = find_paragraph_containing(editor, old_text, para_num)
    if para is None:
        return {
            "edit_index": edit_index,
            "status": "error",
            "message": f"Could not find paragraph containing: {old_text[:80]}..."
        }

    # Collect runs (w:r elements that are direct or near-direct children of the paragraph,
    # not already inside w:del or w:ins)
    runs = []
    for child in para.childNodes:
        if child.nodeType == child.ELEMENT_NODE:
            if child.tagName == "w:r":
                runs.append(child)
            elif child.tagName in ("w:ins", "w:del"):
                # Collect runs inside tracked changes too
                for r in child.getElementsByTagName("w:r"):
                    runs.append(r)
            elif child.tagName == "w:hyperlink":
                for r in child.getElementsByTagName("w:r"):
                    runs.append(r)

    # Build a text map: for each run, track its text and position in the
    # concatenated paragraph text
    text_map = []  # [(run, run_text, start_offset, end_offset)]
    offset = 0
    for run in runs:
        rt = get_run_text(run)
        if rt:
            text_map.append((run, rt, offset, offset + len(rt)))
            offset += len(rt)

    # Find old_text in the concatenated text
    full_text = "".join(item[1] for item in text_map)
    match_start = full_text.find(old_text)
    if match_start == -1:
        return {
            "edit_index": edit_index,
            "status": "error",
            "message": f"Text not found in paragraph runs: {old_text[:80]}..."
        }
    match_end = match_start + len(old_text)

    # Identify which runs are affected
    affected_runs = []  # [(run, portion_start, portion_end)] — offsets within the run's text
    for run, rt, r_start, r_end in text_map:
        if r_end <= match_start or r_start >= match_end:
            continue  # No overlap
        # Calculate the portion of this run that overlaps with the match
        portion_start = max(0, match_start - r_start)
        portion_end = min(len(rt), match_end - r_start)
        affected_runs.append((run, rt, portion_start, portion_end))

    if not affected_runs:
        return {
            "edit_index": edit_index,
            "status": "error",
            "message": f"No runs overlap with matched text: {old_text[:80]}..."
        }

    # Now apply the tracked change.
    # For each affected run, we may need to split it into up to 3 parts:
    #   [before_text] [matched_text] [after_text]
    # The matched_text part goes into w:del; before/after stay as normal runs.

    dom = editor.dom
    first_del = None
    last_del = None

    for run, rt, portion_start, portion_end in affected_runs:
        before_text = rt[:portion_start]
        matched_text = rt[portion_start:portion_end]
        after_text = rt[portion_end:]

        parent = run.parentNode

        # If the run is already inside a w:del or w:ins, skip it
        # (we don't double-wrap tracked changes)
        if parent.tagName in ("w:del", "w:ins"):
            return {
                "edit_index": edit_index,
                "status": "skipped",
                "message": f"Run already has tracked changes, skipping: {old_text[:80]}..."
            }

        # Clone the run's formatting (w:rPr)
        rPr_nodes = run.getElementsByTagName("w:rPr")
        rPr_xml = rPr_nodes[0].toxml() if rPr_nodes else ""

        # Build the "before" run if there's text before the match
        if before_text:
            space_attr = ' xml:space="preserve"' if before_text != before_text.strip() else ""
            before_run_xml = f'<w:r>{rPr_xml}<w:t{space_attr}>{_escape_xml(before_text)}</w:t></w:r>'
            editor.insert_before(run, before_run_xml)

        # Build the deletion run
        space_attr_del = ' xml:space="preserve"' if matched_text != matched_text.strip() else ""
        del_run_xml = f'<w:r>{rPr_xml}<w:delText{space_attr_del}>{_escape_xml(matched_text)}</w:delText></w:r>'
        del_wrapper_xml = f'<w:del>{del_run_xml}</w:del>'
        del_nodes = editor.insert_before(run, del_wrapper_xml)
        del_elem = del_nodes[0] if del_nodes else None

        if first_del is None:
            first_del = del_elem
        last_del = del_elem

        # Build the "after" run if there's text after the match
        if after_text:
            space_attr = ' xml:space="preserve"' if after_text != after_text.strip() else ""
            after_run_xml = f'<w:r>{rPr_xml}<w:t{space_attr}>{_escape_xml(after_text)}</w:t></w:r>'
            editor.insert_before(run, after_run_xml)

        # Remove the original run
        parent.removeChild(run)

    # Insert the new text as a tracked insertion after the last deletion
    if last_del is not None and new_text:
        # Use the formatting from the first affected run
        rPr_nodes = affected_runs[0][0].getElementsByTagName("w:rPr")
        rPr_xml = rPr_nodes[0].toxml() if rPr_nodes else ""
        space_attr_ins = ' xml:space="preserve"' if new_text != new_text.strip() else ""
        ins_run_xml = f'<w:r>{rPr_xml}<w:t{space_attr_ins}>{_escape_xml(new_text)}</w:t></w:r>'
        ins_wrapper_xml = f'<w:ins>{ins_run_xml}</w:ins>'
        ins_nodes = editor.insert_after(last_del, ins_wrapper_xml)
        ins_elem = ins_nodes[0] if ins_nodes else None
    else:
        ins_elem = None

    # Add comment if provided
    if comment_text and first_del is not None:
        anchor_end = ins_elem if ins_elem else last_del
        try:
            doc.add_comment(start=first_del, end=anchor_end, text=comment_text)
        except Exception as e:
            # Non-fatal: comment failed but edit succeeded
            return {
                "edit_index": edit_index,
                "status": "partial",
                "message": f"Edit applied but comment failed: {e}"
            }

    return {"edit_index": edit_index, "status": "ok"}


def apply_comment(doc, editor, edit, edit_index):
    """Apply a comment-only edit."""
    anchor_text = edit.get("anchor", "")
    comment_text = edit["comment"]
    para_num = edit.get("para")

    para = find_paragraph_containing(editor, anchor_text, para_num)
    if para is None:
        # Fall back to paragraph number
        if para_num:
            para = find_paragraph_by_number(editor, para_num)
        if para is None:
            return {
                "edit_index": edit_index,
                "status": "error",
                "message": f"Could not find paragraph for comment anchor: {anchor_text[:80]}..."
            }

    # Find the run containing the anchor text
    anchor_run = None
    if anchor_text:
        for run in para.getElementsByTagName("w:r"):
            if anchor_text in get_run_text(run):
                anchor_run = run
                break

    # Use the run if found, otherwise use the paragraph
    start = anchor_run if anchor_run else para
    end = anchor_run if anchor_run else para

    try:
        doc.add_comment(start=start, end=end, text=comment_text)
    except Exception as e:
        return {
            "edit_index": edit_index,
            "status": "error",
            "message": f"Failed to add comment: {e}"
        }

    return {"edit_index": edit_index, "status": "ok"}


def _escape_xml(text):
    """Escape text for XML content, preserving Unicode."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# Post-processing: fixup + validate
# ---------------------------------------------------------------------------

def run_fixup(unpacked_dir):
    """Run ooxml_fixup.py on the unpacked directory."""
    fixup_script = SKILL_DIR / "ooxml_fixup.py"
    venv_python = SKILL_DIR / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable

    result = subprocess.run(
        [python, str(fixup_script), str(unpacked_dir)],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        return {"status": "error", "message": result.stderr}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "ok", "raw": result.stdout}


def run_validate(unpacked_dir):
    """Run ooxml_validate.py on the unpacked directory."""
    validate_script = SKILL_DIR / "ooxml_validate.py"
    venv_python = SKILL_DIR / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable

    result = subprocess.run(
        [python, str(validate_script), str(unpacked_dir)],
        capture_output=True, text=True, timeout=60
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "PASS" if result.returncode == 0 else "FAIL", "raw": result.stdout}


def pack_output(unpacked_dir, output_path):
    """Pack the unpacked directory back into a .docx file."""
    pack_script = DOCX_PLUGIN_PATH / "ooxml" / "scripts" / "pack.py"
    venv_python = SKILL_DIR / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable

    env = os.environ.copy()
    env["PYTHONPATH"] = str(DOCX_PLUGIN_PATH)
    # Ensure LibreOffice is on PATH for validation
    env["PATH"] = "/Applications/LibreOffice.app/Contents/MacOS:" + env.get("PATH", "")

    result = subprocess.run(
        [python, str(pack_script), str(unpacked_dir), str(output_path), "--force"],
        capture_output=True, text=True, timeout=120, env=env
    )
    if result.returncode != 0:
        return {"status": "error", "message": result.stderr}
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Apply batch edits to an unpacked .docx as tracked changes"
    )
    parser.add_argument("--input", required=True, help="Path to unpacked .docx directory")
    parser.add_argument("--edits", required=True, help="Path to edits JSON file")
    parser.add_argument("--author", default="Claude", help="Author name for tracked changes")
    parser.add_argument("--output", help="Output .docx path (if omitted, edits are applied in-place)")
    parser.add_argument("--no-fixup", action="store_true", help="Skip ooxml_fixup.py")
    parser.add_argument("--no-validate", action="store_true", help="Skip ooxml_validate.py")
    parser.add_argument("--no-pack", action="store_true", help="Skip packing into .docx")
    args = parser.parse_args()

    unpacked_dir = Path(args.input)
    if not unpacked_dir.is_dir():
        print(json.dumps({"status": "error", "message": f"Not a directory: {args.input}"}))
        sys.exit(2)

    edits_path = Path(args.edits)
    if not edits_path.exists():
        print(json.dumps({"status": "error", "message": f"Edits file not found: {args.edits}"}))
        sys.exit(2)

    try:
        edits = json.loads(edits_path.read_text())
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "message": f"Invalid JSON in edits file: {e}"}))
        sys.exit(2)

    if not isinstance(edits, list):
        print(json.dumps({"status": "error", "message": "Edits must be a JSON array"}))
        sys.exit(2)

    # Set up imports
    setup_python_path()
    from scripts.document import Document

    # Initialize Document (handles RSID, people.xml, settings.xml)
    try:
        doc = Document(str(unpacked_dir), author=args.author)
    except Exception as e:
        print(json.dumps({"status": "error", "message": f"Failed to initialize Document: {e}"}))
        sys.exit(2)

    editor = doc["word/document.xml"]

    # Apply each edit
    results = []
    errors = []
    for i, edit in enumerate(edits):
        edit_type = edit.get("type", "replace")
        if edit_type == "replace":
            result = apply_replace(doc, editor, edit, i)
        elif edit_type == "comment":
            result = apply_comment(doc, editor, edit, i)
        else:
            result = {"edit_index": i, "status": "error", "message": f"Unknown edit type: {edit_type}"}

        results.append(result)
        if result["status"] == "error":
            errors.append(result)

    # Save the Document (writes XML back to the unpacked directory)
    try:
        doc.save(validate=False)
    except Exception as e:
        print(json.dumps({
            "status": "error",
            "message": f"Failed to save document: {e}",
            "edit_results": results
        }))
        sys.exit(1)

    # Run ooxml_fixup.py
    fixup_result = None
    if not args.no_fixup:
        fixup_result = run_fixup(unpacked_dir)

    # Run ooxml_validate.py
    validate_result = None
    if not args.no_validate:
        validate_result = run_validate(unpacked_dir)

    # Pack into .docx if output specified
    pack_result = None
    if args.output and not args.no_pack:
        pack_result = pack_output(unpacked_dir, args.output)

    # Build summary
    summary = {
        "status": "error" if errors else "ok",
        "edits_total": len(edits),
        "edits_applied": sum(1 for r in results if r["status"] == "ok"),
        "edits_partial": sum(1 for r in results if r["status"] == "partial"),
        "edits_skipped": sum(1 for r in results if r["status"] == "skipped"),
        "edits_failed": len(errors),
        "edit_results": results,
    }

    if fixup_result:
        summary["fixup"] = fixup_result
    if validate_result:
        summary["validation"] = validate_result
    if pack_result:
        summary["pack"] = pack_result

    print(json.dumps(summary, indent=2))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
