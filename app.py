from __future__ import annotations

import cgi
import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlparse

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
REGULATION_CORPUS = ROOT / "data" / "regulations"
FEEDBACK_FILE = ROOT / "data" / "feedback.jsonl"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
CORPUS_CACHE: list[dict[str, Any]] | None = None
UPLOADED_DOCUMENTS: dict[str, dict[str, Any]] = {}

HEADING_RE = re.compile(
    r"""^\s*(
        (?P<num>\d+(?:\.\d+){0,5})(?:\s+|$)|
        (?P<cn>第[一二三四五六七八九十百千万0-9]+[章节条])|
        (?P<article>Article\s+\d+[A-Za-z]?)|
        (?P<annex>Annex\s+[A-Z0-9]+|Appendix\s+[A-Z0-9]+)
    )""",
    re.IGNORECASE | re.VERBOSE,
)
AMENDMENT_HEADING_RE = re.compile(
    r"^\s*(?:Insert|Delete|Add|Replace|Paragraphs?|Annex|Appendix).{0,180}?(?:amend to read|to read|insert|delete|replace|renumber|shall read|:)\s*$",
    re.IGNORECASE,
)
UN_DOC_NOISE_RE = re.compile(
    r"^(?:GE\.\d{2}-\d+|E/ECE/|E/TRANS/|United Nations|Agreement$|Addendum \d+|Revision \d+|_+$|\d{1,3}$)",
    re.IGNORECASE,
)
DOCUMENT_NOISE_RE = re.compile(
    r"^(?:ICS\s+[\d.]+|[A-Z]\s*\d{1,3}\s*$|\d{1,3}\s*[A-Z]\s*$|[IVXLCDM]{1,6}$|\d{1,4}$|GE\.\d{2}-\d+|GB\s+\d|Replace\s+GB|Issued on|Implemented on|Jointly Issued|NATIONAL STANDARD|中华人民共和国国家标准|UNITED NATIONS|COMMISSION REGULATION|REGULATION \(EU\)|\d{1,2}\s+[A-Z][a-z]+\s+\d{4})",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?\s*(?:%|mm|cm|m|kg|g|N|kN|V|A|W|kW|s|ms|min|h|km/h|g/km|ppm|dB)?", re.I)
REFERENCE_RE = re.compile(r"\b(?:GB|GB/T|ISO|IEC|ECE|UN\s*R|FMVSS|SAE|EN)\s*[-/]?\s*\d+[A-Z0-9\-:]*", re.I)
LEADER_RE = re.compile(r"[.\u2026]{5,}\s*\d{1,4}\s*$")
TECH_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?\s*(?:%|mm|cm|m|kg|g|N|kN|V|A|W|kW|s|ms|min|h|km/h|g/km|ppm|dB)\b", re.I)
BARE_LIMIT_RE = re.compile(r"\b(?:not exceeding|exceeding|less than|more than|at least|minimum|maximum|greater than|no less than|no more than|shall be|限值|不超过|超过|小于|大于|至少|最大|最小)\s+[-+]?\d+(?:\.\d+)?\b", re.I)
SCOPE_WORDS = ("scope", "适用", "范围", "applies", "application")
TEST_WORDS = ("test", "测试", "试验", "procedure", "method", "方法")
DEFINITION_WORDS = ("definition", "术语", "定义", "means", "refers to")


@dataclass
class Clause:
    id: str
    heading: str
    text: str
    start_page: int
    end_page: int


@dataclass
class MatchResult:
    left: Clause | None
    right: Clause | None
    score: float
    change_type: str
    risk: str
    summary: str
    evidence: list[str]


def normalize_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "")
    return value.strip().lower()


def extract_pdf(path: Path) -> list[dict[str, Any]]:
    reader = PdfReader(str(path))
    pages: list[dict[str, Any]] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        pages.append({"page": index, "text": cleaned})
    return pages


