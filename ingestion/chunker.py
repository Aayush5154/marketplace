import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import CHUNK_OVERLAP, CHUNK_SIZE

# ------------------------------------------------------------------
# Fallback splitter for non-policy, non-email PDFs
# ------------------------------------------------------------------
basic_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)

# ------------------------------------------------------------------
# Regex helpers (policy PDF)
# ------------------------------------------------------------------
RULE_START = re.compile(r"(?m)^\s*((?:POL|BRD)-\d+\.\d+[a-z]?)\s{1,}(?=\S)")
SECTION_LINE = re.compile(r"(?m)^\s*(\d{1,2})\.\s+([A-Z][^\n]+)$")
PART_LINE = re.compile(r"(?m)^\s*(Part [AB])\.\s+([^\n]+)$")
APPENDIX_LINE = re.compile(r"(?m)^\s*Appendix\.\s+([^\n]+)$")
FOOTER = re.compile(r"(?m)^\s*Northwind Marketplace - Listing Policy.*$")
RULE_ID_ANY = re.compile(r"\b(?:POL|BRD)-\d+\.\d+[a-z]?\b")
# example / check blocks: one title line immediately followed by "Problem:" or "Pass condition:"
BLOCK_SPLIT = re.compile(r"(?m)^(?=[^\n]+\n\s*(?:Problem|Pass condition):)")


def is_policy_doc(text):
    return len(RULE_ID_ANY.findall(text)) >= 10


def _clean(text):
    """Strip footers; join wrapped lines (keep bullet lines separate)."""
    text = text.replace("\x7f", "•")  # pypdf renders bullets as DEL (\x7f)
    text = FOOTER.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n(?!\n)(?=\s*(?:Problem|Suggested rewrite|Rules|Pass condition|Rule):)", "\n", text)
    return text.strip()


def _join_wrapped(text):
    """Join wrapped PDF lines into one paragraph."""
    return re.sub(r"\s*\n\s*", " ", text).strip()


def _doc_type(rule_id=None, part=None):
    if rule_id:
        return "policy" if rule_id.startswith("POL") else "brand_guide"
    return "policy" if part == "Part A" else "brand_guide" if part == "Part B" else "reference"


