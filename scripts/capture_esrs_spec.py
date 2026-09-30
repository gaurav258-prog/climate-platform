"""Split an ESRS topical standard, as printed in the Official Journal, into its items — machine-exact quotes.

Input: the act's HTML as downloaded from the EU Cellar (the OJ text of Delegated Regulation (EU) 2026/1563, or the
consolidated text of 2023/2772 as amended by 2025/1416); extract() cuts one standard from its title to the next
standard's title, removes footnote blocks and EUR-Lex editorial markers. Output: every Disclosure Requirement (heading) and, in reading order,
its numbered paragraphs, lettered points and roman sub-points, each with the exact printed words, and every
Application Requirement (AR) with the paragraph it is for.

Numbering is structural, so it is read strictly in sequence: a paragraph marker is accepted only when it is the next
paragraph number (1., 2., …), a point only as the next letter within its paragraph, a sub-point only as the next roman
numeral within its point, an AR only as the next AR number. '1,5 °C', 'Chapter 3.3.2' or '(e.g.' can therefore never
open an item. Every quote is a slice of the input, so it is exact by construction; check() proves it again.

    venv/bin/python -m scripts.capture_esrs_spec <act.html> <E1|E3|E4> <2023|2026> > items.json
"""
from __future__ import annotations

import json
import re
import sys

ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv"]
LETTERS = "abcdefghijklmnopqrstuvwxyz"


MARKERS = re.compile(r"\s*[►▼][A-Z]\d*\s*|\s*◄\s*")


def clean(text: str) -> str:
    """The consolidated text (a documentation tool) marks amended and corrected passages with ►M1 / ►C1 … ◄. They are
    EUR-Lex's editorial markers, not words of the act: removed, whitespace collapsed."""
    return re.sub(r"\s+", " ", MARKERS.sub(" ", text)).strip()


# Where each standard starts and ends in each act, as printed (the consolidated 2023 text spells E5 'RESOUCE').
SECTIONS = {
    "2023": {"E1": (r" ESRS E1 CLIMATE CHANGE TABLE OF CONTENTS", r" ESRS E2 POLLUTION TABLE OF CONTENTS"),
             "E3": (r" ESRS E3 WATER AND MARINE RESOURCES TABLE OF CONTENTS", r" ESRS E4 BIODIVERSITY AND ECOSYSTEMS TABLE OF CONTENTS"),
             "E4": (r" ESRS E4 BIODIVERSITY AND ECOSYSTEMS TABLE OF CONTENTS", r" ESRS E5 RESOU?R?CE USE AND CIRCULAR ECONOMY TABLE OF CONTENTS")},
    "2026": {"E1": (r"ESRS E1 – CLIMATE CHANGE TABLE OF CONTENTS", r"ESRS E2 – POLLUTION TABLE OF CONTENTS"),
             "E3": (r"ESRS E3 – WATER[A-Z ]* TABLE OF CONTENTS", r"ESRS E4 – BIODIVERSITY[A-Z ]* TABLE OF CONTENTS"),
             "E4": (r"ESRS E4 – BIODIVERSITY[A-Z ]* TABLE OF CONTENTS", r"ESRS E5 – RESOURCE[A-Z ]* TABLE OF CONTENTS")},
}
# footnote text blocks (the inline marker stays): the OJ's <p class="oj-note">, the consolidated text's <p class="footnote">
_TITLES = re.compile(r'<p\b[^>]*\bclass="(?:title-gr-seq-level-\d|oj-ti-grseq-\d)"[^>]*>(.*?)</p>', re.S)
_FOOTNOTES = re.compile(r'<p\b[^>]*\bclass="(?:oj-note|footnote)"[^>]*>.*?</p>|<hr\b[^>]*\bclass="[^"]*"[^>]*/?>', re.S)


def extract(html: str, version: str, std: str) -> str:
    """One standard's printed text from the act's HTML: footnote blocks removed, tags stripped, entities decoded,
    editorial markers removed, whitespace collapsed."""
    import html as _html
    t = _FOOTNOTES.sub(" ", html)
    # printed titles (section / sub-section headings) are their own elements: mark them ⟦ … ⟧ so the split can tell a
    # title from the text of an item (after a table printed as text, words alone cannot)
    t = _TITLES.sub(lambda m: " ⟦ " + m.group(1) + " ⟧ ", t)
    t = _html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = clean(t)
    start, end = SECTIONS[version][std]
    flat = re.sub(r"[⟦⟧]", " ", t)                       # same length: positions in flat are positions in t
    loose = lambda pat: re.compile(pat.strip().replace(" ", r"[\s]+"))     # noqa: E731 — titles may be marked
    a = [m.start() for m in loose(start).finditer(flat)]
    if len(a) != 1:
        raise SystemExit(f"{std} {version}: start found {len(a)} times")
    b = loose(end).search(flat, a[0])
    if not b:
        raise SystemExit(f"{std} {version}: end not found")
    seg = t[a[0]:b.start()].strip()
    return re.sub(r"^\s*⟧|⟦\s*$", "", seg).strip()      # the marks of the titles the cut runs through