def split_clauses(pages: list[dict[str, Any]]) -> list[Clause]:
    clauses: list[Clause] = []
    current_heading = ""
    current_lines: list[str] = []
    start_page = 1
    end_page = 1

    def flush() -> None:
        nonlocal current_heading, current_lines, start_page, end_page
        body = "\n".join(current_lines).strip()
        if not body or len(body) < 30:
            return
        heading = current_heading or body.splitlines()[0][:90]
        clauses.append(
            Clause(
                id=f"C{len(clauses) + 1:04d}",
                heading=heading,
                text=body,
                start_page=start_page,
                end_page=end_page,
            )
        )
        current_heading = ""
        current_lines = []

    amendment_document = any(
        "Amendment" in str(page["text"]) and ("UN Regulation No. 13" in str(page["text"]) or "Addendum 12" in str(page["text"]))
        for page in pages[:2]
    )

    for page in pages:
        page_no = int(page["page"])
        if amendment_document and page_no == 1:
            continue
        for raw_line in str(page["text"]).splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if is_toc_or_index_line(line):
                continue
            if DOCUMENT_NOISE_RE.match(line):
                continue
            if amendment_document and UN_DOC_NOISE_RE.match(line):
                continue
            is_heading = (bool(HEADING_RE.match(line)) or bool(AMENDMENT_HEADING_RE.match(line))) and len(line) <= 220
            if is_heading and current_lines:
                flush()
                current_heading = line
                start_page = page_no
            elif is_heading:
                current_heading = line
                start_page = page_no

            current_lines.append(line)
            end_page = page_no

    flush()
    if amendment_document and clauses:
        return clauses
    if len(clauses) >= 2:
        return clauses

    return split_fallback_paragraphs(pages)


def split_fallback_paragraphs(pages: list[dict[str, Any]]) -> list[Clause]:
    clauses: list[Clause] = []
    for page in pages:
        page_no = int(page["page"])
        chunks = re.split(r"\n{2,}|(?<=[。.!?])\s+(?=[A-Z0-9第])", str(page["text"]))
        for chunk in chunks:
            text = "\n".join(line for line in chunk.strip().splitlines() if not is_toc_or_index_line(line))
            if len(text) < 20:
                continue
            clauses.append(
                Clause(
                    id=f"C{len(clauses) + 1:04d}",
                    heading=text.splitlines()[0][:90],
                    text=text,
                    start_page=page_no,
                    end_page=page_no,
                )
            )
    return clauses


def similarity(left: Clause, right: Clause) -> float:
    left_key = normalize_text(f"{left.heading}\n{left.text[:1200]}")
    right_key = normalize_text(f"{right.heading}\n{right.text[:1200]}")
    return SequenceMatcher(None, left_key, right_key).ratio()


def classify_change(left: Clause | None, right: Clause | None, score: float) -> tuple[str, str, str, list[str]]:
    if left is None and right is not None:
        return "新增要求", "中", "右侧文档包含左侧未匹配到的条款。", [quote(right.text)]
    if right is None and left is not None:
        return "删除要求", "中", "左侧文档中的条款在右侧未匹配到。", [quote(left.text)]
    if left is None or right is None:
        return "无法判断", "高", "缺少可比较文本。", []

    left_norm = normalize_text(left.text)
    right_norm = normalize_text(right.text)
    if left_norm == right_norm:
        return "无实质变化", "低", "两个条款文本一致或高度一致。", [quote(left.text), quote(right.text)]

    if score < 0.5:
        return "疑似无对应条款", "中", "两个片段匹配度较低，暂不判定为实质数值变化。", [quote(left.text), quote(right.text)]

    left_numbers = extract_requirement_numbers(left.text)
    right_numbers = extract_requirement_numbers(right.text)
    refs_changed = set(REFERENCE_RE.findall(left.text)) != set(REFERENCE_RE.findall(right.text))
    combined = f"{left_norm} {right_norm}"

    if left_numbers and right_numbers and left_numbers != right_numbers:
        change_type = "阈值/数值变化"
        risk = "高"
        detail = f"检测到数值或单位集合变化：左侧 {sorted(left_numbers)[:8]}；右侧 {sorted(right_numbers)[:8]}。"
    elif score >= 0.82 and min(len(left.text), len(right.text)) < 900:
        change_type = "相似条款/可能等效"
        risk = "低"
        detail = "两个片段高度相似，且未检测到明确技术阈值变化；更适合作为对应主题查看。"
    elif refs_changed:
        change_type = "引用标准变化"
        risk = "中"
        detail = "检测到引用标准编号或标准清单变化。"
    elif any(word in combined for word in TEST_WORDS):
        change_type = "测试方法变化"
        risk = "高"
        detail = "差异出现在测试、试验或方法相关条款中，需要工程确认。"
    elif any(word in combined for word in SCOPE_WORDS):
        change_type = "适用范围变化"
        risk = "高"
        detail = "差异出现在适用范围相关条款中。"
    elif any(word in combined for word in DEFINITION_WORDS):
        change_type = "定义变化"
        risk = "中"
        detail = "差异出现在定义或术语相关条款中。"
    elif score >= 0.9:
        change_type = "措辞变化"
        risk = "低"
        detail = "文本高度相似，初步判断更可能是措辞或格式变化。"
    else:
        change_type = "内容修改"
        risk = "中"
        detail = "条款内容存在可见修改。"

    return change_type, risk, detail, [quote(left.text), quote(right.text)]


