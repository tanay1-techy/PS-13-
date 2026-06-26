"""
Document Chunker for RAG Pipeline

Splits runbook markdown files into semantically coherent chunks with metadata
(runbook ID, device type, fault category, classification level).
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.config import rag_cfg, get_path


def _extract_metadata(content: str, filename: str) -> Dict[str, Any]:
    """Extract structured metadata from runbook markdown headers."""
    metadata = {
        "runbook_id": "",
        "title": "",
        "classification": "UNCLASSIFIED",
        "applicable_devices": [],
        "fault_category": "",
        "source_file": filename,
    }

    # Extract runbook ID from filename (e.g., RB-101)
    id_match = re.search(r"(RB-\d+)", filename)
    if id_match:
        metadata["runbook_id"] = id_match.group(1)

    # Extract title from first heading
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if title_match:
        metadata["title"] = title_match.group(1).strip()

    # Extract classification
    class_match = re.search(r"Classification:\s*(\w+)", content)
    if class_match:
        metadata["classification"] = class_match.group(1).strip()

    # Extract applicable devices
    device_match = re.search(r"Applicable Devices:\s*(.+)$", content, re.MULTILINE)
    if device_match:
        devices = [d.strip() for d in device_match.group(1).split(",")]
        metadata["applicable_devices"] = devices

    # Extract fault category
    fault_match = re.search(r"Fault Category:\s*(.+)$", content, re.MULTILINE)
    if fault_match:
        metadata["fault_category"] = fault_match.group(1).strip()

    return metadata


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate (1 token ≈ 4 characters for English text)."""
    return len(text) // 4


def chunk_document(
    content: str,
    filename: str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Split a runbook document into semantically coherent chunks.

    Strategy:
    1. Split by markdown sections (##, ###)
    2. If a section exceeds chunk_size, split by paragraphs
    3. Maintain overlap for context continuity
    4. Attach metadata to each chunk
    """
    cfg = rag_cfg()
    if chunk_size is None:
        chunk_size = cfg.get("chunk_size_tokens", 400)
    if chunk_overlap is None:
        chunk_overlap = cfg.get("chunk_overlap_tokens", 50)

    metadata = _extract_metadata(content, filename)

    # Split by major sections
    sections = re.split(r"\n(?=###?\s)", content)
    chunks = []
    chunk_idx = 0

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Extract section heading
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", section, re.MULTILINE)
        section_title = heading_match.group(2).strip() if heading_match else ""

        est_tokens = _estimate_tokens(section)

        if est_tokens <= chunk_size:
            # Section fits in one chunk
            chunks.append({
                "chunk_id": f"{metadata['runbook_id']}_chunk_{chunk_idx}",
                "text": section,
                "section": section_title,
                "token_estimate": est_tokens,
                **metadata,
            })
            chunk_idx += 1
        else:
            # Split by paragraphs (double newline)
            paragraphs = re.split(r"\n\n+", section)
            current_chunk = ""
            current_tokens = 0

            for para in paragraphs:
                para_tokens = _estimate_tokens(para)

                if current_tokens + para_tokens > chunk_size and current_chunk:
                    # Save current chunk
                    chunks.append({
                        "chunk_id": f"{metadata['runbook_id']}_chunk_{chunk_idx}",
                        "text": current_chunk.strip(),
                        "section": section_title,
                        "token_estimate": current_tokens,
                        **metadata,
                    })
                    chunk_idx += 1

                    # Start new chunk with overlap (last portion of previous)
                    overlap_text = current_chunk[-chunk_overlap * 4:]  # approx token->char
                    current_chunk = overlap_text + "\n\n" + para
                    current_tokens = _estimate_tokens(current_chunk)
                else:
                    current_chunk += "\n\n" + para if current_chunk else para
                    current_tokens += para_tokens

            # Don't forget the last chunk
            if current_chunk.strip():
                chunks.append({
                    "chunk_id": f"{metadata['runbook_id']}_chunk_{chunk_idx}",
                    "text": current_chunk.strip(),
                    "section": section_title,
                    "token_estimate": _estimate_tokens(current_chunk),
                    **metadata,
                })
                chunk_idx += 1

    return chunks


def chunk_all_runbooks(runbooks_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Load and chunk all runbook markdown files from the runbooks directory.
    """
    if runbooks_dir is None:
        runbooks_dir = get_path("paths.runbooks_dir")

    all_chunks = []
    md_files = sorted(runbooks_dir.glob("*.md"))

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        chunks = chunk_document(content, md_file.name)
        all_chunks.extend(chunks)

    return all_chunks


if __name__ == "__main__":
    chunks = chunk_all_runbooks()
    print(f"✅ Chunked {len(chunks)} chunks from runbooks")
    for c in chunks[:5]:
        print(f"   {c['chunk_id']}: {c['section'][:50]} ({c['token_estimate']} tokens) [{c['classification']}]")
