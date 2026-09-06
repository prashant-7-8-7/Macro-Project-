import csv
import json
from pathlib import Path
from typing import List, Dict, Any

class DocumentParser:
    @staticmethod
    def parse(file_path: str) -> List[Dict[str, Any]]:
        """
        Parses a file and returns a list of pages/sections.
        Each item is dict: {'text': str, 'page_number': int}
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        
        if ext == '.pdf':
            return DocumentParser._parse_pdf(path)
        elif ext in ['.txt', '.md']:
            return DocumentParser._parse_text(path)
        elif ext == '.docx':
            return DocumentParser._parse_docx(path)
        elif ext == '.csv':
            return DocumentParser._parse_csv(path)
        elif ext == '.json':
            return DocumentParser._parse_json(path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    @staticmethod
    def _parse_pdf(path: Path) -> List[Dict]:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            pages = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    pages.append({"text": text, "page_number": i + 1})
            return pages
        except Exception as e:
            raise RuntimeError(f"Error parsing PDF: {e}")

    @staticmethod
    def _parse_text(path: Path) -> List[Dict]:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        return [{"text": text, "page_number": 1}]

    @staticmethod
    def _parse_docx(path: Path) -> List[Dict]:
        try:
            from docx import Document
            doc = Document(str(path))
            text = "\n".join([p.text for p in doc.paragraphs if p.text])
            return [{"text": text, "page_number": 1}]
        except Exception as e:
            raise RuntimeError(f"Error parsing DOCX: {e}")

    @staticmethod
    def _parse_csv(path: Path) -> List[Dict]:
        lines = []
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                lines.append(" | ".join(row))
        text = "\n".join(lines)
        return [{"text": text, "page_number": 1}]

    @staticmethod
    def _parse_json(path: Path) -> List[Dict]:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        text = json.dumps(data, indent=2)
        return [{"text": text, "page_number": 1}]