def split_policy_document(doc):
    """
    Structure-aware (rule-based) chunking:
      - 1 rule (POL-x.y / BRD-x.y) = 1 chunk
      - Section heading + rule ID har chunk ke upar context header me
      - Rewrite examples (Section 15) = 1 example = 1 chunk
      - Appendix checks = 1 check = 1 chunk
    Metadata me rule_id, section_no, section_title, doc_type, related_rules.
    """
    raw = doc.page_content
    # Keep only needed metadata; drop PDF junk (author, producer, dates, ...).
    src = str(doc.metadata.get("source", "policy.pdf")).replace("\\", "/").split("/")[-1]
    base = {"source": src}

    # Cover + contents are skipped: policy starts at the last "Part A. Policy" occurrence.
    starts = [m.start() for m in PART_LINE.finditer(raw) if m.group(1) == "Part A"]
    body = raw[starts[-1]:] if starts else raw
    body = _clean(body)

    # Split body on headings: (position, kind, data)
    events = []
    for m in PART_LINE.finditer(body):
        events.append((m.start(), m.end(), "part", (m.group(1), m.group(2))))
    for m in SECTION_LINE.finditer(body):
        events.append((m.start(), m.end(), "section", (m.group(1), m.group(2).strip())))
    for m in APPENDIX_LINE.finditer(body):
        events.append((m.start(), m.end(), "appendix", ("A", m.group(1).strip())))
    events.sort()

    chunks = []
    part, sec_no, sec_title = "Part A", "", ""

    for i, (s, e, kind, data) in enumerate(events):
        nxt = events[i + 1][0] if i + 1 < len(events) else len(body)
        if kind == "part":
            part = data[0]
            continue
        sec_no, sec_title = data
        if kind == "appendix":
            sec_no = "Appendix"
            part = "Appendix"
        section_text = body[e:nxt].strip()
        if not section_text:
            continue

        header_base = f"{sec_no}. {sec_title}" if sec_no != "Appendix" else f"Appendix. {sec_title}"
        common = {**base, "part": part, "section_no": sec_no, "section_title": sec_title}

        # ---- A) Rule chunks ----
        rule_ms = list(RULE_START.finditer(section_text))
        if rule_ms:
            for j, rm in enumerate(rule_ms):
                end = rule_ms[j + 1].start() if j + 1 < len(rule_ms) else len(section_text)
                rule_id = rm.group(1)
                chunk_body = section_text[rm.end():end].strip()
                # Keep bullets (e.g. category lists) on separate lines, join the rest.
                lines = [l.strip() for l in chunk_body.split("\n") if l.strip()]
                text = _join_wrapped(" ".join(lines)) if not any(l.startswith("•") for l in lines) else "\n".join(lines)
                related = sorted(set(RULE_ID_ANY.findall(text)) - {rule_id})
                content = f"[{header_base} | {rule_id}]\n{rule_id}: {text}"
                chunks.append(Document(
                    page_content=content,
                    metadata={**common, "chunk_type": "rule", "rule_id": rule_id,
                              "doc_type": _doc_type(rule_id), "related_rules": related,
                              "chunk_id": rule_id},
                ))
                # Rules with bullet lists (e.g. POL-4.1 categories): one chunk per bullet.
                for bi, bl in enumerate([l.lstrip("• ").strip() for l in lines if l.startswith("•")]):
                    name = bl.split(" - ")[0].strip()
                    chunks.append(Document(
                        page_content=f"[{header_base} | {rule_id} | {name}]\n{rule_id} category {bl}",
                        metadata={**common, "chunk_type": "category_requirements", "rule_id": rule_id,
                                  "category": name, "doc_type": _doc_type(rule_id),
                                  "chunk_id": f"{rule_id}-cat-{bi + 1}"}))
            # Section intro (text before the first rule), if present.
            intro = section_text[:rule_ms[0].start()].strip()
            if len(intro) > 40:
                chunks.append(Document(
                    page_content=f"[{header_base}]\n{_join_wrapped(intro)}",
                    metadata={**common, "chunk_type": "section_intro", "doc_type": _doc_type(None, part),
                              "chunk_id": f"intro-{sec_no}"},
                ))
            continue

        # ---- B) Example / check blocks (Section 15 + Appendix) ----
        blocks = [b.strip() for b in BLOCK_SPLIT.split(section_text) if b.strip()]
        if len(blocks) > 1:
            n = 0
            leftovers = []
            for b in blocks:
                if not re.search(r"(?m)^\s*(Problem|Pass condition):", b):
                    if len(b) > 40:
                        chunks.append(Document(
                            page_content=f"[{header_base}]\n{_join_wrapped(b)}",
                            metadata={**common, "chunk_type": "section_intro",
                                      "doc_type": _doc_type(None, part), "chunk_id": f"intro-{sec_no}"}))
                    continue
                lines = [l.strip().lstrip("• ").strip() for l in b.split("\n") if l.strip()]
                # Text after the "Rules:" / "Rule:" line belongs to the next item.
                cut = next((k for k, l in enumerate(lines) if re.match(r"Rules?:", l)), len(lines) - 1)
                item, rest = lines[:cut + 1], lines[cut + 1:]
                # Join wrapped lines with the previous line (label lines stay separate).
                merged = []
                for l in item:
                    if merged and not re.match(r"(Problem|Suggested rewrite|Rules?|Pass condition):", l) and len(merged) > 1:
                        merged[-1] += " " + l
                    else:
                        merged.append(l)
                item = merged
                if rest:
                    leftovers.append(" ".join(rest))
                n += 1
                kind_name = "rewrite_example" if "Problem:" in b else "deterministic_check"
                related = sorted(set(RULE_ID_ANY.findall(" ".join(item))))
                chunks.append(Document(
                    page_content=f"[{header_base} | {kind_name.replace('_', ' ')} {n}]\n" + "\n".join(item),
                    metadata={**common, "chunk_type": kind_name, "doc_type": _doc_type(None, part),
                              "related_rules": related, "chunk_id": f"{kind_name}-{n}"},
                ))
            for k, para in enumerate(leftovers):
                for q, piece in enumerate(re.split(r"(?<=\.)\s+(?=[A-Z][^.]{0,40}\.\s)", para)):
                    # Skip ingestion meta-notes; they pollute retrieval.
                    if len(piece) < 40 or piece.startswith("Suggested chunking"):
                        continue
                    chunks.append(Document(
                        page_content=f"[{header_base}]\n{piece.strip()}",
                        metadata={**common, "chunk_type": "note", "doc_type": _doc_type(None, part),
                                  "chunk_id": f"note-{sec_no}-{k}-{q}"}))
            continue

        # ---- C) Remaining free text (e.g. appendix notes) ----
        for k, para in enumerate([p for p in re.split(r"\n\s*\n|\n(?=[A-Z][^\n]*:)", section_text) if p.strip()]):
            para = _join_wrapped(para)
            if len(para) < 40:
                continue
            chunks.append(Document(
                page_content=f"[{header_base}]\n{para}",
                metadata={**common, "chunk_type": "note", "doc_type": _doc_type(None, part),
                          "chunk_id": f"note-{sec_no}-{k}"}))

    return chunks


# ------------------------------------------------------------------
# Legacy: email templates (kept for compatibility)
# ------------------------------------------------------------------
def split_email_templates(doc):
    text = doc.page_content
    base_metadata = {k: v for k, v in doc.metadata.items() if v is not None}
    parts = re.split(r"(?=Template \d+:)", text)
    chunks = []
    for part in parts:
        stripped = part.strip()
        if not stripped or not stripped.startswith("Template"):
            continue
        name_match = re.match(r"Template (\d+): (.+)", stripped)
        alert_match = re.search(r"🔍.*", part, re.DOTALL)
        body = re.sub(r"🔍.*", "", part, flags=re.DOTALL).strip()
        if body:
            meta = base_metadata.copy()
            meta.update({
                "chunk_type": "template",
                # Pinecone metadata disallows None, so use empty string.
                "template_num": name_match.group(1) if name_match else "",
                "template_name": name_match.group(2) if name_match else "",
            })
            chunks.append(Document(page_content=body, metadata=meta))
        if alert_match:
            meta = base_metadata.copy()
            meta.update({"chunk_type": "embedded_annotation"})
            chunks.append(Document(page_content=alert_match.group().strip(), metadata=meta))
    return chunks


def chunk_documents(documents):
    """
    Routing:
      - Policy / brand guide PDF  -> rule-based structural chunking
      - email PDF                 -> template chunking
      - other                     -> recursive character chunking
    """
    all_chunks = []
    for doc in documents:
        source = doc.metadata.get("source", "")
        if is_policy_doc(doc.page_content):
            chunks = split_policy_document(doc)
        elif "email" in source.lower():
            chunks = split_email_templates(doc)
        else:
            chunks = basic_splitter.split_documents([doc])
        all_chunks.extend(chunks)

    print(f"Total Chunks Created: {len(all_chunks)}")
    return all_chunks
