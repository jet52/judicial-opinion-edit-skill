#!/usr/bin/env python3
"""
ND Citation Checker — parses North Dakota legal citations, resolves local
files, and builds verification URLs.

Usage:
    python3 nd_cite_check.py --file opinion.md
    echo "N.D.C.C. § 12.1-32-01" | python3 nd_cite_check.py

Output: JSON array of citation records with local paths and URLs.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Roman numeral helpers
# ---------------------------------------------------------------------------

_ROMAN_MAP = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
    "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13,
    "XIV": 14, "XV": 15, "XVI": 16,
}


def roman_to_arabic(roman: str) -> int:
    return _ROMAN_MAP.get(roman.upper(), 0)


# ---------------------------------------------------------------------------
# URL builders (ported from cite2url URLBuilder.swift)
# ---------------------------------------------------------------------------

def url_ndcc_section(title, title_dec, chapter, chapter_dec, section, section_dec):
    title_num = int(title) if title.isdigit() else 0
    chapter_num = int(chapter) if chapter.isdigit() else 0
    section_num = int(section) if section.isdigit() else 0
    if not (1 <= title_num <= 99 and 1 <= chapter_num <= 99 and 1 <= section_num <= 999):
        return None

    if title_dec:
        title_file = f"{title}-{title_dec}"
        title_dest = f"{title}p{title_dec}"
    else:
        title_file = f"{title_num:02d}"
        title_dest = title

    if chapter_dec:
        chapter_file = f"{chapter}-{chapter_dec}"
        chapter_dest = f"{chapter}p{chapter_dec}"
    else:
        chapter_file = f"{chapter_num:02d}"
        chapter_dest = chapter

    section_dest = f"{section}p{section_dec}" if section_dec else section

    url = (f"https://ndlegis.gov/cencode/t{title_file}c{chapter_file}"
           f".pdf#nameddest={title_dest}-{chapter_dest}-{section_dest}")

    if "t--" in url or "c--" in url or "pp" in url:
        return None
    return url


def url_ndcc_chapter(title, title_dec, chapter, chapter_dec):
    title_num = int(title) if title.isdigit() else 0
    chapter_num = int(chapter) if chapter.isdigit() else 0
    if not (1 <= title_num <= 99 and 1 <= chapter_num <= 99):
        return None

    title_file = f"{title}-{title_dec}" if title_dec else f"{title_num:02d}"
    chapter_file = f"{chapter}-{chapter_dec}" if chapter_dec else f"{chapter_num:02d}"

    url = f"https://ndlegis.gov/cencode/t{title_file}c{chapter_file}.pdf"
    if "t--" in url or "c--" in url or "pp" in url:
        return None
    return url


def url_nd_constitution(article_roman, section):
    return f"https://ndconst.org/art{article_roman.lower()}/sec{section}/"


def url_nd_court_rule(rule_set, parts):
    return f"https://www.ndcourts.gov/legal-resources/rules/{rule_set}/{'-'.join(parts)}"


def url_nd_local_rule(rule):
    return f"https://www.ndcourts.gov/legal-resources/rules/local/search?rule={rule}"


def url_ndac(p1, p2, p3):
    return f"https://ndlegis.gov/information/acdata/pdf/{p1}-{p2}-{p3}.pdf"


def url_nd_case(year, number):
    return f"https://www.courtlistener.com/c/nd/{year}/{number}"


# ---------------------------------------------------------------------------
# Local resolver
# ---------------------------------------------------------------------------

def resolve_local(cite_type, parts, refs_dir):
    """Return (local_path, local_exists) for a citation."""
    refs = Path(refs_dir).expanduser()

    if cite_type == "nd_case":
        year, number = parts["year"], parts["number"]
        p = refs / "opin" / "markdown" / year / f"{year}ND{number}.md"
        return str(p), p.exists()

    if cite_type == "ndcc":
        title_str = parts.get("title_full", parts["title"])
        chapter_str = parts.get("chapter_full", parts["chapter"])
        p = refs / "ndcc" / f"title-{title_str}" / f"chapter-{title_str}-{chapter_str}.md"
        return str(p), p.exists()

    if cite_type == "ndcc_chapter":
        title_str = parts.get("title_full", parts["title"])
        chapter_str = parts.get("chapter_full", parts["chapter"])
        p = refs / "ndcc" / f"title-{title_str}" / f"chapter-{title_str}-{chapter_str}.md"
        return str(p), p.exists()

    if cite_type == "nd_const":
        article_roman = parts["article"]
        article_num = roman_to_arabic(article_roman)
        section = parts["section"]
        p = refs / "cnst" / f"art-{article_num:02d}" / f"sec-{section}.md"
        return str(p), p.exists()

    if cite_type == "ndac":
        p1 = parts["p1"]
        p2 = parts["p2"]
        p3 = parts["p3"]
        # NDAC structure: title-{p1}/article-{p1}-{p2}/chapter-{p1}-{p2}-{p3}.md
        p = refs / "ndac" / f"title-{p1}" / f"article-{p1}-{p2}" / f"chapter-{p1}-{p2}-{p3}.md"
        if p.exists():
            return str(p), True
        # Fallback: flat article file
        p2_flat = refs / "ndac" / f"title-{p1}" / f"article-{p1}-{p2}.md"
        if p2_flat.exists():
            return str(p2_flat), True
        return str(p), False

    # Court rules — no local copy
    return None, False


# ---------------------------------------------------------------------------
# Citation matchers
# ---------------------------------------------------------------------------

def match_nd_case(text):
    """Match '2024 ND 42' style ND Supreme Court citations."""
    m = re.search(r'([12]\d{3})\s+ND\s+(\d{1,3})', text)
    if not m:
        return None
    year, number = m.group(1), m.group(2)
    return {
        "cite_text": m.group(0),
        "cite_type": "nd_case",
        "normalized": f"{year} ND {number}",
        "parts": {"year": year, "number": number},
        "url": url_nd_case(year, number),
        "search_hint": f"{year}ND{number}",
    }


def match_ndcc(text):
    """Match NDCC section citations like 'N.D.C.C. § 12.1-32-01'."""
    pattern = (
        r'(?:(?:N[\s.]*D[\s.]*C(?:ent)*[.\s]*C(?:ode)*[,.\s]{0,3}'
        r'(?:[^\s\d]{0,3}|[Ss]ection|[Ss]ec)\s{0,4})'
        r'|(?:(?:[Ss]ection|[Ss]ec\.?)\s+))'
        r'(\d{1,2})(?:\.(\d+))?'
        r'[^.\w]{1,2}(\d{1,2})(?:\.(\d+))?'
        r'[^.\w](\d{1,2})(?:\.(\d+))?'
        r'(?:\([^)]+\))?'
        r'(?:[,\s]*(?:of\s+the\s+)?'
        r'(?:North\s+Dakota\s+Century\s+Code|N[\s.]*D[\s.]*C(?:ent)*[.\s]*C(?:ode)*)|\W|$)'
    )
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None

    title = m.group(1)
    title_dec = m.group(2) or None
    chapter = m.group(3)
    chapter_dec = m.group(4) or None
    section = m.group(5)
    section_dec = m.group(6) or None

    title_full = f"{title}.{title_dec}" if title_dec else title
    chapter_full = f"{chapter}.{chapter_dec}" if chapter_dec else chapter
    section_full = f"{section}.{section_dec}" if section_dec else section

    url = url_ndcc_section(title, title_dec, chapter, chapter_dec, section, section_dec)
    if not url:
        return None

    normalized = f"N.D.C.C. \u00a7 {title_full}-{chapter_full}-{section_full}"
    return {
        "cite_text": m.group(0).strip(),
        "cite_type": "ndcc",
        "normalized": normalized,
        "parts": {
            "title": title, "title_dec": title_dec, "title_full": title_full,
            "chapter": chapter, "chapter_dec": chapter_dec, "chapter_full": chapter_full,
            "section": section, "section_dec": section_dec, "section_full": section_full,
        },
        "url": url,
        "search_hint": f"{title_full}-{chapter_full}-{section_full}",
    }


def match_ndcc_chapter(text):
    """Match NDCC chapter citations like 'N.D.C.C. ch. 32-12'."""
    pattern = (
        r'(?:(?:N[\s.]*D[\s.]*C(?:ent)*[.\s]*C(?:ode)*[,.\s]{0,3}'
        r'(?:ch\.|ch|chapter)\s+)'
        r'|(?:(?<!C\.\s)(?:[Cc]hapter|[Cc]h\.?)\s+))'
        r'(\d{1,2})(?:\.(\d+))?'
        r'[^.\w]{1,2}(\d{1,2})(?:\.(\d+))?'
    )
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None

    title = m.group(1)
    title_dec = m.group(2) or None
    chapter = m.group(3)
    chapter_dec = m.group(4) or None

    title_full = f"{title}.{title_dec}" if title_dec else title
    chapter_full = f"{chapter}.{chapter_dec}" if chapter_dec else chapter

    url = url_ndcc_chapter(title, title_dec, chapter, chapter_dec)
    if not url:
        return None

    normalized = f"N.D.C.C. ch. {title_full}-{chapter_full}"
    return {
        "cite_text": m.group(0).strip(),
        "cite_type": "ndcc_chapter",
        "normalized": normalized,
        "parts": {
            "title": title, "title_dec": title_dec, "title_full": title_full,
            "chapter": chapter, "chapter_dec": chapter_dec, "chapter_full": chapter_full,
        },
        "url": url,
        "search_hint": f"{title_full}-{chapter_full}",
    }


def match_nd_constitution(text):
    """Match ND Constitution citations."""
    # Pattern 1: "Article VI, section 2 of the N.D. Constitution"
    m = re.search(
        r'(?:Article|Art\.?)\s+([IVX]+)[,\s]+(?:section|sec\.?)\s+(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)\s+of\s+the\s+'
        r'N(?:orth)?\s*D(?:akota)?\s*Const(?:itution)?',
        text, re.IGNORECASE
    )
    if m:
        article, section = m.group(1).upper(), m.group(2)
        return _nd_const_result(m.group(0), article, section)

    # Pattern 2: "N.D. Const. art. I, § 20"
    m = re.search(
        r'N(?:orth)?[\s.]*D(?:akota)?[\s.]*Const(?:itution)?[.\s]*'
        r'(?:art\.|[Aa]rticle)\s*([IVX]+)[,\s]*(?:\u00a7|§|[Ss]ec(?:tion)?\.?)\s*(\d+)',
        text, re.IGNORECASE
    )
    if m:
        article, section = m.group(1).upper(), m.group(2)
        return _nd_const_result(m.group(0), article, section)

    return None


def _nd_const_result(cite_text, article, section):
    return {
        "cite_text": cite_text.strip(),
        "cite_type": "nd_const",
        "normalized": f"N.D. Const. art. {article}, \u00a7 {section}",
        "parts": {"article": article, "section": section},
        "url": url_nd_constitution(article, section),
        "search_hint": f"art {article} sec {section}",
    }


# --- Court Rules ---

_RULE_TYPES = {
    "civil": "civ", "civ": "civ",
    "criminal": "crim", "crim": "crim",
    "appellate": "app", "app": "app",
    "juvenile": "juv", "juv": "juv",
}


def match_nd_court_rules(text):
    """Match all ND court rule patterns."""
    # Order matters — try more specific patterns first

    # N.D.R.Ct. 3-part decimal
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})\.(\d{1,2})\.(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*N[\s.]*D[\s.]*R[\s.]*Ct[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Ct[.\s]*(?:Rule\s+)?(\d{1,2})\.(\d{1,2})\.(\d{1,2})',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(4)
        p2 = m.group(2) or m.group(5)
        p3 = m.group(3) or m.group(6)
        if p1:
            return _court_rule_result(m.group(0), "ndrct",
                                      [p1, p2, p3], f"N.D.R.Ct. {p1}.{p2}.{p3}")

    # N.D.R.Ct. 2-part decimal
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})\.(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*N[\s.]*D[\s.]*R[\s.]*Ct[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Ct[.\s]*(?:Rule\s+)?(\d{1,2})\.(\d{1,2})',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        p2 = m.group(2) or m.group(4)
        if p1:
            return _court_rule_result(m.group(0), "ndrct",
                                      [p1, p2], f"N.D.R.Ct. {p1}.{p2}")

    # N.D. Sup. Ct. Admin. R. decimal
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})\.(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*'
        r'N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[\s.]*'
        r'|N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[.\s]*'
        r'(?:Rule\s+)?(\d{1,2})\.(\d{1,2})',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        p2 = m.group(2) or m.group(4)
        if p1:
            return _court_rule_result(m.group(0), "ndsupctadminr",
                                      [p1, p2], f"N.D. Sup. Ct. Admin. R. {p1}.{p2}")

    # N.D. Sup. Ct. Admin. R. simple
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*'
        r'N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[\s.]*'
        r'|N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[.\s]*'
        r'(?:Rule\s+)?(\d{1,2})(?:(?:\([a-z\d]*\))*|[^.\d])',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndsupctadminr",
                                      [r], f"N.D. Sup. Ct. Admin. R. {r}")

    # N.D.R.Ev. (Evidence)
    m = re.search(
        r'(?:Rule\s+)?(\d{3,4})'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Ev(?:id|idence)?[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Ev(?:id|idence)?[.\s]*'
        r'(?:Rule\s+)?(\d{3,4})',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrev",
                                      [r], f"N.D.R.Ev. {r}")

    # N.D.R. Prof. Conduct
    m = re.search(
        r'(?:Rule\s+)?(\d)\.(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Prof(?:essional)?[\s.]*Conduct[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Prof(?:essional)?[\s.]*Conduct[.\s]*'
        r'(?:Rule\s+)?(\d)\.(\d+)',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        p2 = m.group(2) or m.group(4)
        if p1:
            return _court_rule_result(m.group(0), "ndrprofconduct",
                                      [p1, p2], f"N.D.R. Prof. Conduct {p1}.{p2}")

    # N.D.R. Lawyer Discipline
    m = re.search(
        r'(?:Rule\s+)?(\d)\.(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Lawyer[\s.]*Discipl(?:ine)?[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Lawyer[\s.]*Discipl(?:ine)?[.\s]*'
        r'(?:Rule\s+)?(\d)\.(\d+)',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        p2 = m.group(2) or m.group(4)
        if p1:
            return _court_rule_result(m.group(0), "ndrlawyerdiscipl",
                                      [p1, p2], f"N.D.R. Lawyer Discipl. {p1}.{p2}")

    # N.D. Code Jud. Conduct — Canon:Rule format
    m = re.search(
        r'Canon\s+(\d)\s*:\s*Rule\s+(\d)\.(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*Code[\s.]*Jud(?:icial)?[\s.]*Conduct[\s.]*'
        r'|N[\s.]*D[\s.]*Code[\s.]*Jud(?:icial)?[\s.]*Conduct[.\s]*'
        r'Canon\s+(\d)\s*:\s*Rule\s+(\d)\.(\d+)',
        text, re.IGNORECASE
    )
    if m:
        canon = m.group(1) or m.group(4)
        if canon:
            return _court_rule_result(m.group(0), "ndcodejudconduct",
                                      [f"canon-{canon}"],
                                      f"N.D. Code Jud. Conduct Canon {canon}")

    # N.D. Code Jud. Conduct — Rule-only format
    m = re.search(
        r'(?:Rule\s+)?(\d)\.(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*Code[\s.]*Jud(?:icial)?[\s.]*Conduct[\s.]*'
        r'|N[\s.]*D[\s.]*Code[\s.]*Jud(?:icial)?[\s.]*Conduct[.\s]*'
        r'(?:Rule\s+)?(\d)\.(\d+)',
        text, re.IGNORECASE
    )
    if m:
        canon = m.group(1) or m.group(3)
        if canon:
            return _court_rule_result(m.group(0), "ndcodejudconduct",
                                      [f"canon-{canon}"],
                                      f"N.D. Code Jud. Conduct Canon {canon}")

    # Juvenile Procedure — decimal
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})\.(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'(?:North\s+Dakota\s+Rules\s+of\s+Juvenile\s+Procedure'
        r'|N[\s.]*D[\s.]*R[\s.]*Juv(?:enile)?[\s.]*P(?:rocedure)?[\s.]*)'
        r'|(?:North\s+Dakota\s+Rules\s+of\s+Juvenile\s+Procedure'
        r'|N[\s.]*D[\s.]*R[\s.]*Juv(?:enile)?[\s.]*P(?:rocedure)?[.\s]*)'
        r'(?:Rule\s+)?(\d{1,2})\.(\d+)',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        p2 = m.group(2) or m.group(4)
        if p1:
            return _court_rule_result(m.group(0), "ndrjuvp",
                                      [p1, p2], f"N.D.R. Juv. P. {p1}.{p2}")

    # Procedural rules — simple numbering (Civil, Criminal, Appellate, Juvenile)
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*'
        r'(?:North\s+Dakota\s+Rules\s+of\s+(Civil|Criminal|Appellate|Juvenile)\s+Procedure'
        r'|N[\s.]*D[\s.]*R[\s.]*(Civ|Crim|App|Juv)(?:il|inal|ellate|enile)?[\s.]*P(?:rocedure)?[\s.]*)'
        r'|(?:North\s+Dakota\s+Rules\s+of\s+(Civil|Criminal|Appellate|Juvenile)\s+Procedure'
        r'|N[\s.]*D[\s.]*R[\s.]*(Civ|Crim|App|Juv)(?:il|inal|ellate|enile)?[\s.]*P(?:rocedure)?[.\s]*)'
        r'(?:Rule\s+)?(\d{1,2})(?:(?:\([a-z\d]*\))*|[^.\d])',
        text, re.IGNORECASE
    )
    if m:
        rule_num = m.group(1) or m.group(6)
        raw_type = next((g for g in [m.group(2), m.group(3), m.group(4), m.group(5)] if g), None)
        if rule_num and raw_type:
            rt = _RULE_TYPES.get(raw_type.lower(), raw_type.lower())
            return _court_rule_result(m.group(0), f"ndr{rt}p",
                                      [rule_num], f"N.D.R.{rt.capitalize()}.P. {rule_num}")

    # N.D.R.App.P. — explicit abbreviation (catch common form not handled above)
    m = re.search(
        r'N[\s.]*D[\s.]*R[\s.]*App[\s.]*P[.\s]*(?:Rule\s+)?(\d{1,2})'
        r'|(?:Rule\s+)?(\d{1,2})[,\s]*N[\s.]*D[\s.]*R[\s.]*App[\s.]*P[\s.]*',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrapp p",
                                      [r], f"N.D.R.App.P. {r}")

    # N.D.R.Civ.P. — explicit abbreviation
    m = re.search(
        r'N[\s.]*D[\s.]*R[\s.]*Civ[\s.]*P[.\s]*(?:Rule\s+)?(\d{1,2})'
        r'|(?:Rule\s+)?(\d{1,2})[,\s]*N[\s.]*D[\s.]*R[\s.]*Civ[\s.]*P[\s.]*',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrcivp",
                                      [r], f"N.D.R.Civ.P. {r}")

    # N.D.R.Crim.P. — explicit abbreviation
    m = re.search(
        r'N[\s.]*D[\s.]*R[\s.]*Crim[\s.]*P[.\s]*(?:Rule\s+)?(\d{1,2})'
        r'|(?:Rule\s+)?(\d{1,2})[,\s]*N[\s.]*D[\s.]*R[\s.]*Crim[\s.]*P[\s.]*',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrcrimp",
                                      [r], f"N.D.R.Crim.P. {r}")

    # N.D.R.Ct. simple (no decimal)
    m = re.search(
        r'N[\s.]*D[\s.]*R[\s.]*Ct[.\s]*(?:Rule\s+)?(\d{1,2})(?:(?:\([a-z\d]*\))*|[^.\d])'
        r'|(?:Rule\s+)?(\d{1,2})(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*N[\s.]*D[\s.]*R[\s.]*Ct[\s.]*',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrct",
                                      [r], f"N.D.R.Ct. {r}")

    # N.D.R. Continuing Legal Ed.
    m = re.search(
        r'(?:Rule\s+)?(\d)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Continuing[\s.]*Legal[\s.]*Ed(?:ucation)?[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Continuing[\s.]*Legal[\s.]*Ed(?:ucation)?[.\s]*'
        r'(?:Rule\s+)?(\d)',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrcontinuinglegaled",
                                      [r], f"N.D.R. Continuing Legal Ed. {r}")

    # Admission to Practice — decimal
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})\.(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*Admission[\s.]*to[\s.]*Practice[\s.]*R(?:ules)?[\s.]*'
        r'|N[\s.]*D[\s.]*Admission[\s.]*to[\s.]*Practice[\s.]*R(?:ules)?[.\s]*'
        r'(?:Rule\s+)?(\d{1,2})\.(\d+)',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        p2 = m.group(2) or m.group(4)
        if p1:
            return _court_rule_result(m.group(0), "admissiontopracticer",
                                      [p1, p2],
                                      f"N.D. Admission to Practice R. {p1}.{p2}")

    # Admission to Practice — simple
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*'
        r'N[\s.]*D[\s.]*Admission[\s.]*to[\s.]*Practice[\s.]*R(?:ules)?[\s.]*'
        r'|N[\s.]*D[\s.]*Admission[\s.]*to[\s.]*Practice[\s.]*R(?:ules)?[.\s]*'
        r'(?:Rule\s+)?(\d{1,2})(?:(?:\([a-z\d]*\))*|[^.\d])',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "admissiontopracticer",
                                      [r], f"N.D. Admission to Practice R. {r}")

    # Lawyer Sanctions Standards
    m = re.search(
        r'(?:Standard\s+)?(\d)\.(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*Stds[\s.]*Imposing[\s.]*Lawyer[\s.]*Sanctions[\s.]*'
        r'|N[\s.]*D[\s.]*Stds[\s.]*Imposing[\s.]*Lawyer[\s.]*Sanctions[.\s]*'
        r'(?:Standard\s+)?(\d)\.(\d{1,2})',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        if p1:
            return _court_rule_result(m.group(0), "ndstdsimposinglawyersanctions",
                                      [p1, "0"],
                                      f"N.D. Stds. Imposing Lawyer Sanctions {p1}")

    # Local Rules
    m = re.search(r'Local[\s.]*Rule[\s.]*(\d{1,4}(?:-\d+)?)', text, re.IGNORECASE)
    if m:
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "nd_court_rule",
            "normalized": f"Local Rule {m.group(1)}",
            "parts": {"rule_set": "local", "parts": [m.group(1)]},
            "url": url_nd_local_rule(m.group(1)),
            "search_hint": f"Local Rule {m.group(1)}",
        }

    # N.D.R. Proc. R.
    m = re.search(
        r'(?:Section\s+)?(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Proc[\s.]*R[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Proc[\s.]*R[.\s]*'
        r'(?:Section\s+)?(\d{1,2})',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrprocr",
                                      [r], f"N.D.R. Proc. R. {r}")

    # N.D.R. Local Ct. P.R.
    m = re.search(
        r'(?:Section\s+)?(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Local[\s.]*Ct[\s.]*P[\s.]*R[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Local[\s.]*Ct[\s.]*P[\s.]*R[.\s]*'
        r'(?:Section\s+)?(\d{1,2})',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "ndrlocalctpr",
                                      [r], f"N.D.R. Local Ct. P.R. {r}")

    # Student Practice Rules (Roman numerals)
    m = re.search(
        r'(?:Section\s+)?([IVX]+)'
        r'(?:(?:\([a-z\d]*\))*|\W)[,\s]*'
        r'(?:Limited\s+Practice\s+of\s+Law\s+by\s+Law\s+Students'
        r'|N[\s.]*D[\s.]*Student[\s.]*Practice[\s.]*R[\s.]*)'
        r'|(?:Limited\s+Practice\s+of\s+Law\s+by\s+Law\s+Students'
        r'|N[\s.]*D[\s.]*Student[\s.]*Practice[\s.]*R[.\s]*)'
        r'(?:Section\s+)?([IVX]+)',
        text, re.IGNORECASE
    )
    if m:
        roman = m.group(1) or m.group(2)
        if roman:
            return _court_rule_result(m.group(0), "rltdpracticeoflawbylawstudents",
                                      [roman.upper()],
                                      f"N.D. Student Practice R. \u00a7 {roman.upper()}")

    # Judicial Conduct Commission — decimal
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})\.(\d+)'
        r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Jud[\s.]*Conduct[\s.]*Commission[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Jud[\s.]*Conduct[\s.]*Commission[.\s]*'
        r'(?:Rule\s+)?(\d{1,2})\.(\d+)',
        text, re.IGNORECASE
    )
    if m:
        p1 = m.group(1) or m.group(3)
        p2 = m.group(2) or m.group(4)
        if p1:
            return _court_rule_result(m.group(0), "rjudconductcomm",
                                      [p1, p2],
                                      f"N.D.R. Jud. Conduct Commission {p1}.{p2}")

    # Judicial Conduct Commission — simple
    m = re.search(
        r'(?:Rule\s+)?(\d{1,2})'
        r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*'
        r'N[\s.]*D[\s.]*R[\s.]*Jud[\s.]*Conduct[\s.]*Commission[\s.]*'
        r'|N[\s.]*D[\s.]*R[\s.]*Jud[\s.]*Conduct[\s.]*Commission[.\s]*'
        r'(?:Rule\s+)?(\d{1,2})(?:(?:\([a-z\d]*\))*|[^.\d])',
        text, re.IGNORECASE
    )
    if m:
        r = m.group(1) or m.group(2)
        if r:
            return _court_rule_result(m.group(0), "rjudconductcomm",
                                      [r],
                                      f"N.D.R. Jud. Conduct Commission {r}")

    return None


def _court_rule_result(cite_text, rule_set, parts, description):
    # Fix rule_set with space (typo from "ndrapp p")
    rule_set_clean = rule_set.replace(" ", "")
    return {
        "cite_text": cite_text.strip(),
        "cite_type": "nd_court_rule",
        "normalized": description,
        "parts": {"rule_set": rule_set_clean, "parts": parts},
        "url": url_nd_court_rule(rule_set_clean, parts),
        "search_hint": description,
    }


def match_ndac(text):
    """Match NDAC citations."""
    # "N.D.A.C. § 43-02-05-01" (4-part section)
    m = re.search(
        r'N[\s.]*D[\s.]*A(?:dmin)*[.\s]*(?:Code|C|Rules|R)*[,.\s]*[^\s\d]{0,3}\s*'
        r'(\d{1,2}\.?\d*)[^.\w]{1,2}(\d{2}\.?\d*)[^.\w]{1,2}'
        r'(\d{2}\.?\d*)[^.\w]{1,2}(\d{2}\.?\d*)',
        text, re.IGNORECASE
    )
    if m:
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "ndac",
            "normalized": f"N.D.A.C. \u00a7 {m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}",
            "parts": {"p1": m.group(1), "p2": m.group(2), "p3": m.group(3), "p4": m.group(4)},
            "url": url_ndac(m.group(1), m.group(2), m.group(3)),
            "search_hint": f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}",
        }

    # "N.D.A.C. ch. 43-02-05" (3-part chapter)
    m = re.search(
        r'N[\s.]*D[\s.]*A(?:dmin)*[.\s]*(?:Code|C|Rules|R)*[,.\s]{0,2}'
        r'(?:Ch\.|ch\.|Ch|ch)\s*'
        r'(\d{1,2}\.?\d*)[^.\w]{1,2}(\d{2}\.?\d*)[^.\w]{1,2}(\d{2}\.?\d*)',
        text, re.IGNORECASE
    )
    if m:
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "ndac",
            "normalized": f"N.D.A.C. ch. {m.group(1)}-{m.group(2)}-{m.group(3)}",
            "parts": {"p1": m.group(1), "p2": m.group(2), "p3": m.group(3)},
            "url": url_ndac(m.group(1), m.group(2), m.group(3)),
            "search_hint": f"{m.group(1)}-{m.group(2)}-{m.group(3)}",
        }

    # Reverse: "43-02-05-01, N.D. Admin Code"
    m = re.search(
        r'(\d{2}\.?\d*)[^.\w]{1,2}(\d{2}\.?\d*)[^.\w]{1,2}'
        r'(\d{2}\.?\d*)[^.\w]{1,2}(\d{2}\.?\d*)'
        r'(?:(?:\([a-z\d]*\))*|\D)(?:,\s{0,3})'
        r'N[\s.]*D[\s.]*A(?:dmin)*[.\s]*(?:Code|C|Rules|R)*',
        text, re.IGNORECASE
    )
    if m:
        return {
            "cite_text": m.group(0).strip(),
            "cite_type": "ndac",
            "normalized": f"N.D.A.C. \u00a7 {m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}",
            "parts": {"p1": m.group(1), "p2": m.group(2), "p3": m.group(3), "p4": m.group(4)},
            "url": url_ndac(m.group(1), m.group(2), m.group(3)),
            "search_hint": f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}",
        }

    return None


# ---------------------------------------------------------------------------
# Scanner — find all ND citations in opinion text
# ---------------------------------------------------------------------------

# Matchers in priority order (ND-specific only)
_MATCHERS = [
    match_nd_constitution,
    match_ndcc,
    match_ndcc_chapter,
    match_nd_court_rules,
    match_ndac,
    match_nd_case,
]


def scan_opinion(text, refs_dir="~/refs"):
    """Scan opinion text for all ND citations. Returns deduplicated list."""
    results = []
    seen = set()

    for matcher in _MATCHERS:
        # Re-scan full text for each matcher to catch all occurrences
        # We use a sliding window to find multiple matches
        pos = 0
        while pos < len(text):
            chunk = text[pos:]
            result = matcher(chunk)
            if not result:
                break

            normalized = result["normalized"]
            if normalized not in seen:
                seen.add(normalized)

                # Resolve local path
                cite_type = result["cite_type"]
                parts = result.get("parts", {})
                local_path, local_exists = resolve_local(cite_type, parts, refs_dir)

                entry = {
                    "cite_text": result["cite_text"],
                    "cite_type": cite_type,
                    "normalized": normalized,
                    "url": result["url"],
                    "search_hint": result["search_hint"],
                }
                if local_path:
                    entry["local_path"] = local_path
                    entry["local_exists"] = local_exists
                else:
                    entry["local_path"] = None
                    entry["local_exists"] = False

                results.append(entry)

            # Advance past this match
            match_start = chunk.find(result["cite_text"])
            if match_start >= 0:
                pos += match_start + len(result["cite_text"])
            else:
                pos += 1

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Parse ND legal citations, resolve local files, build URLs."
    )
    parser.add_argument("--file", "-f", help="Scan a file for all ND citations")
    parser.add_argument("--refs-dir", default="~/refs",
                        help="Override refs directory (default: ~/refs)")
    parser.add_argument("--json", action="store_true", default=True,
                        help="Output as JSON (default)")
    args = parser.parse_args()

    if args.file:
        path = Path(args.file).expanduser()
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        text = path.read_text(encoding="utf-8")
        results = scan_opinion(text, refs_dir=args.refs_dir)
    else:
        # stdin mode — one citation per line
        results = []
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            found = scan_opinion(line, refs_dir=args.refs_dir)
            results.extend(found)

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