def _body(text: str) -> str:
    """Skip the table of contents: the body opens at its 'Objective' title, followed by paragraph 1."""
    m = re.search(r"(?:⟦\s*)?Objective(?:\s*⟧)?\s+1\. ", text)
    if not m:
        raise SystemExit("no 'Objective 1.' — is this a whole standard?")
    return text[m.start():]


def _headings(body: str, std: str, para_at: list[int]) -> list[tuple[int, int, str, str]]:
    """(start, end, id, title) of every Disclosure Requirement heading — its own and the 'related to ESRS 2' ones. A
    candidate is a heading only when the next paragraph marker follows it within a heading's length (a mention of a
    Disclosure Requirement inside a sentence is not followed by a new paragraph)."""
    out = []
    # the OJ prints the ESRS 2 related headings in several ways: 'related to ESRS 2 IRO-1', 'SBM 3' (E4, 2023)
    pat = re.compile(r"Disclosure [Rr]equirements? (?:(" + std + r"-\d+)|(?:related to )?(?:ESRS 2 )?(GOV|SBM|IRO)[- ](\d))")
    for m in pat.finditer(body):
        # a printed heading has a dash straight after its code ('E1-9 – Anticipated …', 'SBM 3 – …') or reads
        # 'related to ESRS 2 IRO-1 Description …'; a mention inside a sentence never does ('E1-6 paragraph 51', 'E1-4);')
        dashed = re.match(r"\s*[–-]\s", body[m.end():])
        related = m.group(2) and "related to" in m.group(0) and re.match(r"\s*[A-Z]", body[m.end():])
        if not (dashed or related):
            continue
        nxt = next((p for p in para_at if p > m.start()), None)
        if nxt is None or nxt - m.start() > 400:
            continue
        title = body[m.start():nxt].strip()
        if re.search(r"\.\s", title):
            continue
        hid = m.group(1) or f"ESRS2-{m.group(2)}-{m.group(3)}"
        out.append((m.start(), nxt, hid, title))
    return out


def split(text: str, std: str) -> dict:
    body = _body(clean(text))
    # a printed title naming a Disclosure Requirement is its heading: unwrapped (same length, so positions hold);
    # every other printed title ends the item before it and is recorded, never kept in an item
    spans = []
    for m in re.finditer(r"⟦(.*?)⟧", body):
        if re.search(r"Disclosure [Rr]equirements? (?:" + std + r"-\d|(?:related to )?(?:ESRS 2 )?(?:GOV|SBM|IRO)[- ]\d)", m.group(1)):
            body = body[:m.start()] + " " + m.group(1) + " " + body[m.end():]
        else:
            spans.append((m.start(), m.end(), m.group(1).strip()))
    ar_at = None
    m = re.search(r"Appendix A:? ?Application Requirements", body)       # 2023: ARs in an appendix
    if m:
        ar_at = m.start()
    main = body if ar_at is None else body[:ar_at]

    # paragraph markers in strict sequence
    paras: list[tuple[int, int]] = []           # (number, position of the marker)
    n, pos = 1, 0
    while True:
        m = re.compile(rf"(?:(?<=\s)|^){n}\. (?=[A-Z(‘'])").search(main, pos)
        if not m:
            break
        paras.append((n, m.start()))
        pos, n = m.end(), n + 1
    # AR markers in strict sequence (2026: inline after each DR; 2023: in the appendix)
    ars: list[tuple[int, int, str]] = []
    src_ar = body if ar_at is None else body[ar_at:]
    base = 0 if ar_at is None else ar_at
    k, pos = 1, 0
    while True:
        m = re.compile(rf"(?:(?<=\s)|^)AR {k}(?:\.| for )").search(src_ar, pos)
        if not m:
            break
        ars.append((k, base + m.start(), ""))
        pos, k = m.end(), k + 1

    heads = _headings(main, std, [p for _, p in paras])
    # boundaries: every marker (paragraph, AR, heading) ends the item before it
    cuts = sorted({p for _, p in paras} | {p for _, p, _ in ars} | {h[0] for h in heads} | ({ar_at} if ar_at else set())
                  | {a for a, _, _ in spans} | {len(body)})

    def upto(start: int) -> int:
        return next(c for c in cuts if c > start)

    items, current_dr, last_id = [], None, {}
    heads_at = {h[0]: h for h in heads}
    order = sorted([(p, "para", num) for num, p in paras] + [(h[0], "head", h) for h in heads])
    for p, what, x in order:
        if what == "head":
            _, end, hid, title = x
            current_dr = hid
            items.append({"id": hid, "kind": "heading", "label": title, "parent": None})
            continue
        if p in heads_at:
            continue
        raw = body[p:upto(p)].strip()
        pid = f"{current_dr or std}.{x}"
        pts = _points(raw, pid, current_dr, x)
        items.extend(pts)
        last_id[p] = pts[-1]["id"]
    instructions = []
    # 2023: the appendix groups ARs under Disclosure Requirement headings; an AR is for the heading it stands under
    ar_heads = [] if ar_at is None else [(h[0] + ar_at, h[2]) for h in _headings(body[ar_at:], std, [p - ar_at for _, p, _ in ars])]
    ar_cuts = sorted(set(cuts) | {h for h, _ in ar_heads})
    for num, p, _ in ars:
        raw = body[p:next(c for c in ar_cuts if c > p)].strip()
        last_id[p] = f"AR {num}"
        fm = re.match(rf"AR {num} for paras?\.? ?([\d(),a-z\s–-]+?)(?: \(|$| [A-Z])", raw)
        # 2023: the appendix heading it stands under; 2026: ARs follow their Disclosure Requirement inline
        under = (next((hid for h, hid in reversed(ar_heads) if h < p), None) if ar_at is not None
                 else next((h[2] for h in reversed(heads) if h[0] < p), None))
        instructions.append({"ref": f"AR {num}", "for": (fm.group(1).strip() if fm else None), "under": under,
                             "quote": raw})
    titles = []
    all_cuts = sorted(set(cuts) | {h for h, _ in ar_heads})
    for a, e, title in spans:
        nxt = next((c for c in all_cuts if c > a), len(body))
        rest = re.sub(r"⟦.*?⟧", " ", body[e:nxt]).strip()
        if rest:
            raise SystemExit(f"printed title '{title}' is followed by text no item holds: '{rest[:80]}'")
        before = max((p for p in last_id if p < a), default=None)
        titles.append({"after": last_id.get(before), "title": title})
    return {"standard": std, "items": items, "instructions": instructions, "printed_titles_removed": titles}


