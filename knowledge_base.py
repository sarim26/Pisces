"""Local knowledge-base loader and keyword retrieval (Phase 1)."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from loguru import logger

from config import Config

STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is", "it",
    "this", "that", "with", "from", "at", "as", "be", "are", "was", "were",
    "by", "not", "no", "yes", "please", "help", "issue", "problem", "ticket",
    "how", "your", "you", "using", "procedure", "kindly", "below", "page",
    "making", "comfortable", "pisceser1", "marine", "infotech", "knowledge",
    "sharing", "click", "then",
}

TEXT_EXTENSIONS = {".md", ".txt"}
PDF_EXTENSIONS = {".pdf"}
SKIP_NAMES = {"keywords.json", "readme.md"}
HEADER_NOISE = [
    r"making you comfortable",
    r"pisceser1 marine infotech[^\n]*",
    r"cin u74999[^\n]*",
    r"vakratunda corporate park[^\n]*",
    r"www\.pisceser1marine\.com[^\n]*",
    r"operations@pisceser1marine\.com[^\n]*",
    r"knowledge sharing",
    r"page \d+ of \d+",
]


@dataclass
class KnowledgeChunk:
    source: str
    title: str
    text: str
    score: float = 0.0


class KnowledgeBase:
    """Load markdown, text, and PDF files and rank chunks against a ticket."""

    def __init__(self, root: Optional[str] = None):
        self.root = Path(root or Config.KNOWLEDGE_DIR)
        self.keywords_by_category: Dict[str, List[str]] = {}
        self.chunks: List[KnowledgeChunk] = []
        self.reload()

    def reload(self) -> None:
        self.keywords_by_category = self._load_keywords()
        self.chunks = self._load_chunks()
        logger.info(
            f"Knowledge base loaded: {len(self.chunks)} chunks from {self.root}"
        )

    def _load_keywords(self) -> Dict[str, List[str]]:
        path = self.root / "keywords.json"
        if not path.exists():
            logger.warning(f"No keywords.json at {path}")
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                str(category).lower(): [str(k).lower() for k in keywords]
                for category, keywords in data.items()
            }
        except Exception as e:
            logger.error(f"Failed to read keywords.json: {e}")
            return {}

    def _load_chunks(self) -> List[KnowledgeChunk]:
        if not self.root.exists():
            logger.warning(f"Knowledge directory missing: {self.root}")
            return []

        chunks: List[KnowledgeChunk] = []
        loaded_files = 0
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            if path.name.startswith(".") or path.name.lower() in SKIP_NAMES:
                continue
            suffix = path.suffix.lower()
            if suffix not in TEXT_EXTENSIONS | PDF_EXTENSIONS:
                logger.warning(f"Skipping unsupported knowledge file: {path.name}")
                continue
            try:
                text = self._read_file(path)
            except Exception as e:
                logger.error(f"Could not read knowledge file {path.name}: {e}")
                continue
            text = self._clean_text(text)
            title = self._title_from_filename(path)
            if not text:
                logger.warning(f"No extractable text in {path.name}; indexing filename only")
                text = title
            loaded_files += 1
            # Always prefix the article title so filename terms (VPN, RAID, RAM) match
            body = f"{title}\n\n{text}"
            for part_title, part_text in self._split_content(body, title, suffix):
                chunks.append(KnowledgeChunk(
                    source=str(path.relative_to(self.root)),
                    title=part_title,
                    text=part_text[:8000],
                ))
        logger.info(f"Indexed {loaded_files} knowledge files")
        return chunks

    def _read_file(self, path: Path) -> str:
        if path.suffix.lower() in PDF_EXTENSIONS:
            return self._read_pdf(path)
        return path.read_text(encoding="utf-8", errors="ignore")

    @staticmethod
    def _read_pdf(path: Path) -> str:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            extracted = page.extract_text() or ""
            pages.append(extracted)
        return "\n\n".join(pages)

    @staticmethod
    def _clean_text(text: str) -> str:
        text = text.replace("\uf0b7", "- ").replace("\uf076", "- ").replace("\u2022", "- ")
        for pattern in HEADER_NOISE:
            text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _title_from_filename(path: Path) -> str:
        stem = path.stem
        stem = re.sub(r"^(KS|Tech_KS|Tech KS)\s*_?\s*", "", stem, flags=re.IGNORECASE)
        stem = re.sub(r"^\d+\.\s*", "", stem)
        stem = stem.replace("+", " ").replace("_", " ").replace("-", " ")
        stem = re.sub(r"\s+", " ", stem).strip()
        return stem or path.stem

    def _split_content(self, text: str, fallback_title: str, suffix: str) -> List[Tuple[str, str]]:
        if suffix in PDF_EXTENSIONS:
            # Keep PDF articles as one procedure unless they are very long
            if len(text) <= 5000:
                return [(fallback_title, text)]
            parts = re.split(r"\n{2,}", text)
            buckets: List[str] = []
            current = ""
            for part in parts:
                if len(current) + len(part) > 3500 and current:
                    buckets.append(current.strip())
                    current = part
                else:
                    current = f"{current}\n\n{part}" if current else part
            if current.strip():
                buckets.append(current.strip())
            return [(fallback_title, bucket) for bucket in buckets] or [(fallback_title, text)]

        parts = re.split(r"\n(?=#{1,3} )", text)
        sections: List[Tuple[str, str]] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            first_line = part.splitlines()[0].lstrip("# ").strip()
            title = first_line or fallback_title
            sections.append((title, part))
        return sections or [(fallback_title, text)]

    def match_keywords(self, ticket_text: str) -> Dict[str, List[str]]:
        content = ticket_text.lower()
        hits: Dict[str, List[str]] = {}
        for category, keywords in self.keywords_by_category.items():
            matched = [kw for kw in keywords if kw in content]
            if matched:
                hits[category] = matched
        return hits

    def search(self, ticket_text: str, limit: Optional[int] = None) -> List[KnowledgeChunk]:
        limit = limit or Config.KNOWLEDGE_MAX_CHUNKS
        query_tokens = self._tokenize(ticket_text)
        keyword_hits = self.match_keywords(ticket_text)
        extra_tokens = {
            tok
            for kws in keyword_hits.values()
            for tok in self._tokenize(" ".join(kws))
        }
        query_tokens |= extra_tokens

        scored: List[KnowledgeChunk] = []
        for chunk in self.chunks:
            title_tokens = self._tokenize(chunk.title + " " + Path(chunk.source).stem)
            chunk_tokens = self._tokenize(chunk.text) | title_tokens
            if not chunk_tokens or not query_tokens:
                continue
            overlap = query_tokens & chunk_tokens
            title_overlap = query_tokens & title_tokens
            if not overlap:
                continue
            # Drop weak one-word hits (e.g. "menu" matching a random article)
            if len(overlap) < 2 and not title_overlap:
                continue
            score = len(overlap) / max(len(query_tokens), 1)
            if title_overlap:
                score += 0.35 * (len(title_overlap) / max(len(title_tokens), 1))
            for category, kws in keyword_hits.items():
                blob = f"{chunk.source} {chunk.title} {chunk.text}".lower()
                if category in blob or any(kw in blob for kw in kws[:4]):
                    score += 0.12
            scored.append(KnowledgeChunk(
                chunk.source,
                chunk.title,
                chunk.text,
                round(min(score, 1.0), 4),
            ))

        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:limit]

    def retrieval_score(self, chunks: Sequence[KnowledgeChunk]) -> float:
        if not chunks:
            return 0.0
        return min(max(chunks[0].score, 0.0), 1.0)

    @staticmethod
    def _tokenize(text: str) -> set:
        words = re.findall(r"[a-z0-9]{3,}", text.lower())
        return {w for w in words if w not in STOPWORDS}

    def format_context(self, chunks: Sequence[KnowledgeChunk]) -> str:
        if not chunks:
            return ""
        blocks = []
        for i, chunk in enumerate(chunks, start=1):
            blocks.append(
                f"[Source {i}: {chunk.source} — {chunk.title} | match={chunk.score:.2f}]\n{chunk.text}"
            )
        return "\n\n".join(blocks)
