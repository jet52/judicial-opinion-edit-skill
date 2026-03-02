#!/usr/bin/env python3
"""OOXML post-processing fixup for JetRedline.

Runs after all edits are applied, before packing. Resolves ID collisions,
deduplicates relationships, cleans orphaned comment artifacts, and fixes
xml:space="preserve" attributes.

Usage:
    python ooxml_fixup.py <unpacked_dir>

Outputs JSON summary to stdout.
"""

import json
import os
import sys
from pathlib import Path

import defusedxml.minidom as minidom


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_xml(path):
    """Parse an XML file with defusedxml. Returns (doc, True) or (None, False)."""
    try:
        doc = minidom.parse(str(path))
        return doc, True
    except Exception:
        return None, False


def write_xml(doc, path):
    """Write a minidom document back to file, preserving XML declaration."""
    xml_str = doc.toxml("utf-8")
    Path(path).write_bytes(xml_str)


def get_elements_by_tag(doc, tag):
    """Get all elements matching a tag (handles namespaced tags)."""
    return doc.getElementsByTagName(tag)


def collect_w_ids(doc, tags):
    """Collect all w:id values from given element tag names. Returns {id_int: [(tag, element)]}."""
    id_map = {}
    for tag in tags:
        for el in get_elements_by_tag(doc, tag):
            val = el.getAttribute("w:id")
            if not val:
                continue
            try:
                id_int = int(val)
            except ValueError:
                continue
            id_map.setdefault(id_int, []).append((tag, el))
    return id_map


# ---------------------------------------------------------------------------
# A. ID deconfliction
# ---------------------------------------------------------------------------

BOOKMARK_TAGS = ["w:bookmarkStart", "w:bookmarkEnd"]
COMMENT_DOC_TAGS = ["w:commentRangeStart", "w:commentRangeEnd", "w:commentReference"]
CHANGE_TAGS = ["w:ins", "w:del", "w:rPrChange", "w:pPrChange", "w:sectPrChange",
               "w:tblPrChange", "w:trPrChange", "w:tcPrChange", "w:tblGridChange"]


def deconflict_ids(unpacked_dir):
    """Renumber comment and tracked-change IDs to avoid collisions with bookmarks."""
    summary = {"comments_renumbered": 0, "changes_renumbered": 0}

    doc_path = unpacked_dir / "word" / "document.xml"
    comments_path = unpacked_dir / "word" / "comments.xml"

    doc, ok = parse_xml(doc_path)
    if not ok:
        return summary

    # Collect ALL w:id values across annotation types in document.xml
    all_tags = BOOKMARK_TAGS + COMMENT_DOC_TAGS + CHANGE_TAGS
    all_ids = collect_w_ids(doc, all_tags)
    bookmark_ids = collect_w_ids(doc, BOOKMARK_TAGS)
    comment_doc_ids = collect_w_ids(doc, COMMENT_DOC_TAGS)
    change_ids = collect_w_ids(doc, CHANGE_TAGS)

    # Find the max ID across all annotation types
    all_id_values = set(all_ids.keys())
    if not all_id_values:
        return summary

    max_id = max(all_id_values)

    # Check if there are actual collisions; if not, skip
    bookmark_id_set = set(bookmark_ids.keys())
    comment_id_set = set(comment_doc_ids.keys())
    change_id_set = set(change_ids.keys())

    has_collision = bool(
        (bookmark_id_set & comment_id_set) or
        (bookmark_id_set & change_id_set) or
        (comment_id_set & change_id_set)
    )

    if not has_collision:
        return summary

    # Parse comments.xml for consistent renumbering
    comments_doc = None
    if comments_path.exists():
        comments_doc, _ = parse_xml(comments_path)

    # Build old→new mapping for comments
    next_id = max_id + 1
    comment_id_remap = {}
    for old_id in sorted(comment_id_set):
        if old_id in bookmark_id_set or old_id in change_id_set:
            comment_id_remap[old_id] = next_id
            next_id += 1

    # Renumber comments in document.xml
    for old_id, new_id in comment_id_remap.items():
        if old_id in comment_doc_ids:
            for tag, el in comment_doc_ids[old_id]:
                el.setAttribute("w:id", str(new_id))
                summary["comments_renumbered"] += 1

    # Renumber comments in comments.xml
    if comments_doc and comment_id_remap:
        for comment_el in get_elements_by_tag(comments_doc, "w:comment"):
            val = comment_el.getAttribute("w:id")
            if not val:
                continue
            try:
                old_id = int(val)
            except ValueError:
                continue
            if old_id in comment_id_remap:
                comment_el.setAttribute("w:id", str(comment_id_remap[old_id]))

    # Build old→new mapping for tracked changes
    change_id_remap = {}
    for old_id in sorted(change_id_set):
        if old_id in bookmark_id_set or old_id in comment_id_set:
            change_id_remap[old_id] = next_id
            next_id += 1

    # Renumber tracked changes in document.xml
    for old_id, new_id in change_id_remap.items():
        if old_id in change_ids:
            for tag, el in change_ids[old_id]:
                el.setAttribute("w:id", str(new_id))
                summary["changes_renumbered"] += 1

    # Write back
    write_xml(doc, doc_path)
    if comments_doc and comment_id_remap:
        write_xml(comments_doc, comments_path)

    return summary