def quote(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:320] + ("..." if len(compact) > 320 else "")


def excerpt(text: str, limit: int = 1400) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:limit] + ("..." if len(compact) > limit else "")


def is_toc_or_index_line(line: str) -> bool:
    compact = line.strip()
    if not compact:
        return False
    if LEADER_RE.search(compact):
        return True
    dot_count = compact.count(".") + compact.count("…")
    return dot_count >= 8 and len(re.sub(r"[.\u2026\s\d]", "", compact)) < 40


def extract_requirement_numbers(text: str) -> set[str]:
    clean_lines = [line for line in text.splitlines() if not is_toc_or_index_line(line)]
    clean_text = "\n".join(clean_lines)
    technical = {match.group(0).strip() for match in TECH_NUMBER_RE.finditer(clean_text)}
    contextual = {
        NUMBER_RE.search(match.group(0)).group(0).strip()
        for match in BARE_LIMIT_RE.finditer(clean_text)
        if NUMBER_RE.search(match.group(0))
    }
    return {value for value in technical | contextual if len(value) > 1}


def compare_clauses(left_clauses: list[Clause], right_clauses: list[Clause]) -> list[MatchResult]:
    results: list[MatchResult] = []
    used_right: set[int] = set()

    for left in left_clauses:
        best_index = -1
        best_score = 0.0
        for index, right in enumerate(right_clauses):
            if index in used_right:
                continue
            score = similarity(left, right)
            if score > best_score:
                best_score = score
                best_index = index

        if best_index >= 0 and best_score >= 0.32:
            right = right_clauses[best_index]
            used_right.add(best_index)
            change_type, risk, summary, evidence = classify_change(left, right, best_score)
            results.append(MatchResult(left, right, best_score, change_type, risk, summary, evidence))
        else:
            change_type, risk, summary, evidence = classify_change(left, None, 0.0)
            results.append(MatchResult(left, None, 0.0, change_type, risk, summary, evidence))

    for index, right in enumerate(right_clauses):
        if index not in used_right:
            change_type, risk, summary, evidence = classify_change(None, right, 0.0)
            results.append(MatchResult(None, right, 0.0, change_type, risk, summary, evidence))

    return sorted(results, key=result_order, reverse=True)


def risk_order(risk: str) -> int:
    return {"高": 3, "中": 2, "低": 1}.get(risk, 0)


def result_order(item: MatchResult) -> tuple[int, int, float]:
    type_rank = {
        "阈值/数值变化": 5,
        "测试方法变化": 4,
        "适用范围变化": 4,
        "引用标准变化": 3,
        "定义变化": 3,
        "内容修改": 2,
        "新增要求": 1,
        "删除要求": 1,
        "疑似无对应条款": 0,
        "相似条款/可能等效": 0,
        "措辞变化": 0,
        "无实质变化": -1,
    }
    return (type_rank.get(item.change_type, 0), risk_order(item.risk), item.score)