def _points(raw: str, pid: str, dr: str | None, num: int) -> list[dict]:
    """A paragraph and its lettered points (a), (b)… and roman sub-points i., ii.… — each in strict sequence."""
    marks = []
    li, pos = 0, 0
    while li < len(LETTERS):
        # '(a)' straight after a number ('paragraph 44 (a)', '30(a)') is a cross-reference, not a point
        m = re.compile(rf"(?<![\d\s]\d)(?<!\d)(?<!\d )\({LETTERS[li]}\) ").search(raw, pos)
        if not m or (li == 0 and not re.search(r"[:;,]\s*$|following|including|\bby\b|\bon\b|\bof\b|\bits\b|\bthe\b",
                                               raw[:m.start()][-60:])):
            break
        marks.append(("pt", LETTERS[li], m.start()))
        pos, li = m.end(), li + 1
    out = [{"id": pid, "kind": "text", "label": raw[:marks[0][2]].strip() if marks else raw, "parent": dr,
            "note": f"§{num}"}]
    for i, (_, letter, start) in enumerate(marks):
        end = marks[i + 1][2] if i + 1 < len(marks) else len(raw)
        seg = raw[start:end].strip()
        subs, ri, rpos = [], 0, 0
        while ri < len(ROMAN):
            m = re.compile(rf"(?:(?<=\s)|^){ROMAN[ri]}\. ").search(seg, rpos)
            if not m:
                break
            subs.append((ROMAN[ri], m.start()))
            rpos, ri = m.end(), ri + 1
        out.append({"id": f"{pid}{letter}", "kind": "text", "label": seg[:subs[0][1]].strip() if subs else seg,
                    "parent": pid, "note": f"§{num}({letter})"})
        for j, (rn, rs) in enumerate(subs):
            re_ = subs[j + 1][1] if j + 1 < len(subs) else len(seg)
            out.append({"id": f"{pid}{letter}.{rn}", "kind": "text", "label": seg[rs:re_].strip(),
                        "parent": f"{pid}{letter}", "note": f"§{num}({letter})({rn})"})
    return out


def check(text: str, captured: dict) -> list[str]:
    """Every quote a verbatim slice of the source (whitespace-normalised); ids unique; parents exist."""
    src = clean(re.sub(r"[⟦⟧]", " ", text))
    errs, ids = [], set()
    for i in captured["items"]:
        if i["id"] in ids:
            errs.append(f"duplicate id {i['id']}")
        ids.add(i["id"])
        if re.sub(r"\s+", " ", i["label"]) not in src:
            errs.append(f"{i['id']}: label is not in the source")
    for i in captured["items"]:
        if i.get("parent") and i["parent"] not in ids:
            errs.append(f"{i['id']}: parent {i['parent']} missing")
    for a in captured["instructions"]:
        if re.sub(r"\s+", " ", a["quote"]) not in src:
            errs.append(f"{a['ref']}: quote is not in the source")
    return errs


if __name__ == "__main__":
    path, std, version = sys.argv[1], sys.argv[2], sys.argv[3]
    t = extract(open(path, encoding="utf-8").read(), version, std)
    out = split(t, std)
    errs = check(t, out)
    if errs:
        raise SystemExit("\n".join(errs[:30]))
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