# ---------------------------------------------------------------------------
# B. Deduplicate relationships
# ---------------------------------------------------------------------------

def dedup_relationships(unpacked_dir):
    """Remove duplicate entries from [Content_Types].xml and all .rels files."""
    summary = {"content_types_removed": 0, "rels_removed": 0}

    # [Content_Types].xml
    ct_path = unpacked_dir / "[Content_Types].xml"
    if ct_path.exists():
        doc, ok = parse_xml(ct_path)
        if ok:
            root = doc.documentElement
            # Dedup Override by PartName
            seen = set()
            for el in list(get_elements_by_tag(doc, "Override")):
                key = el.getAttribute("PartName")
                if key in seen:
                    el.parentNode.removeChild(el)
                    summary["content_types_removed"] += 1
                else:
                    seen.add(key)
            # Dedup Default by Extension
            seen = set()
            for el in list(get_elements_by_tag(doc, "Default")):
                key = el.getAttribute("Extension")
                if key in seen:
                    el.parentNode.removeChild(el)
                    summary["content_types_removed"] += 1
                else:
                    seen.add(key)
            if summary["content_types_removed"] > 0:
                write_xml(doc, ct_path)

    # All .rels files
    for rels_path in unpacked_dir.rglob("*.rels"):
        doc, ok = parse_xml(rels_path)
        if not ok:
            continue
        seen = set()
        removed = 0
        for el in list(get_elements_by_tag(doc, "Relationship")):
            key = (el.getAttribute("Type"), el.getAttribute("Target"))
            if key in seen:
                el.parentNode.removeChild(el)
                removed += 1
            else:
                seen.add(key)
        if removed > 0:
            write_xml(doc, rels_path)
            summary["rels_removed"] += removed

    return summary


# ---------------------------------------------------------------------------
# C. Clean orphaned comment artifacts
# ---------------------------------------------------------------------------