def serialize_result(result: MatchResult) -> dict[str, Any]:
    data = asdict(result)
    data["score"] = round(result.score, 3)
    return data


def build_compare_conclusion(left_name: str, right_name: str, results: list[MatchResult]) -> dict[str, Any]:
    total = len(results)
    counts: dict[str, int] = {}
    risks: dict[str, int] = {}
    for item in results:
        counts[item.change_type] = counts.get(item.change_type, 0) + 1
        risks[item.risk] = risks.get(item.risk, 0) + 1

    substantive_types = {"阈值/数值变化", "测试方法变化", "适用范围变化", "引用标准变化", "定义变化", "内容修改"}
    substantive = [item for item in results if item.change_type in substantive_types]
    additions = counts.get("新增要求", 0)
    deletions = counts.get("删除要求", 0)
    low_confidence = counts.get("疑似无对应条款", 0)

    if substantive:
        headline = f"初步结论：两份文档存在 {len(substantive)} 条可能影响工程判断的实质差异。"
    elif additions or deletions:
        headline = f"初步结论：未发现明确的同条款实质修改，但存在 {additions} 条新增和 {deletions} 条删除/未匹配条款。"
    else:
        headline = "初步结论：未发现明显实质差异，主要差异可能来自格式、目录或低置信度匹配。"

    key_findings = []
    for item in substantive[:6]:
        heading = item.left.heading if item.left else item.right.heading if item.right else "未命名条款"
        key_findings.append(
            {
                "type": item.change_type,
                "risk": item.risk,
                "score": round(item.score, 3),
                "heading": heading,
                "summary": item.summary,
            }
        )

    caveats = []
    if low_confidence:
        caveats.append(f"有 {low_confidence} 条低匹配度结果，建议人工确认后再用于合规结论。")
    if total and (additions + deletions) / total > 0.35:
        caveats.append("新增/删除占比较高，可能是文档结构、目录、样页或版本范围不一致导致。")
    caveats.append("本摘要基于本地文本解析和规则分类，最终法规解释仍需查看原文证据。")

    return {
        "headline": headline,
        "left": left_name,
        "right": right_name,
        "counts": counts,
        "risks": risks,
        "key_findings": key_findings,
        "caveats": caveats,
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self.send_file(STATIC / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/static/"):
            target = STATIC / parsed.path.removeprefix("/static/")
            content_type = "text/css; charset=utf-8" if target.suffix == ".css" else "application/javascript; charset=utf-8"
            self.send_file(target, content_type)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/api/feedback":
            self.handle_feedback()
            return
        if self.path == "/api/upload-document":
            self.handle_upload_document()
            return
        if self.path == "/api/ask":
            self.handle_ask()
            return
        if self.path != "/api/compare":
            self.send_error(404)
            return
        content_length = int(self.headers.get("content-length", "0"))
        if content_length > MAX_UPLOAD_BYTES:
            self.send_json({"error": "文件太大，单次上传请控制在 50MB 内。"}, status=413)
            return

        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        left_file = form["left"] if "left" in form else None
        right_file = form["right"] if "right" in form else None
        if left_file is None or right_file is None or not left_file.file or not right_file.file:
            self.send_json({"error": "请同时上传两个 PDF 文件。"}, status=400)
            return

        try:
            with TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                left_path = tmp_dir / "left.pdf"
                right_path = tmp_dir / "right.pdf"
                left_path.write_bytes(left_file.file.read())
                right_path.write_bytes(right_file.file.read())

                left_pages = extract_pdf(left_path)
                right_pages = extract_pdf(right_path)
                left_clauses = split_clauses(left_pages)
                right_clauses = split_clauses(right_pages)
                results = compare_clauses(left_clauses, right_clauses)

                self.send_json(
                    {
                        "left": document_summary(left_file.filename, left_pages, left_clauses),
                        "right": document_summary(right_file.filename, right_pages, right_clauses),
                        "conclusion": build_compare_conclusion(left_file.filename, right_file.filename, results),
                        "results": [serialize_result(item) for item in results],
                    }
                )
        except Exception as exc:
            self.send_json({"error": f"解析失败：{html.escape(str(exc))}"}, status=500)

    def handle_ask(self) -> None:
        content_length = int(self.headers.get("content-length", "0"))
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            question = str(payload.get("question", "")).strip()
            doc_id = str(payload.get("doc_id", "")).strip()
            if len(question) < 2:
                self.send_json({"error": "请输入要查询的问题。"}, status=400)
                return
            if doc_id:
                if doc_id not in UPLOADED_DOCUMENTS:
                    self.send_json({"error": "未找到已上传的法规文档，请重新上传。"}, status=404)
                    return
                results = search_uploaded_document(question, doc_id)
            else:
                results = search_corpus(question)
            self.send_json(
                {
                    "question": question,
                    "answer": build_retrieval_answer(question, results),
                    "results": results,
                }
            )
        except Exception as exc:
            self.send_json({"error": f"检索失败：{html.escape(str(exc))}"}, status=500)

    def handle_feedback(self) -> None:
        content_length = int(self.headers.get("content-length", "0"))
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            feedback = {
                "admin": "13248301527@139.com",
                "user": str(payload.get("user", "demo_user")).strip()[:120],
                "type": str(payload.get("type", "general")).strip()[:80],
                "message": str(payload.get("message", "")).strip()[:3000],
                "contact": str(payload.get("contact", "")).strip()[:160],
            }
            if not feedback["message"]:
                self.send_json({"error": "请填写反馈内容。"}, status=400)
                return
            FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
            with FEEDBACK_FILE.open("a", encoding="utf-8") as file:
                file.write(json.dumps(feedback, ensure_ascii=False) + "\n")
            self.send_json({"ok": True, "message": "反馈已记录，将汇总给管理员 13248301527@139.com。"})
        except Exception as exc:
            self.send_json({"error": f"反馈提交失败：{html.escape(str(exc))}"}, status=500)

    def handle_upload_document(self) -> None:
        content_length = int(self.headers.get("content-length", "0"))
        if content_length > MAX_UPLOAD_BYTES:
            self.send_json({"error": "文件太大，单次上传请控制在 50MB 内。"}, status=413)
            return

        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        uploaded = form["document"] if "document" in form else None
        if uploaded is None or not uploaded.file:
            self.send_json({"error": "请上传一个 PDF 文件。"}, status=400)
            return

        try:
            with TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                pdf_path = tmp_dir / "document.pdf"
                pdf_path.write_bytes(uploaded.file.read())
                pages = extract_pdf(pdf_path)
                clauses = split_clauses(pages)
                doc_id = f"doc_{len(UPLOADED_DOCUMENTS) + 1}_{abs(hash(uploaded.filename))}"
                chunks = chunks_from_clauses(clauses, uploaded.filename, doc_id)
                UPLOADED_DOCUMENTS[doc_id] = {
                    "filename": uploaded.filename,
                    "pages": len(pages),
                    "clauses": len(clauses),
                    "chunks": chunks,
                }
                self.send_json(
                    {
                        "doc_id": doc_id,
                        "filename": uploaded.filename,
                        "pages": len(pages),
                        "clauses": len(clauses),
                    }
                )
        except Exception as exc:
            self.send_json({"error": f"上传解析失败：{html.escape(str(exc))}"}, status=500)

    def send_file(self, path: Path, content_type: str) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def document_summary(filename: str, pages: list[dict[str, Any]], clauses: list[Clause]) -> dict[str, Any]:
    return {
        "filename": filename,
        "pages": len(pages),
        "clauses": len(clauses),
        "empty_pages": sum(1 for page in pages if not page["text"]),
    }


def search_corpus(question: str, limit: int = 8) -> list[dict[str, Any]]:
    chunks = load_corpus_chunks()
    return search_chunks(question, chunks, limit)


def search_uploaded_document(question: str, doc_id: str, limit: int = 8) -> list[dict[str, Any]]:
    document = UPLOADED_DOCUMENTS.get(doc_id)
    if not document:
        return []
    return search_chunks(question, document["chunks"], limit)


def search_chunks(question: str, chunks: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    query_tokens = set(tokenize(question))
    if not query_tokens:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in chunks:
        chunk_tokens = chunk["tokens"]
        overlap = query_tokens & chunk_tokens
        if not overlap:
            continue
        score = len(overlap) / (len(query_tokens) ** 0.5 * len(chunk_tokens) ** 0.35)
        if any(token in chunk["text"].lower() for token in query_tokens):
            score += 0.15
        scored.append((score, chunk))

    results = []
    for score, chunk in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]:
        item = {key: value for key, value in chunk.items() if key != "tokens"}
        item["score"] = round(score, 3)
        results.append(item)
    return results


def build_retrieval_answer(question: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return "没有在本地法规库中找到明显相关条款。请换一个关键词，或补充完整法规 PDF。"
    question_tokens = set(tokenize(question))
    intent = detect_question_intent(question)
    best_sentences = []
    for result in results[:12]:
        for sentence in split_sentences(result["text"]):
            sentence_tokens = set(tokenize(sentence))
            overlap = len(question_tokens & sentence_tokens)
            numbers = extract_answer_numbers(sentence)
            unit_bonus = answer_unit_bonus(numbers, intent)
            if intent and not unit_bonus and not sentence_matches_intent(sentence, intent):
                continue
            if overlap or numbers:
                best_sentences.append((overlap * 2 + unit_bonus + len(numbers) * 0.4, sentence, numbers, result, unit_bonus))

    best_sentences.sort(key=lambda item: item[0], reverse=True)
    if intent and any(item[4] >= 5 for item in best_sentences):
        best_sentences = [item for item in best_sentences if item[4] >= 5]
    if not best_sentences:
        result = results[0]
        return f"没有抽取到明确数值。最相关依据是 {result['code']}，{result['heading']}，位置 {result['page']}：{result['text']}"

    top = best_sentences[0]
    _, sentence, numbers, result, _ = top
    if numbers:
        answer = f"直接答案：相关数值为 {', '.join(numbers[:8])}。"
    else:
        answer = f"直接答案：{sentence}"

    answer += f"\n依据：{result['code']}，{result['heading']}，位置 {result['page']}。"
    answer += f"\n原文片段：{sentence}"

    if len(best_sentences) > 1:
        supporting = []
        seen = {sentence}
        for _, support_sentence, support_numbers, support_result, _ in best_sentences[1:4]:
            if support_sentence in seen:
                continue
            seen.add(support_sentence)
            value = f"{support_result['code']} {support_result['page']}：{support_sentence}"
            if support_numbers:
                value += f"（数值：{', '.join(support_numbers[:5])}）"
            supporting.append(value)
        if supporting:
            answer += "\n其他相关依据：" + "；".join(supporting)

    return answer


def split_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[。.!?;；])\s+|(?<=\.)\s+(?=[A-Z])", compact)
    sentences = [part.strip() for part in parts if len(part.strip()) >= 20]
    windows = list(sentences)
    for index in range(len(sentences) - 1):
        windows.append(f"{sentences[index]} {sentences[index + 1]}")
    return windows


def extract_answer_numbers(text: str) -> list[str]:
    patterns = [
        r"[-+]?\d+(?:\.\d+)?\s*(?:\u00b0C|\u2103|\u00b0F|K|degrees?\s+C|degrees?\s+F)\b",
        r"[-+]?\d+(?:\.\d+)?\s*(?:°C|℃|°F|K|degrees?\s+C|degrees?\s+F|\bC\b|\bF\b|percent|%|mm|cm|m|km|kg|g|N|kN|daN|Nm|N·m|V|A|W|kW|s|ms|min|h|km/h|mph|kPa|MPa|bar|g/km|g/kWh|mg/kWh|ppm|dB|dB\\(A\\)|cd|lx|lux|degrees?|°)\b",
        r"\b(?:minus|negative)?\s*\d+(?:\.\d+)?\s*degrees?\b",
    ]
    values = []
    for pattern in patterns:
        values.extend(match.group(0).strip() for match in re.finditer(pattern, text, re.I))
    deduped = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def detect_question_intent(question: str) -> str:
    lowered = question.lower()
    if any(term in lowered for term in ["温度", "temperature", "ambient", "℃", "°c"]):
        return "temperature"
    if any(term in lowered for term in ["速度", "speed", "km/h", "mph"]):
        return "speed"
    if any(term in lowered for term in ["压力", "pressure", "kpa", "mpa", "bar"]):
        return "pressure"
    if any(term in lowered for term in ["距离", "distance"]):
        return "distance"
    if any(term in lowered for term in ["力", "载荷", "force", "load", "kn", "dan"]):
        return "force"
    if any(term in lowered for term in ["噪声", "noise", "db"]):
        return "noise"
    if any(term in lowered for term in ["排放", "emission", "g/kwh", "mg/kwh"]):
        return "emission"
    if any(term in lowered for term in ["角度", "angle", "degree"]):
        return "angle"
    if any(term in lowered for term in ["照度", "亮度", "luminous", "lux", "candela", "cd"]):
        return "lighting"
    return ""


def answer_unit_bonus(numbers: list[str], intent: str) -> float:
    if not intent:
        return len(numbers) * 1.5
    unit_map = {
        "temperature": ("°c", "℃", "°f", "degrees", " k"),
        "speed": ("km/h", "mph"),
        "pressure": ("kpa", "mpa", "bar"),
        "distance": (" mm", " cm", " m"),
        "force": ("kn", "dan", " n", "nm", "n·m"),
        "noise": ("db", "db(a)"),
        "emission": ("g/kwh", "mg/kwh", "g/km", "ppm"),
        "angle": ("degree", "°"),
        "lighting": ("lx", "lux", "cd"),
    }
    units = unit_map.get(intent, ())
    if intent == "temperature":
        units = units + ("\u00b0c", "\u2103", "\u00b0f")
    bonus = 0.0
    for number in numbers:
        lowered = number.lower()
        bonus += 5.0 if any(unit in lowered for unit in units) else 0.2
    return bonus


def sentence_matches_intent(sentence: str, intent: str) -> bool:
    lowered = sentence.lower()
    terms = {
        "temperature": ("temperature", "ambient", "cold", "hot", "温度"),
        "speed": ("speed", "velocity", "速度"),
        "pressure": ("pressure", "压力"),
        "distance": ("distance", "stopping", "距离"),
        "force": ("force", "load", "载荷", "力"),
        "noise": ("noise", "sound", "噪声"),
        "emission": ("emission", "pollutant", "排放"),
        "angle": ("angle", "degree", "角度"),
        "lighting": ("luminous", "illuminance", "lighting", "照度", "亮度"),
    }
    return any(term in lowered for term in terms.get(intent, ()))


def load_corpus_chunks() -> list[dict[str, Any]]:
    global CORPUS_CACHE
    if CORPUS_CACHE is not None:
        return CORPUS_CACHE

    chunks: list[dict[str, Any]] = []
    manifest_path = REGULATION_CORPUS / "manifest.json"
    if not manifest_path.exists():
        CORPUS_CACHE = []
        return CORPUS_CACHE

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest:
        path = ROOT / entry["path"]
        if not path.exists() or path.suffix.lower() not in {".pdf", ".xml"}:
            continue
        try:
            entry_chunks = extract_search_chunks(path, entry)
        except Exception:
            continue
        for chunk in entry_chunks:
            tokens = set(tokenize(chunk["text"] + " " + entry["code"] + " " + entry["title"]))
            if tokens:
                chunk["tokens"] = tokens
                chunks.append(chunk)

    CORPUS_CACHE = chunks
    return CORPUS_CACHE


def extract_search_chunks(path: Path, entry: dict[str, Any]) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".pdf":
        pages = extract_pdf(path)
        clauses = split_clauses(pages)
        return chunks_from_clauses(clauses, entry["title"], entry["code"], entry["domain"], entry["region"], str(path.relative_to(ROOT)))

    root = ET.parse(path).getroot()
    section_text = " ".join(root.itertext())
    section_text = re.sub(r"\s+", " ", section_text).strip()
    chunks = []
    for index, text in enumerate(split_long_text(section_text), start=1):
        chunks.append(
            {
                "code": entry["code"],
                "title": entry["title"],
                "domain": entry["domain"],
                "region": entry["region"],
                "path": str(path.relative_to(ROOT)),
                "heading": f"{entry['code']} chunk {index}",
                "page": "CFR XML",
                "text": excerpt(text),
            }
        )
    return chunks


def chunks_from_clauses(
    clauses: list[Clause],
    title: str,
    code: str,
    domain: str = "uploaded_document",
    region: str = "uploaded",
    path: str = "",
) -> list[dict[str, Any]]:
    chunks = [
        {
            "code": code,
            "title": title,
            "domain": domain,
            "region": region,
            "path": path,
            "heading": clause.heading,
            "page": f"{clause.start_page}-{clause.end_page}",
            "text": excerpt(clause.text),
        }
        for clause in clauses
        if len(clause.text.strip()) > 40
    ]
    for chunk in chunks:
        chunk["tokens"] = set(tokenize(chunk["text"] + " " + chunk["code"] + " " + chunk["title"]))
    return chunks


def split_long_text(text: str, size: int = 1200, overlap: int = 160) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        chunk = text[start : start + size].strip()
        if len(chunk) > 80:
            chunks.append(chunk)
        start += max(1, size - overlap)
    return chunks


def tokenize(text: str) -> list[str]:
    lowered = expand_query_terms(text.lower())
    words = re.findall(r"[a-z0-9][a-z0-9./-]{1,}|[\u4e00-\u9fff]{2,}", lowered)
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
    grams = [cjk[index : index + 2] for index in range(max(0, len(cjk) - 1))]
    return words + grams


def expand_query_terms(text: str) -> str:
    mapping = {
        "温度": " temperature ambient initial hot cold celsius",
        "环境温度": " ambient temperature",
        "初始温度": " initial temperature",
        "制动": " braking brake",
        "刹车": " braking brake",
        "速度": " speed velocity km/h mph",
        "压力": " pressure kpa mpa bar",
        "距离": " distance stopping distance",
        "减速度": " deceleration",
        "适用": " application scope applies vehicles categories",
        "车辆": " vehicle vehicles category categories",
        "挂车": " trailer trailers",
        "报警": " warning signal",
        "碰撞": " collision",
        "稳定": " stability control",
        "转向": " steering",
        "防护": " underrun protection guard protective device",
        "后防护": " rear underrun protection guard",
        "前防护": " front underrun protection",
        "侧防护": " lateral protection side guard",
        "视野": " indirect vision mirror rear visibility",
        "照明": " lighting lamps light-signalling luminous intensity",
        "灯具": " lamps lighting light-signalling",
        "电磁": " electromagnetic compatibility emc",
        "网络安全": " cyber security",
        "软件更新": " software update",
        "排放": " emissions pollutants g/kwh mg/kwh",
        "噪声": " noise sound dB",
        "轮胎": " tyres tires rims load index speed category",
        "挂接": " coupling fifth wheel drawbar mechanical coupling",
        "载荷": " load force kN daN",
        "角度": " angle degrees",
        "照度": " luminous intensity illuminance lux cd",
    }
    expanded = text
    for term, addition in mapping.items():
        if term in text:
            expanded += addition
    return expanded


def main() -> None:
    port = 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"法规对比原型已启动：http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