def clean_orphaned_comments(unpacked_dir):
    """Remove entries from commentsExtended/commentsIds/commentsExtensible
    that don't correspond to actual w:comment entries in comments.xml."""
    summary = {"orphans_removed": 0}

    comments_path = unpacked_dir / "word" / "comments.xml"
    if not comments_path.exists():
        return summary

    comments_doc, ok = parse_xml(comments_path)
    if not ok:
        return summary

    # Collect paraIds from comments.xml
    valid_para_ids = set()
    for comment_el in get_elements_by_tag(comments_doc, "w:comment"):
        # Each w:comment may contain paragraphs with w14:paraId
        for p_el in comment_el.getElementsByTagName("w:p"):
            para_id = (p_el.getAttribute("w14:paraId") or
                       p_el.getAttribute("w:paraId"))
            if para_id:
                valid_para_ids.add(para_id)

    # Also collect comment IDs for commentsExtensible (uses durableId linkage)
    valid_comment_ids = set()
    for comment_el in get_elements_by_tag(comments_doc, "w:comment"):
        cid = comment_el.getAttribute("w:id")
        if cid:
            valid_comment_ids.add(cid)

    # Process commentsExtended.xml
    ext_path = unpacked_dir / "word" / "commentsExtended.xml"
    durable_ids_from_valid = set()
    if ext_path.exists():
        ext_doc, ok = parse_xml(ext_path)
        if ok:
            removed = 0
            for el in list(get_elements_by_tag(ext_doc, "w15:commentEx")):
                para_id = el.getAttribute("w15:paraId")
                if para_id and para_id not in valid_para_ids:
                    el.parentNode.removeChild(el)
                    removed += 1
                elif para_id and para_id in valid_para_ids:
                    # Track durable IDs that correspond to valid comments
                    did = el.getAttribute("w15:durableId")
                    if did:
                        durable_ids_from_valid.add(did)
            if removed > 0:
                write_xml(ext_doc, ext_path)
                summary["orphans_removed"] += removed

    # Process commentsIds.xml
    ids_path = unpacked_dir / "word" / "commentsIds.xml"
    if ids_path.exists():
        ids_doc, ok = parse_xml(ids_path)
        if ok:
            removed = 0
            for el in list(get_elements_by_tag(ids_doc, "w16cid:commentId")):
                para_id = el.getAttribute("w16cid:paraId")
                if para_id and para_id not in valid_para_ids:
                    el.parentNode.removeChild(el)
                    removed += 1
            if removed > 0:
                write_xml(ids_doc, ids_path)
                summary["orphans_removed"] += removed

    # Process commentsExtensible.xml (keyed by durableId)
    extensible_path = unpacked_dir / "word" / "commentsExtensible.xml"
    if extensible_path.exists():
        ext_doc, ok = parse_xml(extensible_path)
        if ok:
            removed = 0
            for el in list(get_elements_by_tag(ext_doc, "w16cex:commentExtensible")):
                durable_id = el.getAttribute("w16cex:durableId")
                if durable_id and durable_ids_from_valid and durable_id not in durable_ids_from_valid:
                    el.parentNode.removeChild(el)
                    removed += 1
            if removed > 0:
                write_xml(ext_doc, extensible_path)
                summary["orphans_removed"] += removed

    return summary


# ---------------------------------------------------------------------------
# D. Fix xml:space="preserve"
# ---------------------------------------------------------------------------

def fix_xml_space(unpacked_dir):
    """Add xml:space='preserve' to w:t elements with leading/trailing whitespace."""
    summary = {"space_attrs_added": 0}

    doc_path = unpacked_dir / "word" / "document.xml"
    doc, ok = parse_xml(doc_path)
    if not ok:
        return summary

    modified = False
    for wt in get_elements_by_tag(doc, "w:t"):
        # Get text content
        text = ""
        for child in wt.childNodes:
            if child.nodeType == child.TEXT_NODE:
                text += child.data
        if not text:
            continue
        if text != text.strip():
            # Has leading/trailing whitespace
            if not wt.getAttribute("xml:space"):
                wt.setAttribute("xml:space", "preserve")
                summary["space_attrs_added"] += 1
                modified = True

    if modified:
        write_xml(doc, doc_path)

    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <unpacked_dir>", file=sys.stderr)
        sys.exit(1)

    unpacked_dir = Path(sys.argv[1])
    if not unpacked_dir.is_dir():
        print(f"Error: {unpacked_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    results = {}
    results["id_deconfliction"] = deconflict_ids(unpacked_dir)
    results["relationship_dedup"] = dedup_relationships(unpacked_dir)
    results["orphan_cleanup"] = clean_orphaned_comments(unpacked_dir)
    results["xml_space_fix"] = fix_xml_space(unpacked_dir)

    # Compute total changes
    total = sum(
        v for section in results.values() for v in section.values()
    )
    results["total_changes"] = total

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
