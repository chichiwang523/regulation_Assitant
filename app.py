from __future__ import annotations

import cgi
import hashlib
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib import error as urlerror
from urllib.parse import urlparse
from urllib import request as urlrequest

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
REGULATION_CORPUS = ROOT / "data" / "regulations"
FEEDBACK_FILE = ROOT / "data" / "feedback.jsonl"
USERS_FILE = ROOT / "data" / "users.json"
INVITE_CODES_FILE = ROOT / "data" / "invite_codes.json"
UPLOAD_ARCHIVE_DIR = ROOT / "data" / "uploads"
UPLOAD_FILES_DIR = UPLOAD_ARCHIVE_DIR / "files"
UPLOAD_CACHE_DIR = UPLOAD_ARCHIVE_DIR / "cache"
UPLOAD_INDEX_FILE = UPLOAD_ARCHIVE_DIR / "index.json"
ARCHIVE_LOCK = threading.Lock()
USAGE_LOG_FILE = ROOT / "data" / "usage.jsonl"
USAGE_LOCK = threading.Lock()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(ROOT / ".env")

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
CORPUS_CACHE: list[dict[str, Any]] | None = None
CORPUS_LOCK = threading.Lock()
OCR_CACHE_DIR = REGULATION_CORPUS / "_cache" / "ocr"
OCR_ENABLED = os.environ.get("REG_ASSISTANT_OCR_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
OCR_LANGS = os.environ.get("REG_ASSISTANT_OCR_LANGS", "eng").strip() or "eng"
# Uploads may be Chinese GB standards; OCR them with both English + Simplified
# Chinese so scanned CN documents are searchable too.
UPLOAD_OCR_LANGS = os.environ.get("REG_ASSISTANT_UPLOAD_OCR_LANGS", "eng+chi_sim").strip() or "eng+chi_sim"
OCR_LOW_TEXT_PAGE_CHARS = int(os.environ.get("REG_ASSISTANT_OCR_LOW_TEXT_PAGE_CHARS", "40"))
OCR_TRIGGER_LOW_TEXT_RATIO = float(os.environ.get("REG_ASSISTANT_OCR_TRIGGER_LOW_TEXT_RATIO", "0.20"))
OCR_TRIGGER_TOTAL_CHARS_PER_PAGE = int(os.environ.get("REG_ASSISTANT_OCR_TRIGGER_TOTAL_CHARS_PER_PAGE", "80"))
OCR_TIMEOUT_SECONDS = int(os.environ.get("REG_ASSISTANT_OCR_TIMEOUT", "900"))
CORPUS_CACHE_VERSION = "2026-06-02-ocr-table-v1"
UPLOADED_DOCUMENTS: dict[str, dict[str, Any]] = {}
SESSIONS: dict[str, str] = {}
ADMIN_EMAIL = os.environ.get("REG_ASSISTANT_ADMIN_EMAIL", "xingchi.wang@zf.com").strip().lower()
ADMIN_PASSWORD = os.environ.get("REG_ASSISTANT_ADMIN_PASSWORD", "123456")
LOGIN_CODE = os.environ.get("REG_ASSISTANT_LOGIN_CODE", "zf-test")
LOGIN_CODES = [code.strip() for code in os.environ.get("REG_ASSISTANT_LOGIN_CODES", "").split(",") if code.strip()]
SESSION_COOKIE = "reg_assistant_session"
LLM_API_KEY = (
    os.environ.get("REG_ASSISTANT_LLM_API_KEY")
    or os.environ.get("DASHSCOPE_API_KEY")
    or os.environ.get("DEEPSEEK_API_KEY")
    or ""
).strip()
LLM_BASE_URL = os.environ.get("REG_ASSISTANT_LLM_BASE_URL", "").strip()
LLM_FLASH_MODEL = os.environ.get("REG_ASSISTANT_LLM_FLASH_MODEL", "deepseek-v4-flash").strip()
LLM_PRO_MODEL = os.environ.get("REG_ASSISTANT_LLM_PRO_MODEL", "deepseek-v4-pro").strip()
LLM_TIMEOUT_SECONDS = float(os.environ.get("REG_ASSISTANT_LLM_TIMEOUT", "45"))
LLM_MAX_CONTEXT_CHARS = int(os.environ.get("REG_ASSISTANT_LLM_MAX_CONTEXT_CHARS", "12000"))
LLM_MAX_TOKENS = int(os.environ.get("REG_ASSISTANT_LLM_MAX_TOKENS", "900"))
SEMANTIC_FALLBACK_FLAG = "semantic_fulltext"
SEMANTIC_FALLBACK_PREFIX = "关键词检索不到，已启动 LLM 智能全文理解回答。"

DEFINITION_SENTENCE_RE = re.compile(
    r"(\bmeans\b|\bis defined as\b|\brefers to\b|是指|指的是|的定义|定义为)",
    re.IGNORECASE,
)
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
PARAMETER_VALUE_RE = re.compile(
    r"(?P<value>[-+]?\d+(?:[\s\u00a0]\d{3})*(?:\.\d+)?)\s*(?P<unit>°C|℃|°F|K|percent|%|km/h|mph|mg/kWh|g/kWh|g/km|mm|cm|km|kg|kN|daN|N·m|Nm|kPa|MPa|dB\(A\)|dB|kW|ms|min|lux|bar|ppm|cd|lx|m|g|N|V|A|W|s|h|degrees?|°)(?=$|[^A-Za-z0-9_/])",
    re.I,
)
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


@dataclass
class ParameterHit:
    label: str
    value: str
    unit: str
    context: str
    heading: str
    page: str


@dataclass
class LlmAnswer:
    answer: str
    model: str
    tier: str
    provider: str
    reason: str
    used: bool
    fallback: str = ""


def normalize_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "")
    return value.strip().lower()


def compact_feedback_context(value: Any, limit: int = 12000) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return {"unserializable": str(value)[:1000]}
    if len(encoded) <= limit:
        return value
    return {
        "truncated": True,
        "preview": encoded[:limit],
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def load_users() -> dict[str, Any]:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if USERS_FILE.exists():
        try:
            payload = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {"users": {}}
    else:
        payload = {"users": {}}
    users = payload.setdefault("users", {})
    if ADMIN_EMAIL not in users:
        users[ADMIN_EMAIL] = {
            "email": ADMIN_EMAIL,
            "role": "admin",
            "status": "approved",
            "created_at": now_iso(),
            "approved_at": now_iso(),
        }
        save_users(payload)
    return payload


def save_users(payload: dict[str, Any]) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_user(email: str) -> dict[str, Any] | None:
    return load_users().get("users", {}).get(normalize_email(email))


def load_invite_codes() -> set[str]:
    codes = set(LOGIN_CODES)
    has_invite_file = INVITE_CODES_FILE.exists()
    if LOGIN_CODE and (os.environ.get("REG_ASSISTANT_LOGIN_CODE") or not has_invite_file):
        codes.add(LOGIN_CODE)
    if has_invite_file:
        try:
            payload = json.loads(INVITE_CODES_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = []
        if isinstance(payload, list):
            codes.update(str(code).strip() for code in payload)
        elif isinstance(payload, dict):
            values = payload.get("codes", [])
            if isinstance(values, list):
                codes.update(str(code).strip() for code in values)
    return {code for code in codes if code}


def is_valid_login_code(code: str) -> bool:
    return code.strip() in load_invite_codes()


def list_feedback(limit: int = 100) -> list[dict[str, Any]]:
    if not FEEDBACK_FILE.exists():
        return []
    rows = []
    for line in FEEDBACK_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows[-limit:]))


def log_usage(email: str, action: str, detail: str = "") -> None:
    """Append a usage event for admin auditing (best-effort)."""
    try:
        entry = {
            "at": now_iso(),
            "user": email or "anonymous",
            "action": action,
            "detail": str(detail)[:300],
        }
        with USAGE_LOCK:
            USAGE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with USAGE_LOG_FILE.open("a", encoding="utf-8") as file:
                file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def log_answer_usage(email: str, question: str, llm_answer: LlmAnswer, results: list[dict[str, Any]]) -> None:
    model_label = llm_answer.model if llm_answer.used else llm_answer.reason
    mode = "全文兜底" if is_semantic_fallback_results(results) else "关键词命中"
    preview = re.sub(r"\s+", " ", llm_answer.answer or "").strip()
    detail = f"{mode} | {model_label} | Q: {question} | A: {preview}"
    log_usage(email, "answer", detail)


def list_usage(limit: int = 300) -> list[dict[str, Any]]:
    if not USAGE_LOG_FILE.exists():
        return []
    rows = []
    for line in USAGE_LOG_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows[-limit:]))


def list_archived_documents() -> list[dict[str, Any]]:
    documents = load_upload_index().get("documents", {})
    items = []
    for record in documents.values():
        items.append(
            {
                "doc_id": record.get("doc_id", ""),
                "name": record.get("name") or record.get("filename", ""),
                "filename": record.get("filename", ""),
                "pages": record.get("pages", 0),
                "clauses": record.get("clauses", 0),
                "size_bytes": record.get("size_bytes", 0),
                "uploaded_by": record.get("uploaded_by", []),
                "first_uploaded_at": record.get("first_uploaded_at", ""),
                "last_uploaded_at": record.get("last_uploaded_at", ""),
                "access_count": record.get("access_count", 0),
            }
        )
    items.sort(key=lambda item: (item["name"].lower(), item["first_uploaded_at"]))
    return items


def regulation_name_from_filename(filename: str) -> str:
    name = (filename or "").strip()
    name = re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE)
    name = name.replace("_", " ").strip()
    return name or "未命名法规"


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "email": user.get("email", ""),
        "role": user.get("role", "tester"),
        "status": user.get("status", "pending"),
        "created_at": user.get("created_at", ""),
        "approved_at": user.get("approved_at", ""),
    }


def default_llm_base_url() -> str:
    if os.environ.get("DEEPSEEK_API_KEY") and not os.environ.get("DASHSCOPE_API_KEY"):
        return "https://api.deepseek.com"
    return "https://dashscope.aliyuncs.com/compatible-mode/v1"


def llm_base_url() -> str:
    return LLM_BASE_URL or default_llm_base_url()


def llm_chat_url() -> str:
    base = llm_base_url().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def resolve_chat_url(base_url: str | None) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return llm_chat_url()
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def llm_provider_name() -> str:
    base = llm_base_url().lower()
    if "dashscope" in base or "aliyuncs" in base:
        return "Alibaba Cloud Model Studio"
    if "deepseek" in base:
        return "DeepSeek"
    return "OpenAI-compatible"


def llm_public_config() -> dict[str, Any]:
    return {
        "enabled": bool(LLM_API_KEY),
        "provider": "内置模型",
    }


def select_llm_tier(question: str, results: list[dict[str, Any]]) -> tuple[str, str]:
    text = normalize_text(question)
    total_context = sum(len(str(item.get("text", ""))) for item in results[:8])
    if is_semantic_fallback_results(results):
        return "pro", "keyword miss; full-document semantic fallback"
    high_complexity_terms = (
        "compare",
        "difference",
        "risk",
        "conflict",
        "compliance",
        "interpret",
        "explain",
        "judge",
        "whether",
        "why",
        "差异",
        "风险",
        "冲突",
        "合规",
        "解释",
        "判断",
        "是否",
        "为什么",
        "影响",
        "要求",
    )
    if len(question) >= 120:
        return "pro", "long question"
    if total_context >= 9000:
        return "pro", "large retrieved context"
    if any(term in text for term in high_complexity_terms):
        return "pro", "complex regulatory reasoning"
    return "flash", "direct retrieval answer"


def build_llm_context(results: list[dict[str, Any]]) -> str:
    blocks = []
    budget = LLM_MAX_CONTEXT_CHARS
    for index, item in enumerate(results[:8], start=1):
        source = f"[{index}] {item.get('code', 'document')} | {item.get('heading', '')} | {item.get('page', '')}"
        text = re.sub(r"\s+", " ", str(item.get("text", ""))).strip()
        block = f"{source}\n{text}"
        if len(block) > budget:
            block = block[: max(0, budget - 20)] + "..."
        blocks.append(block)
        budget -= len(block)
        if budget <= 0:
            break
    return "\n\n".join(blocks)


def is_semantic_fallback_results(results: list[dict[str, Any]]) -> bool:
    return any(item.get("retrieval_fallback") == SEMANTIC_FALLBACK_FLAG for item in results)


def build_llm_messages(question: str, results: list[dict[str, Any]]) -> list[dict[str, str]]:
    context = build_llm_context(results)
    semantic_fallback = is_semantic_fallback_results(results)
    system = (
        "You are an internal commercial vehicle regulation assistant. "
        "Answer in Simplified Chinese, using ONLY the provided evidence. "
        "Optimize for the reader's time: be precise and short, never pad. "
        "Format strictly as follows:\n"
        "1) First line: a single-sentence direct answer that leads with the key "
        "value/threshold/conclusion, preserving every number and unit exactly.\n"
        "2) Then at most 2-3 short bullet points of supporting evidence. Each bullet "
        "MUST include: the exact value+unit, the regulation number, the clause/section "
        "or page, and a source citation like [1]. Use the regulation code and page shown "
        "in each evidence header.\n"
        "Do NOT restate the question, do NOT add background, caveats, or filler. "
        "If the evidence does not contain the answer, reply in one sentence that it "
        "was not found in the provided clauses and name the closest related clause. "
        "If the user named a specific regulation, only use evidence from that regulation."
    )
    if semantic_fallback:
        system += (
            f" Keyword retrieval found no direct hit. Start the first line exactly with "
            f"'{SEMANTIC_FALLBACK_PREFIX}' and then give the best answer from the full-text evidence."
        )
    user = f"Question:\n{question}\n\nEvidence:\n{context}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_llm(
    model: str,
    messages: list[dict[str, str]],
    api_key: str | None = None,
    base_url: str | None = None,
) -> str:
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": LLM_MAX_TOKENS,
    }
    request = urlrequest.Request(
        resolve_chat_url(base_url),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key or LLM_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(request, timeout=LLM_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"LLM HTTP {exc.code}: {detail}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"LLM connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("LLM request timed out") from exc

    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("LLM response did not include choices")
    message = choices[0].get("message") or {}
    content = str(message.get("content") or "").strip()
    if not content:
        raise RuntimeError("LLM response was empty")
    return content


def build_llm_answer(question: str, results: list[dict[str, Any]]) -> LlmAnswer:
    tier, reason = select_llm_tier(question, results)
    model = LLM_PRO_MODEL if tier == "pro" else LLM_FLASH_MODEL
    messages = build_llm_messages(question, results)
    answer = call_llm(model, messages)
    return LlmAnswer(answer, model, tier, llm_provider_name(), reason, True)


def synthesize_answer(
    question: str,
    results: list[dict[str, Any]],
    api_key: str | None = None,
    base_url: str | None = None,
) -> LlmAnswer:
    retrieval_answer = build_retrieval_answer(question, results)
    semantic_fallback = is_semantic_fallback_results(results)
    effective_key = api_key or LLM_API_KEY
    if not effective_key:
        return LlmAnswer(retrieval_answer, "local-rules", "local", "Local retrieval", "LLM API key not configured", False)
    if not results:
        return LlmAnswer(retrieval_answer, "local-rules", "local", "Local retrieval", "no retrieved evidence", False)
    tier, reason = select_llm_tier(question, results)
    model = LLM_PRO_MODEL if tier == "pro" else LLM_FLASH_MODEL
    messages = build_llm_messages(question, results)
    try:
        answer = call_llm(model, messages, api_key=api_key, base_url=base_url)
        if semantic_fallback and not answer.startswith(SEMANTIC_FALLBACK_PREFIX):
            answer = f"{SEMANTIC_FALLBACK_PREFIX}\n{answer}"
        return LlmAnswer(answer, model, tier, llm_provider_name(), reason, True)
    except Exception as exc:
        first_error = str(exc)
        if tier == "flash" and LLM_PRO_MODEL and LLM_PRO_MODEL != LLM_FLASH_MODEL:
            try:
                answer = call_llm(LLM_PRO_MODEL, messages, api_key=api_key, base_url=base_url)
                if semantic_fallback and not answer.startswith(SEMANTIC_FALLBACK_PREFIX):
                    answer = f"{SEMANTIC_FALLBACK_PREFIX}\n{answer}"
                return LlmAnswer(
                    answer,
                    LLM_PRO_MODEL,
                    "pro",
                    llm_provider_name(),
                    "flash failed; retried pro",
                    True,
                    first_error,
                )
            except Exception as pro_exc:
                first_error = f"{first_error}; pro fallback failed: {pro_exc}"
        return LlmAnswer(retrieval_answer, "local-rules", "local", "Local retrieval", "LLM failed; used local answer", False, first_error)


def clean_pdf_page_text(text: str) -> str:
    return "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())


def read_pdf_text_pages(path: Path, source: str = "pypdf") -> list[dict[str, Any]]:
    try:
        reader = PdfReader(str(path), strict=False)
        page_list = list(reader.pages)
    except Exception:
        # Malformed/truncated PDF (e.g. "Stream has ended unexpectedly").
        # Return nothing so the caller can fall back to OCR/repair.
        return []
    pages: list[dict[str, Any]] = []
    for index, page in enumerate(page_list, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            # One broken page should not abort the whole document.
            text = ""
        cleaned = clean_pdf_page_text(text)
        pages.append({"page": index, "text": cleaned, "text_source": source, "text_chars": len(cleaned)})
    return pages


def pdf_extraction_summary(pages: list[dict[str, Any]]) -> dict[str, Any]:
    page_count = len(pages)
    text_chars = [int(page.get("text_chars", len(str(page.get("text", ""))))) for page in pages]
    low_text_pages = [int(page.get("page", index + 1)) for index, page in enumerate(pages) if text_chars[index] < OCR_LOW_TEXT_PAGE_CHARS]
    sources = {str(page.get("text_source", "pypdf")) for page in pages if str(page.get("text", "")).strip()}
    if not page_count:
        method = "pypdf"
    elif not sources:
        method = "empty"
    elif sources == {"ocr"}:
        method = "ocr"
    elif "ocr" in sources:
        method = "mixed"
    else:
        method = "pypdf"
    return {
        "extract_method": method,
        "pages": page_count,
        "total_text_chars": sum(text_chars),
        "text_pages": page_count - len(low_text_pages),
        "empty_pages": len(low_text_pages),
        "text_coverage": round((page_count - len(low_text_pages)) / page_count, 3) if page_count else 0.0,
        "ocr_pages": [int(page.get("page", index + 1)) for index, page in enumerate(pages) if page.get("text_source") == "ocr"],
    }


def should_ocr_pdf(pages: list[dict[str, Any]]) -> bool:
    if not OCR_ENABLED or not pages:
        return False
    stats = pdf_extraction_summary(pages)
    if stats["empty_pages"] <= 0:
        return False
    low_text_ratio = stats["empty_pages"] / max(1, stats["pages"])
    average_chars = stats["total_text_chars"] / max(1, stats["pages"])
    return low_text_ratio >= OCR_TRIGGER_LOW_TEXT_RATIO or average_chars < OCR_TRIGGER_TOTAL_CHARS_PER_PAGE


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_under_path(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        value = resolved.relative_to(ROOT)
    except ValueError:
        value = path
    return str(value).replace("\\", "/")


def run_ocr_pdf(path: Path, langs: str | None = None) -> Path | None:
    executable = shutil.which("ocrmypdf")
    if not executable:
        return None

    langs = (langs or OCR_LANGS).strip() or OCR_LANGS
    lang_slug = re.sub(r"[^A-Za-z0-9_.+-]+", "_", langs)
    use_persistent_cache = is_under_path(path, REGULATION_CORPUS)
    if use_persistent_cache:
        OCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        digest = file_sha256(path)
        output_path = OCR_CACHE_DIR / f"{digest[:20]}-{lang_slug}.pdf"
        if output_path.exists() and output_path.stat().st_size > 0:
            return output_path
    else:
        output_path = path.with_name(f"{path.stem}.{lang_slug}.ocr.pdf")

    command = [
        executable,
        "--skip-text",
        "--deskew",
        "--rotate-pages",
        "--language",
        langs,
        str(path),
        str(output_path),
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=OCR_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            pass
        return None
    return output_path


def merge_pdf_text_pages(original: list[dict[str, Any]], ocr_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    ocr_by_page = {int(page.get("page", 0)): page for page in ocr_pages}
    for page in original:
        page_no = int(page.get("page", len(merged) + 1))
        ocr_page = ocr_by_page.get(page_no)
        original_chars = int(page.get("text_chars", len(str(page.get("text", "")))))
        ocr_chars = int(ocr_page.get("text_chars", 0)) if ocr_page else 0
        if ocr_page and original_chars < OCR_LOW_TEXT_PAGE_CHARS and ocr_chars > original_chars:
            merged.append({**ocr_page, "text_source": "ocr", "text_chars": ocr_chars})
        else:
            merged.append({**page, "text_source": page.get("text_source", "pypdf"), "text_chars": original_chars})
    return merged


def extract_pdf(path: Path, langs: str | None = None) -> list[dict[str, Any]]:
    pages = read_pdf_text_pages(path, "pypdf")
    # OCR when text is sparse/scanned, OR when pypdf could not read the file at
    # all (corrupt/truncated PDF) — ocrmypdf runs Ghostscript which often repairs.
    needs_ocr = should_ocr_pdf(pages) or (OCR_ENABLED and not pages)
    if not needs_ocr:
        return pages
    ocr_path = run_ocr_pdf(path, langs=langs)
    if not ocr_path:
        return pages
    try:
        ocr_pages = read_pdf_text_pages(ocr_path, "ocr")
    except Exception:
        return pages
    if not pages:
        return ocr_pages
    if sum(int(page.get("text_chars", 0)) for page in ocr_pages) <= sum(int(page.get("text_chars", 0)) for page in pages):
        return pages
    return merge_pdf_text_pages(pages, ocr_pages)


DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_docx(path: Path) -> list[dict[str, Any]]:
    """Extract text from a .docx (Office Open XML) file using only stdlib."""
    try:
        with zipfile.ZipFile(str(path)) as archive:
            xml_bytes = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile, OSError) as exc:
        raise ValueError("无法读取 Word 文档（文件可能损坏或非 .docx 格式）。") from exc
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError("Word 文档内容解析失败。") from exc

    lines: list[str] = []
    for paragraph in root.iter(f"{DOCX_NS}p"):
        parts: list[str] = []
        for node in paragraph.iter():
            tag = node.tag
            if tag == f"{DOCX_NS}t":
                parts.append(node.text or "")
            elif tag == f"{DOCX_NS}tab":
                parts.append("\t")
            elif tag in (f"{DOCX_NS}br", f"{DOCX_NS}cr"):
                parts.append("\n")
        text = "".join(parts).strip()
        if text:
            lines.append(text)
    body = "\n".join(lines)
    if not body.strip():
        raise ValueError("Word 文档没有可提取的文本内容。")
    return [{"page": 1, "text": body, "text_source": "docx", "text_chars": len(body)}]


def extract_txt(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    text = ""
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    cleaned = clean_pdf_page_text(text)
    if not cleaned.strip():
        raise ValueError("文本文件为空或无法解码。")
    return [{"page": 1, "text": cleaned, "text_source": "txt", "text_chars": len(cleaned)}]


SUPPORTED_UPLOAD_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


def extract_document(path: Path, filename: str, langs: str | None = None) -> list[dict[str, Any]]:
    """Dispatch to the right parser based on the original file extension."""
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".docx":
        return extract_docx(path)
    if suffix in {".txt", ".md"}:
        return extract_txt(path)
    if suffix == ".doc":
        raise ValueError("暂不支持旧版 .doc 格式，请用 Word 另存为 .docx 或导出 PDF 后再上传。")
    # default: treat as PDF (covers .pdf and unknown extensions)
    return extract_pdf(path, langs=langs)


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


def _clause_compare_key(clause: Clause) -> str:
    return normalize_text(f"{clause.heading}\n{clause.text[:1200]}")


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

    # Precision first: every left clause is compared against every remaining
    # right clause so we always pick the true best match. We only avoid
    # redundant work that does NOT change the result: normalized keys are
    # computed once per clause (instead of on every pairwise call) and the
    # matcher caches the left-hand sequence while we iterate the right ones.
    right_norm = [_clause_compare_key(right) for right in right_clauses]
    matcher = SequenceMatcher(autojunk=False)

    for left in left_clauses:
        left_norm = _clause_compare_key(left)
        matcher.set_seq2(left_norm)  # cache left; only the right side changes

        best_index = -1
        best_score = 0.0
        for index in range(len(right_clauses)):
            if index in used_right:
                continue
            matcher.set_seq1(right_norm[index])
            # real_quick_ratio() and quick_ratio() are cheap upper bounds on
            # ratio(). If the upper bound cannot beat the current best, skip the
            # expensive exact ratio() entirely. This is precision-identical: the
            # selected best match is exactly the same as the exhaustive scan.
            if matcher.real_quick_ratio() <= best_score:
                continue
            if matcher.quick_ratio() <= best_score:
                continue
            score = matcher.ratio()
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


def build_parameter_matrix(results: list[MatchResult], limit: int = 50) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in results:
        left_hits = extract_parameter_hits(item.left) if item.left else []
        right_hits = extract_parameter_hits(item.right) if item.right else []
        if not left_hits and not right_hits:
            continue

        labels = sorted({hit.label for hit in left_hits + right_hits}, key=parameter_label_order)
        for label in labels:
            left_values = [hit for hit in left_hits if hit.label == label]
            right_values = [hit for hit in right_hits if hit.label == label]
            left_set = {hit.value for hit in left_values}
            right_set = {hit.value for hit in right_values}
            changed = bool(left_set and right_set and left_set != right_set)
            only_one_side = bool(left_set) != bool(right_set)
            if not changed and not only_one_side and item.change_type not in {"阈值/数值变化", "测试方法变化", "适用范围变化"}:
                continue

            rows.append(
                {
                    "parameter": label,
                    "change_type": item.change_type,
                    "risk": item.risk,
                    "score": round(item.score, 3),
                    "changed": changed or only_one_side,
                    "left_values": summarize_parameter_hits(left_values),
                    "right_values": summarize_parameter_hits(right_values),
                    "left_context": left_values[0].context if left_values else "",
                    "right_context": right_values[0].context if right_values else "",
                    "left_location": left_values[0].page if left_values else "",
                    "right_location": right_values[0].page if right_values else "",
                    "left_heading": item.left.heading if item.left else "",
                    "right_heading": item.right.heading if item.right else "",
                }
            )

    rows.sort(key=parameter_row_order, reverse=True)
    return rows[:limit]


def extract_parameter_hits(clause: Clause) -> list[ParameterHit]:
    hits: list[ParameterHit] = []
    seen: set[tuple[str, str, str]] = set()
    for sentence in split_sentences(clause.text):
        for match in PARAMETER_VALUE_RE.finditer(sentence):
            raw_value = re.sub(r"[\s\u00a0]+", " ", match.group("value")).strip()
            unit = normalize_unit(match.group("unit") or "")
            if not unit:
                continue
            label = infer_parameter_label(sentence, unit)
            value = f"{raw_value} {unit}".strip()
            key = (label, value.lower(), sentence[:80].lower())
            if key in seen:
                continue
            seen.add(key)
            hits.append(
                ParameterHit(
                    label=label,
                    value=value,
                    unit=unit,
                    context=excerpt(sentence, 260),
                    heading=clause.heading,
                    page=f"P{clause.start_page}-{clause.end_page}",
                )
            )
            if len(hits) >= 8:
                return hits
    return hits


def summarize_parameter_hits(hits: list[ParameterHit]) -> str:
    values = []
    for hit in hits:
        if hit.value not in values:
            values.append(hit.value)
    return "；".join(values[:8])


def normalize_unit(unit: str) -> str:
    unit = unit.strip()
    replacements = {"degrees": "degree", "percent": "%", "℃": "°C", "\u2103": "°C"}
    return replacements.get(unit.lower(), unit)


def infer_parameter_label(sentence: str, unit: str) -> str:
    lowered = sentence.lower()
    unit_lower = unit.lower()
    if unit_lower in {"°c", "°f", "k"}:
        return "温度"
    if unit_lower in {"km/h", "mph"}:
        return "速度"
    if unit_lower in {"kpa", "mpa", "bar"}:
        return "压力"
    if unit_lower in {"kn", "dan", "n"}:
        return "载荷/力"
    if unit_lower in {"mm", "cm", "m", "km"}:
        if "distance" in lowered or "stopping" in lowered or "距离" in sentence:
            return "距离"
        return "尺寸/距离"
    if unit_lower in {"db", "db(a)"}:
        return "噪声"
    if unit_lower in {"g/km", "g/kwh", "mg/kwh", "ppm"}:
        return "排放"
    if unit_lower in {"degree", "°"}:
        return "角度"
    if unit_lower in {"lx", "lux", "cd"}:
        return "照明/光学"
    if unit_lower in {"v", "a", "w", "kw"}:
        return "电气参数"
    if unit_lower == "%":
        return "比例/百分比"
    if unit_lower in {"s", "ms", "min", "h"}:
        return "时间"
    if "temperature" in lowered or "温度" in sentence:
        return "温度"
    if "speed" in lowered or "velocity" in lowered or "速度" in sentence:
        return "速度"
    if "pressure" in lowered or "压力" in sentence:
        return "压力"
    if "force" in lowered or "load" in lowered or "载荷" in sentence:
        return "载荷/力"
    if "noise" in lowered or "sound" in lowered or "噪声" in sentence:
        return "噪声"
    if "emission" in lowered or "排放" in sentence:
        return "排放"
    if "angle" in lowered or "角度" in sentence:
        return "角度"
    if "luminous" in lowered or "illuminance" in lowered or "照度" in sentence:
        return "照明/光学"
    return "其他数值"


def parameter_label_order(label: str) -> int:
    order = {
        "载荷/力": 10,
        "速度": 9,
        "温度": 8,
        "压力": 7,
        "尺寸/距离": 6,
        "距离": 6,
        "时间": 5,
        "角度": 4,
        "照明/光学": 3,
        "噪声": 2,
        "排放": 2,
    }
    return order.get(label, 0)


def parameter_row_order(row: dict[str, Any]) -> tuple[int, int, int, float]:
    return (
        1 if row["changed"] else 0,
        risk_order(str(row["risk"])),
        parameter_label_order(str(row["parameter"])),
        float(row["score"]),
    )


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
        if parsed.path == "/api/session":
            self.handle_session()
            return
        if parsed.path == "/healthz":
            self.send_json({"ok": True})
            return
        if parsed.path == "/api/admin/users":
            if not self.require_admin():
                return
            self.send_json({"users": list(load_users().get("users", {}).values())})
            return
        if parsed.path == "/api/admin/feedback":
            if not self.require_admin():
                return
            self.send_json({"feedback": list_feedback()})
            return
        if parsed.path == "/api/admin/usage":
            if not self.require_admin():
                return
            self.send_json({"usage": list_usage()})
            return
        if parsed.path == "/api/admin/uploads":
            if not self.require_admin():
                return
            self.send_json({"documents": list_archived_documents()})
            return
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
        if self.path == "/api/login":
            self.handle_login()
            return
        if self.path == "/api/logout":
            self.handle_logout()
            return
        if self.path == "/api/admin/approve":
            if not self.require_admin():
                return
            self.handle_admin_approve()
            return
        if not self.require_user():
            return
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
            user = self.current_user()
            left_raw = left_file.file.read()
            right_raw = right_file.file.read()
            left_suffix = Path(left_file.filename or "").suffix.lower() or ".pdf"
            right_suffix = Path(right_file.filename or "").suffix.lower() or ".pdf"
            with TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                left_path = tmp_dir / f"left{left_suffix}"
                right_path = tmp_dir / f"right{right_suffix}"
                left_path.write_bytes(left_raw)
                right_path.write_bytes(right_raw)

                left_pages = extract_document(left_path, left_file.filename or f"left{left_suffix}", langs=UPLOAD_OCR_LANGS)
                right_pages = extract_document(right_path, right_file.filename or f"right{right_suffix}", langs=UPLOAD_OCR_LANGS)
                left_clauses = split_clauses(left_pages)
                right_clauses = split_clauses(right_pages)
                results = compare_clauses(left_clauses, right_clauses)

                user_email = user["email"] if user else ""
                try:
                    archive_document(left_raw, left_file.filename, user_email, left_pages, left_clauses)
                    archive_document(right_raw, right_file.filename, user_email, right_pages, right_clauses)
                except Exception:
                    pass

                log_usage(
                    user_email,
                    "compare",
                    f"{regulation_name_from_filename(left_file.filename)} ↔ {regulation_name_from_filename(right_file.filename)}",
                )

                self.send_json(
                    {
                        "left": document_summary(left_file.filename, left_pages, left_clauses),
                        "right": document_summary(right_file.filename, right_pages, right_clauses),
                        "conclusion": build_compare_conclusion(left_file.filename, right_file.filename, results),
                        "parameter_matrix": build_parameter_matrix(results),
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
            use_llm = bool(payload.get("use_llm", True))
            user_api_key = str(payload.get("api_key", "")).strip() or None
            user_base_url = str(payload.get("base_url", "")).strip() or None
            if len(question) < 2:
                self.send_json({"error": "请输入要查询的问题。"}, status=400)
                return
            if doc_id:
                if get_uploaded_document(doc_id) is None:
                    self.send_json({"error": "未找到已上传的法规文档，请重新上传。"}, status=404)
                    return
                results = search_uploaded_document(question, doc_id)
            else:
                results = search_corpus(question)
            llm_answer = synthesize_answer(question, results, api_key=user_api_key, base_url=user_base_url) if use_llm else LlmAnswer(
                build_retrieval_answer(question, results),
                "local-rules",
                "local",
                "Local retrieval",
                "LLM disabled by request",
                False,
            )
            user = self.current_user()
            user_email = user["email"] if user else ""
            log_usage(user_email, "ask", question)
            log_answer_usage(user_email, question, llm_answer, results)
            self.send_json(
                {
                    "question": question,
                    "answer": llm_answer.answer,
                    "llm": asdict(llm_answer),
                    "results": results,
                }
            )
        except Exception as exc:
            self.send_json({"error": f"检索失败：{html.escape(str(exc))}"}, status=500)

    def handle_session(self) -> None:
        user = self.current_user()
        self.send_json({"user": public_user(user) if user else None, "admin_email": ADMIN_EMAIL, "llm": llm_public_config()})

    def handle_login(self) -> None:
        content_length = int(self.headers.get("content-length", "0"))
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            email = normalize_email(str(payload.get("email", "")))
            code = str(payload.get("code", ""))
            if "@" not in email:
                self.send_json({"error": "请输入公司邮箱。"}, status=400)
                return
            if email == ADMIN_EMAIL:
                if code != ADMIN_PASSWORD:
                    self.send_json({"error": "管理员密码不正确。"}, status=403)
                    return
            elif not is_valid_login_code(code):
                self.send_json({"error": "测试邀请码不正确，请联系管理员。"}, status=403)
                return

            users_payload = load_users()
            users = users_payload["users"]
            user = users.get(email)
            now = now_iso()
            if not user:
                user = {
                    "email": email,
                    "role": "tester",
                    "status": "approved",
                    "created_at": now,
                    "approved_at": now,
                }
                users[email] = user

            if email == ADMIN_EMAIL:
                user["role"] = "admin"
            if user.get("status") != "approved":
                user["status"] = "approved"
                user["approved_at"] = user.get("approved_at") or now
            save_users(users_payload)

            token = secrets.token_urlsafe(32)
            SESSIONS[token] = email
            log_usage(email, "login", "管理员" if user.get("role") == "admin" else "测试用户")
            self.send_json(
                {"ok": True, "user": public_user(user)},
                headers={"Set-Cookie": f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax"},
            )
        except Exception as exc:
            self.send_json({"error": f"登录失败：{html.escape(str(exc))}"}, status=500)

    def handle_logout(self) -> None:
        token = self.session_token()
        if token:
            SESSIONS.pop(token, None)
        self.send_json({"ok": True}, headers={"Set-Cookie": f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})

    def handle_admin_approve(self) -> None:
        content_length = int(self.headers.get("content-length", "0"))
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            email = normalize_email(str(payload.get("email", "")))
            users_payload = load_users()
            user = users_payload["users"].get(email)
            if not user:
                self.send_json({"error": "未找到该用户。"}, status=404)
                return
            user["status"] = "approved"
            user["approved_at"] = now_iso()
            user["approved_by"] = self.current_user()["email"]
            save_users(users_payload)
            self.send_json({"ok": True, "user": public_user(user)})
        except Exception as exc:
            self.send_json({"error": f"审批失败：{html.escape(str(exc))}"}, status=500)

    def handle_feedback(self) -> None:
        content_length = int(self.headers.get("content-length", "0"))
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            user = self.current_user()
            feedback = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "user": (user or {}).get("email", "anonymous"),
                "type": str(payload.get("type", "general")).strip()[:80],
                "message": str(payload.get("message", "")).strip()[:3000],
                "contact": str(payload.get("contact", "")).strip()[:160],
                "context": compact_feedback_context(payload.get("context", {})),
            }
            if not feedback["message"]:
                self.send_json({"error": "请填写反馈内容。"}, status=400)
                return
            FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
            with FEEDBACK_FILE.open("a", encoding="utf-8") as file:
                file.write(json.dumps(feedback, ensure_ascii=False) + "\n")
            self.send_json({"ok": True, "message": "反馈已记录并提交到管理员后台，感谢你的反馈！"})
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
            raw = uploaded.file.read()
            user = self.current_user()
            suffix = Path(uploaded.filename or "").suffix.lower() or ".pdf"
            if suffix not in SUPPORTED_UPLOAD_SUFFIXES and suffix != ".doc":
                self.send_json({"error": "暂不支持该文件格式，请上传 PDF、Word(.docx) 或 .txt 文件。"}, status=400)
                return
            with TemporaryDirectory() as tmp:
                doc_path = Path(tmp) / f"document{suffix}"
                doc_path.write_bytes(raw)
                pages = extract_document(doc_path, uploaded.filename or f"document{suffix}", langs=UPLOAD_OCR_LANGS)
                clauses = split_clauses(pages)
            if not pages or not any(str(page.get("text", "")).strip() for page in pages):
                self.send_json(
                    {"error": "未能从文件中提取到文本，可能是加密、纯图片且 OCR 质量过低，请提供可复制文本的 PDF/Word。"},
                    status=422,
                )
                return
            record = archive_document(raw, uploaded.filename, user["email"] if user else "", pages, clauses)
            doc_id = record["doc_id"]
            UPLOADED_DOCUMENTS[doc_id] = {
                "filename": record["filename"],
                "pages": record["pages"],
                "clauses": record["clauses"],
                "chunks": record["chunks"],
                "extraction": record.get("extraction", {}),
            }
            log_usage(
                user["email"] if user else "",
                "upload",
                f"{regulation_name_from_filename(uploaded.filename)}（{record['pages']}页）",
            )
            self.send_json(
                {
                    "doc_id": doc_id,
                    "filename": record["filename"],
                    "pages": record["pages"],
                    "clauses": record["clauses"],
                    "extraction": record.get("extraction", {}),
                    "cached": record.get("cached", False),
                }
            )
        except Exception as exc:
            self.send_json({"error": f"上传解析失败：{html.escape(str(exc))}"}, status=500)

    def session_token(self) -> str:
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            name, _, value = part.strip().partition("=")
            if name == SESSION_COOKIE:
                return value
        return ""

    def current_user(self) -> dict[str, Any] | None:
        email = SESSIONS.get(self.session_token())
        if not email:
            return None
        user = get_user(email)
        if not user or user.get("status") != "approved":
            return None
        return user

    def require_user(self) -> bool:
        if self.current_user():
            return True
        self.send_json({"error": "请先登录。"}, status=401)
        return False

    def require_admin(self) -> bool:
        user = self.current_user()
        if user and user.get("role") == "admin":
            return True
        self.send_json({"error": "需要管理员权限。"}, status=403)
        return False

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

    def send_json(self, payload: dict[str, Any], status: int = 200, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
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
    document = get_uploaded_document(doc_id)
    if not document:
        return []
    if is_summary_question(question):
        return summarize_uploaded_document_chunks(document, limit)
    results = search_chunks(question, document["chunks"], limit)
    if results:
        return results
    # Generic uploaded-document questions such as "总结法规" often have no
    # overlapping technical keyword. Fall back to representative clauses instead
    # of sending the user back to keyword guessing.
    if wants_uploaded_document_overview(question):
        return summarize_uploaded_document_chunks(document, limit)
    return semantic_uploaded_document_fallback_chunks(document, limit)


SUMMARY_QUERY_RE = re.compile(
    r"(总结|概括|概要|主要内容|讲什么|这份法规|这个法规|整篇|全文|overview|summary|summarize|main points|what is this)",
    re.I,
)
OVERVIEW_QUERY_RE = re.compile(
    r"(法规|文档|文件|pdf|document|regulation|standard)",
    re.I,
)
SUMMARY_HEADING_RE = re.compile(
    r"\b(scope|application|definitions?|requirements?|specifications?|general|test procedure|conformity|annex)\b|"
    r"(范围|适用|定义|要求|规范|试验|测试|一致性|附录)",
    re.I,
)


def is_summary_question(question: str) -> bool:
    return bool(SUMMARY_QUERY_RE.search(question or ""))


def wants_uploaded_document_overview(question: str) -> bool:
    text = question or ""
    return bool(OVERVIEW_QUERY_RE.search(text)) and len(tokenize(text)) <= 8


def summarize_uploaded_document_chunks(document: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    chunks = document.get("chunks", [])
    if not chunks:
        return []
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, chunk in enumerate(chunks):
        text = str(chunk.get("text", ""))
        heading = str(chunk.get("heading", ""))
        combined = f"{heading} {text}"
        score = 0.0
        if index < 5:
            score += 1.8 - index * 0.15
        if SUMMARY_HEADING_RE.search(combined):
            score += 1.2
        if re.search(r"\bshall\b|应当|应|必须|不得", text, re.I):
            score += 0.9
        if extract_answer_numbers(text):
            score += 0.4
        if len(text) < 120:
            score -= 0.4
        if chunk_is_junk(chunk):
            score -= 1.5
        scored.append((score, index, chunk))

    selected: list[dict[str, Any]] = []
    seen_headings: set[str] = set()
    for score, _index, chunk in sorted(scored, key=lambda item: item[0], reverse=True):
        heading_key = normalize_text(str(chunk.get("heading", "")))[:80]
        if heading_key in seen_headings and len(selected) >= max(3, limit // 2):
            continue
        seen_headings.add(heading_key)
        item = {key: value for key, value in chunk.items() if key not in ("tokens", "reg_codes", "is_junk", "text_lower")}
        item["score"] = round(score, 3)
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def semantic_uploaded_document_fallback_chunks(document: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    selected = summarize_uploaded_document_chunks(document, limit)
    for item in selected:
        item["retrieval_fallback"] = SEMANTIC_FALLBACK_FLAG
        item["retrieval_note"] = "keyword_search_empty; representative_fulltext_context"
    return selected


def load_upload_index() -> dict[str, Any]:
    if UPLOAD_INDEX_FILE.exists():
        try:
            data = json.loads(UPLOAD_INDEX_FILE.read_text(encoding="utf-8"))
            data.setdefault("documents", {})
            return data
        except Exception:
            return {"documents": {}}
    return {"documents": {}}


def save_upload_index(index: dict[str, Any]) -> None:
    UPLOAD_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = UPLOAD_INDEX_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(UPLOAD_INDEX_FILE)


def rehydrate_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for chunk in chunks:
        chunk["tokens"] = set(
            tokenize(f"{chunk.get('text', '')} {chunk.get('code', '')} {chunk.get('title', '')}")
        )
    return chunks


def get_uploaded_document(doc_id: str) -> dict[str, Any] | None:
    document = UPLOADED_DOCUMENTS.get(doc_id)
    if document:
        return document
    record = load_upload_index().get("documents", {}).get(doc_id)
    if not record:
        return None
    cache_path = ROOT / record.get("cache_path", "")
    if not cache_path.exists():
        return None
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    document = {
        "filename": record.get("filename", ""),
        "pages": record.get("pages", 0),
        "clauses": record.get("clauses", 0),
        "chunks": rehydrate_chunks(cached.get("chunks", [])),
        "extraction": record.get("extraction", cached.get("extraction", {})),
    }
    UPLOADED_DOCUMENTS[doc_id] = document
    return document


def archive_document(
    raw: bytes,
    filename: str,
    user_email: str,
    pages: list[dict[str, Any]],
    clauses: list[Clause],
) -> dict[str, Any]:
    """Persist an uploaded PDF and its parsed chunks; dedup by content hash."""
    filename = (filename or "uploaded.pdf").strip() or "uploaded.pdf"
    content_hash = hashlib.sha256(raw).hexdigest()
    doc_id = content_hash[:16]
    timestamp = now_iso()

    with ARCHIVE_LOCK:
        index = load_upload_index()
        documents = index["documents"]
        record = documents.get(doc_id)
        cache_path = UPLOAD_CACHE_DIR / f"{doc_id}.json"

        if record and cache_path.exists():
            record["last_uploaded_at"] = timestamp
            record["access_count"] = record.get("access_count", 0) + 1
            filenames = set(record.get("filenames", []))
            filenames.add(filename)
            record["filenames"] = sorted(filenames)
            if user_email:
                uploaders = set(record.get("uploaded_by", []))
                uploaders.add(user_email)
                record["uploaded_by"] = sorted(uploaders)
            save_upload_index(index)
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            chunks = rehydrate_chunks(cached.get("chunks", []))
            return {
                "doc_id": doc_id,
                "filename": filename,
                "pages": record.get("pages", len(pages)),
                "clauses": record.get("clauses", len(clauses)),
                "chunks": chunks,
                "extraction": record.get("extraction", cached.get("extraction", {})),
                "cached": True,
            }

        UPLOAD_FILES_DIR.mkdir(parents=True, exist_ok=True)
        UPLOAD_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        stored_suffix = Path(filename).suffix.lower()
        if stored_suffix not in SUPPORTED_UPLOAD_SUFFIXES:
            stored_suffix = ".pdf"
        pdf_path = UPLOAD_FILES_DIR / f"{doc_id}{stored_suffix}"
        if not pdf_path.exists():
            pdf_path.write_bytes(raw)
        chunks = chunks_from_clauses(clauses, filename, doc_id)
        serializable = [{key: value for key, value in chunk.items() if key != "tokens"} for chunk in chunks]
        extraction = pdf_extraction_summary(pages)
        cache_path.write_text(json.dumps({"chunks": serializable, "extraction": extraction}, ensure_ascii=False), encoding="utf-8")

        documents[doc_id] = {
            "doc_id": doc_id,
            "content_sha256": content_hash,
            "name": regulation_name_from_filename(filename),
            "filename": filename,
            "filenames": [filename],
            "size_bytes": len(raw),
            "pages": len(pages),
            "clauses": len(clauses),
            "chunk_count": len(chunks),
            "extraction": extraction,
            "uploaded_by": [user_email] if user_email else [],
            "first_uploaded_at": timestamp,
            "last_uploaded_at": timestamp,
            "access_count": 1,
            "pdf_path": str(pdf_path.relative_to(ROOT)).replace("\\", "/"),
            "cache_path": str(cache_path.relative_to(ROOT)).replace("\\", "/"),
        }
        save_upload_index(index)
        return {
            "doc_id": doc_id,
            "filename": filename,
            "pages": len(pages),
            "clauses": len(clauses),
            "chunks": chunks,
            "extraction": extraction,
            "cached": False,
        }


JUNK_CHUNK_RE = re.compile(
    r"approval mark|distinguishing number|trade name or mark|maximum format|"
    r"communication|approval (?:granted|extended|refused|withdrawn)|"
    r"production definitively discontinued|table of contents|arrangement of the approval|"
    r"name and address of (?:the )?(?:technical service|administrative|manufacturer)|目录",
    re.I,
)
MANAGEMENT_REQUIREMENT_QUERY_RE = re.compile(
    r"\b(?:csms|sums|cyber security|software update|management system|process|"
    r"manufacturer|shall|requirements?|specifications?)\b",
    re.I,
)
CORE_MANAGEMENT_REQUIREMENT_RE = re.compile(
    r"\b7\.(?:1|2|3|4)(?:\.\d+)*\b.{0,320}\b(?:requirements?|specifications?|processes?|manufacturer|shall)\b",
    re.I,
)
DECLARATION_TEMPLATE_RE = re.compile(
    r"\b(?:model of .*declaration|declaration of compliance|certificate of compliance)\b",
    re.I,
)


def extract_reg_codes(text: str) -> set[str]:
    """Pull canonical regulation identifiers (FMVSS123 / UNR13 / GB12676) from text."""
    up = (text or "").upper()
    codes: set[str] = set()
    for match in re.finditer(r"FMVSS\s*0*(\d{1,3})", up):
        codes.add(f"FMVSS{int(match.group(1))}")
    for match in re.finditer(r"49\s*CFR\s*571\.0*(\d{1,3})", up):
        codes.add(f"FMVSS{int(match.group(1))}")
    for match in re.finditer(r"(?:UN\s*R|ECE\s*R|UNECE\s*R|UN\s*REGULATION\s*NO\.?\s*)0*(\d{1,3})", up):
        codes.add(f"UNR{int(match.group(1))}")
    for match in re.finditer(r"(?<![A-Z])R\s*0*(\d{1,3})\b", up):
        codes.add(f"UNR{int(match.group(1))}")
    for match in re.finditer(r"GB(?:/T)?\s*0*(\d{3,5})", up):
        codes.add(f"GB{int(match.group(1))}")
    return codes


def chunk_reg_codes(chunk: dict[str, Any]) -> set[str]:
    cached = chunk.get("reg_codes")
    if cached is None:
        cached = extract_reg_codes(f"{chunk.get('code', '')} {chunk.get('title', '')}")
        chunk["reg_codes"] = cached
    return cached


def chunk_is_junk(chunk: dict[str, Any]) -> bool:
    cached = chunk.get("is_junk")
    if cached is None:
        head = f"{chunk.get('heading', '')} {chunk.get('text', '')[:200]}"
        cached = bool(JUNK_CHUNK_RE.search(head))
        chunk["is_junk"] = cached
    return cached


def search_chunks(question: str, chunks: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    query_tokens = set(tokenize(question))
    if not query_tokens:
        return []
    query_codes = extract_reg_codes(question)
    expanded_question = expand_query_terms(question.lower())
    wants_management_requirements = bool(MANAGEMENT_REQUIREMENT_QUERY_RE.search(expanded_question))
    query_len_factor = len(query_tokens) ** 0.5
    scored: list[tuple[float, bool, dict[str, Any]]] = []
    for chunk in chunks:
        chunk_tokens = chunk["tokens"]
        overlap = query_tokens & chunk_tokens
        code_match = bool(query_codes and (chunk_reg_codes(chunk) & query_codes))
        if not overlap and not code_match:
            continue
        score = len(overlap) / (query_len_factor * len(chunk_tokens) ** 0.35) if overlap else 0.0
        text_lower = chunk.get("text_lower")
        if text_lower is None:
            text_lower = chunk["text"].lower()
            chunk["text_lower"] = text_lower
        if any(token in text_lower for token in query_tokens):
            score += 0.15
        heading_lower = str(chunk.get("heading", "")).lower()
        head_and_text = f"{heading_lower} {text_lower}"
        is_declaration_template = False
        if wants_management_requirements:
            has_subclause_number = bool(re.search(r"\b7\.(?:1|2|3|4)\.\d+\b", head_and_text))
            is_core_management_requirement = has_subclause_number and bool(CORE_MANAGEMENT_REQUIREMENT_RE.search(head_and_text))
            if is_core_management_requirement:
                score += 1.1
            if not is_core_management_requirement and DECLARATION_TEMPLATE_RE.search(f"{heading_lower} {text_lower[:500]}"):
                is_declaration_template = True
                score *= 0.55
        # Push boilerplate (approval forms, distinguishing numbers, TOC) down so
        # it stops crowding out the real requirement clauses.
        if chunk_is_junk(chunk):
            score *= 0.2
        # When the user names a regulation, that regulation's clauses must win.
        if code_match:
            score += 5.0
        if wants_management_requirements and is_declaration_template:
            score -= 0.8
        scored.append((score, code_match, chunk))

    # If the question specified a regulation number and we matched it, restrict
    # results to that regulation so a different reg can never rank ahead.
    if query_codes and any(code_match for _, code_match, _ in scored):
        scored = [entry for entry in scored if entry[1]]

    results = []
    for score, _code_match, chunk in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]:
        item = {key: value for key, value in chunk.items() if key not in ("tokens", "reg_codes", "is_junk", "text_lower")}
        item["score"] = round(score, 3)
        results.append(item)
    return results


def build_retrieval_answer(question: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return "没有在本地法规库中找到明显相关条款。请换一个关键词，或补充完整法规 PDF。"
    semantic_fallback = is_semantic_fallback_results(results)
    if is_summary_question(question):
        lines = ["这份法规的可检索内容摘要如下："]
        for result in results[:5]:
            text = compact_space(str(result.get("text", "")))
            sentences = split_sentences(text)
            summary_sentence = sentences[0] if sentences else text[:220]
            if len(summary_sentence) > 240:
                summary_sentence = summary_sentence[:240] + "..."
            lines.append(
                f"- {result.get('heading', result.get('code', '文档'))}，位置 {result.get('page', '-')}: {summary_sentence}"
            )
        lines.append("建议下一步直接问具体参数、适用范围、测试方法或某个条款号，我会返回更精确的原文证据。")
        answer = "\n".join(lines)
        return f"{SEMANTIC_FALLBACK_PREFIX}\n{answer}" if semantic_fallback else answer
    question_tokens = set(tokenize(question))
    intent = detect_question_intent(question)
    wants_value = bool(intent) or any(term in question for term in ("多少", "几", "限值", "阈值", "数值", "要求是", "应为", "应不"))
    best_sentences = []
    for result in results[:12]:
        for sentence in split_sentences(result["text"]):
            sentence_tokens = set(tokenize(sentence))
            overlap = len(question_tokens & sentence_tokens)
            numbers = extract_answer_numbers(sentence)
            unit_bonus = answer_unit_bonus(numbers, intent)
            if intent and not unit_bonus and not sentence_matches_intent(sentence, intent):
                continue
            score = overlap * 2 + unit_bonus + len(numbers) * 0.4
            # A value question rarely wants a definition sentence ("X means ...",
            # "...是指..."). Down-weight definitions that carry no number so the
            # actual numeric requirement surfaces first.
            if wants_value and not numbers and DEFINITION_SENTENCE_RE.search(sentence):
                score -= 3.0
            if overlap or numbers:
                best_sentences.append((score, sentence, numbers, result, unit_bonus))

    best_sentences.sort(key=lambda item: item[0], reverse=True)
    if intent and any(item[4] >= 5 for item in best_sentences):
        best_sentences = [item for item in best_sentences if item[4] >= 5]
    if not best_sentences:
        result = results[0]
        answer = f"没有抽取到明确数值。最相关依据是 {result['code']}，{result['heading']}，位置 {result['page']}：{result['text']}"
        return f"{SEMANTIC_FALLBACK_PREFIX}\n{answer}" if semantic_fallback else answer

    top = best_sentences[0]
    _, sentence, numbers, result, _ = top
    # When the question targets a specific unit (e.g. 载荷→kN), only accept
    # numbers carrying that unit as the headline value, so we never report a
    # wrong-unit figure (e.g. an "A4 297 mm" page size for a force question).
    display_numbers = [n for n in numbers if number_matches_intent(n, intent)] if intent else numbers
    if display_numbers:
        answer = f"直接答案：相关数值为 {', '.join(display_numbers[:8])}。"
    elif intent:
        unit_hint = INTENT_UNIT_LABEL.get(intent, "目标单位")
        answer = f"直接答案：本地条款中未检索到带{unit_hint}的明确数值，最相关原文如下，建议核对原文或换用内置模型。"
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
            shown_numbers = [n for n in support_numbers if number_matches_intent(n, intent)] if intent else support_numbers
            value = f"{support_result['code']} {support_result['page']}：{support_sentence}"
            if shown_numbers:
                value += f"（数值：{', '.join(shown_numbers[:5])}）"
            supporting.append(value)
        if supporting:
            answer += "\n其他相关依据：" + "；".join(supporting)

    return f"{SEMANTIC_FALLBACK_PREFIX}\n{answer}" if semantic_fallback else answer


def split_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[。.!?;；])\s+|(?<=\.)\s+(?=[A-Z])", compact)
    sentences = [part.strip() for part in parts if len(part.strip()) >= 20]
    windows = list(sentences)
    for index in range(len(sentences) - 1):
        windows.append(f"{sentences[index]} {sentences[index + 1]}")
    return windows


def extract_answer_numbers(text: str) -> list[str]:
    num = r"\d{1,3}(?:[,\u00a0]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
    patterns = [
        rf"[-+]?(?:{num})\s*(?:\u00b0C|\u2103|\u00b0F|K|degrees?\s+C|degrees?\s+F)\b",
        rf"[-+]?(?:{num})\s*(?:°C|℃|°F|K|degrees?\s+C|degrees?\s+F|\bC\b|\bF\b|percent|%|mm|cm|m|km|kg|g|kN|daN|Nm|N·m|N|MΩ|kΩ|Ω|ohm/V|ohm|VAC|VDC|kV|V|A|W|kW|s|ms|min|h|km/h|mph|kPa|MPa|bar|g/km|g/kWh|mg/kWh|ppm|dB|dB\\(A\\)|cd|lx|lux|degrees?|°)\b",
        rf"\b(?:minus|negative)?\s*(?:{num})\s*degrees?\b",
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


INTENT_UNITS = {
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
INTENT_UNIT_LABEL = {
    "temperature": "温度(°C)",
    "speed": "速度(km/h)",
    "pressure": "压力(kPa/MPa)",
    "distance": "尺寸(mm/cm/m)",
    "force": "力/载荷(kN/daN/N)",
    "noise": "噪声(dB)",
    "emission": "排放(g/kWh)",
    "angle": "角度(°)",
    "lighting": "照度/光强(lx/cd)",
}


def intent_units(intent: str) -> tuple[str, ...]:
    units = INTENT_UNITS.get(intent, ())
    if intent == "temperature":
        units = units + ("\u00b0c", "\u2103", "\u00b0f")
    return units


def number_matches_intent(number: str, intent: str) -> bool:
    if not intent:
        return True
    lowered = number.lower()
    return any(unit in lowered for unit in intent_units(intent))


def answer_unit_bonus(numbers: list[str], intent: str) -> float:
    if not intent:
        return len(numbers) * 1.5
    units = intent_units(intent)
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


CORPUS_CACHE_FILE = REGULATION_CORPUS / "_cache" / "corpus_chunks.json"


def load_corpus_chunks() -> list[dict[str, Any]]:
    global CORPUS_CACHE
    if CORPUS_CACHE is not None:
        return CORPUS_CACHE

    with CORPUS_LOCK:
        if CORPUS_CACHE is not None:
            return CORPUS_CACHE

        manifest_path = REGULATION_CORPUS / "manifest.json"
        if not manifest_path.exists():
            CORPUS_CACHE = []
            return CORPUS_CACHE

        source_fingerprint = corpus_source_fingerprint(manifest_path)
        cached = _load_corpus_disk_cache(manifest_path, source_fingerprint)
        if cached is not None:
            CORPUS_CACHE = cached
            return CORPUS_CACHE

        chunks: list[dict[str, Any]] = []
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest:
            # manifest paths may use Windows separators; normalize for any OS.
            rel = str(entry.get("path", "")).replace("\\", "/")
            path = ROOT / rel
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

        _save_corpus_disk_cache(chunks, source_fingerprint)
        CORPUS_CACHE = chunks
        return CORPUS_CACHE


def corpus_source_fingerprint(manifest_path: Path) -> dict[str, Any]:
    fingerprint: dict[str, Any] = {
        "version": CORPUS_CACHE_VERSION,
        "ocr_enabled": OCR_ENABLED,
        "ocr_langs": OCR_LANGS,
        "ocr_low_text_page_chars": OCR_LOW_TEXT_PAGE_CHARS,
        "ocr_trigger_low_text_ratio": OCR_TRIGGER_LOW_TEXT_RATIO,
        "ocr_trigger_total_chars_per_page": OCR_TRIGGER_TOTAL_CHARS_PER_PAGE,
        "manifest_mtime": manifest_path.stat().st_mtime,
        "sources": [],
    }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return fingerprint
    for entry in manifest:
        rel = str(entry.get("path", "")).replace("\\", "/")
        path = ROOT / rel
        if not path.exists() or path.suffix.lower() not in {".pdf", ".xml"}:
            continue
        stat = path.stat()
        fingerprint["sources"].append(
            {
                "path": rel,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }
        )
    return fingerprint


def _load_corpus_disk_cache(manifest_path: Path, source_fingerprint: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Return cached corpus chunks if a fresh on-disk cache exists, else None."""
    try:
        if not CORPUS_CACHE_FILE.exists():
            return None
        if CORPUS_CACHE_FILE.stat().st_mtime < manifest_path.stat().st_mtime:
            return None
        data = json.loads(CORPUS_CACHE_FILE.read_text(encoding="utf-8"))
        if data.get("source_fingerprint") != source_fingerprint:
            return None
        chunks = data.get("chunks", [])
        for chunk in chunks:
            chunk["tokens"] = set(chunk.get("tokens", []))
        return chunks
    except Exception:
        return None


def _save_corpus_disk_cache(chunks: list[dict[str, Any]], source_fingerprint: dict[str, Any]) -> None:
    try:
        CORPUS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        serializable = [
            {**{k: v for k, v in chunk.items() if k != "tokens"}, "tokens": sorted(chunk.get("tokens", []))}
            for chunk in chunks
        ]
        tmp = CORPUS_CACHE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"source_fingerprint": source_fingerprint, "chunks": serializable}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CORPUS_CACHE_FILE)
    except Exception:
        pass


def warm_corpus_cache() -> None:
    try:
        load_corpus_chunks()
    except Exception:
        pass


STRUCTURED_BOUNDARY_RE = re.compile(
    r"(?=\b(?:S\d+(?:\.\d+)*\.?|Annex\s+\d+[A-Z]?|Appendix\s+\d+|Table\s+[A-Z0-9IVXLC]+|P[123])\b|"
    r"\b\d+(?:\.\d+){0,5}\.?\s+[A-Z][A-Za-z-]+|\([a-z0-9]+\)\s+)",
    re.I,
)
PARAMETER_ANCHOR_RE = re.compile(
    r"\b(?:table|annex|appendix|load|force|energy|voltage|isolation|ohms?/volt|"
    r"resistance|height|clearance|side marker|reflex|retro-reflector|"
    r"csms|sums|process|manufacturer|certificate|shall|P1|P2|P3|S\d)",
    re.I,
)
XML_SECTION_HEADING_RE = re.compile(r"^(?:S\d+(?:\.\d+)*\.?|§\s*\d+(?:\.\d+)*)\s+")


def compact_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def split_parameter_chunks(text: str, size: int = 1500, overlap: int = 120) -> list[str]:
    compact = compact_space(text)
    if len(compact) <= size:
        return [compact] if len(compact) > 80 else []

    parts = [part.strip() for part in STRUCTURED_BOUNDARY_RE.split(compact) if part.strip()]
    if len(parts) <= 1:
        return split_long_text(compact, size=size, overlap=overlap)

    chunks: list[str] = []
    current = ""
    for part in parts:
        if not current:
            current = part
            continue
        if len(current) + len(part) + 1 <= size:
            current = f"{current} {part}"
            continue
        if len(current) > 80:
            chunks.append(current)
        current = part
    if len(current) > 80:
        chunks.append(current)

    expanded: list[str] = []
    for chunk in chunks:
        if len(chunk) <= size:
            expanded.append(chunk)
        else:
            expanded.extend(split_long_text(chunk, size=size, overlap=overlap))
    return expanded


def element_local_name(element: ET.Element) -> str:
    return str(element.tag).rsplit("}", 1)[-1].upper()


def element_compact_text(element: ET.Element) -> str:
    return compact_space(" ".join(element.itertext()))


def extract_xml_blocks(root: ET.Element) -> list[tuple[str, str]]:
    paragraphs: list[str] = []
    for element in root.iter():
        if element_local_name(element) not in {"P", "HD", "FP"}:
            continue
        text = element_compact_text(element)
        if len(text) >= 8:
            paragraphs.append(text)
    if not paragraphs:
        text = element_compact_text(root)
        return [("XML text", text)] if text else []

    blocks: list[tuple[str, str]] = []
    heading = "XML text"
    current: list[str] = []

    def flush() -> None:
        nonlocal current, heading
        text = compact_space(" ".join(current))
        if len(text) >= 80:
            blocks.append((heading, text))
        current = []

    for paragraph in paragraphs:
        is_heading = bool(XML_SECTION_HEADING_RE.match(paragraph))
        if is_heading and current:
            flush()
            heading = paragraph[:180]
        elif is_heading:
            heading = paragraph[:180]
        current.append(paragraph)
    flush()
    return blocks


def extract_xml_search_chunks(path: Path, entry: dict[str, Any]) -> list[dict[str, Any]]:
    root = ET.parse(path).getroot()
    chunks: list[dict[str, Any]] = []
    for block_index, (heading, block_text) in enumerate(extract_xml_blocks(root), start=1):
        parts = split_parameter_chunks(block_text, size=1700, overlap=160)
        if not parts:
            continue
        for part_index, text in enumerate(parts, start=1):
            chunk_heading = heading if len(parts) == 1 else f"{heading} / part {part_index}"
            chunks.append(
                {
                    "code": entry["code"],
                    "title": entry["title"],
                    "domain": entry["domain"],
                    "region": entry["region"],
                    "path": display_path(path),
                    "heading": chunk_heading or f"{entry['code']} section {block_index}",
                    "page": "CFR XML",
                    "text": excerpt(text),
                }
            )
    if chunks:
        return chunks

    section_text = compact_space(" ".join(root.itertext()))
    for index, text in enumerate(split_long_text(section_text), start=1):
        chunks.append(
            {
                "code": entry["code"],
                "title": entry["title"],
                "domain": entry["domain"],
                "region": entry["region"],
                "path": display_path(path),
                "heading": f"{entry['code']} chunk {index}",
                "page": "CFR XML",
                "text": excerpt(text),
            }
        )
    return chunks


def extract_search_chunks(path: Path, entry: dict[str, Any]) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".pdf":
        pages = extract_pdf(path)
        clauses = split_clauses(pages)
        chunks = chunks_from_clauses(clauses, entry["title"], entry["code"], entry["domain"], entry["region"], display_path(path))
        extraction = pdf_extraction_summary(pages)
        for chunk in chunks:
            chunk["extract_method"] = extraction["extract_method"]
            chunk["text_coverage"] = extraction["text_coverage"]
        return chunks

    return extract_xml_search_chunks(path, entry)


def chunks_from_clauses(
    clauses: list[Clause],
    title: str,
    code: str,
    domain: str = "uploaded_document",
    region: str = "uploaded",
    path: str = "",
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for clause in clauses:
        text = compact_space(clause.text)
        if len(text) <= 40:
            continue
        page = f"{clause.start_page}-{clause.end_page}"
        base = {
            "code": code,
            "title": title,
            "domain": domain,
            "region": region,
            "path": path,
            "heading": clause.heading,
            "page": page,
            "text": excerpt(text),
        }
        chunks.append(base)

        should_split = len(text) > 1100 or bool(PARAMETER_ANCHOR_RE.search(text))
        if not should_split:
            continue
        parts = split_parameter_chunks(text, size=1500, overlap=140)
        if len(parts) <= 1:
            continue
        for part_index, part in enumerate(parts, start=1):
            part_text = excerpt(part)
            if part_text == base["text"]:
                continue
            chunks.append(
                {
                    "code": code,
                    "title": title,
                    "domain": domain,
                    "region": region,
                    "path": path,
                    "heading": f"{clause.heading} / parameter {part_index}",
                    "page": page,
                    "text": part_text,
                }
            )
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
    # Chinese engineering terms -> English regulation wording. The corpus is in
    # English, so a Chinese query only retrieves well if we inject the English
    # equivalents it should match against.
    mapping = {
        "温度": " temperature ambient initial hot cold celsius",
        "环境温度": " ambient temperature",
        "初始温度": " initial temperature",
        "制动": " braking brake",
        "刹车": " braking brake",
        "制动力": " braking force",
        "制动距离": " braking distance stopping distance",
        "停车距离": " stopping distance",
        "响应时间": " response time reaction time build-up time",
        "响应": " response reaction",
        "压缩空气": " compressed air pneumatic",
        "气压制动": " compressed air braking pneumatic braking",
        "压缩空气制动": " compressed air braking pneumatic braking",
        "防抱死": " anti-lock abs",
        "电子稳定": " electronic stability control esc",
        "稳定性": " stability control",
        "速度": " speed velocity km/h mph",
        "测试速度": " test speed",
        "压力": " pressure kpa mpa bar",
        "距离": " distance stopping distance",
        "减速度": " deceleration",
        "适用": " application scope applies vehicles categories",
        "适用范围": " scope of application applies vehicles categories",
        "范围": " scope range",
        "车辆": " vehicle vehicles category categories",
        "挂车": " trailer trailers",
        "报警": " warning signal alert",
        "碰撞": " collision impact crash",
        "避免碰撞": " collision avoidance avoid collision",
        "误报": " false reaction false warning",
        "稳定": " stability control",
        "转向": " steering",
        "车道": " lane lane departure lane keeping",
        "盲区": " blind spot",
        "防护": " underrun protection guard protective device",
        "后防护": " rear underrun protection guard",
        "前防护": " front underrun protection",
        "前下部防护": " front underrun protection",
        "后下部防护": " rear underrun protection",
        "侧防护": " lateral protection side guard",
        "能量吸收": " energy absorption",
        "离地高度": " ground clearance height",
        "视野": " indirect vision mirror rear visibility",
        "照明": " lighting lamps light-signalling luminous intensity",
        "灯具": " lamps lighting light-signalling",
        "侧标志灯": " side marker lamp side marker light",
        "标志灯": " marker lamp marker light",
        "反射器": " retro-reflector reflex reflector reflector",
        "回复反射器": " retro-reflector reflex reflector",
        "电磁": " electromagnetic compatibility emc",
        "电磁兼容": " electromagnetic compatibility emc",
        "网络安全": " cyber security cybersecurity csms",
        "软件更新": " software update sums software update management",
        "排放": " emissions pollutants g/kwh mg/kwh",
        "噪声": " noise sound dB",
        "轮胎": " tyres tires rims load index speed category",
        "挂接": " coupling fifth wheel drawbar mechanical coupling",
        "载荷": " load force kN daN",
        "试验载荷": " test load applied force kN daN",
        "角度": " angle degrees",
        "照度": " luminous intensity illuminance lux cd",
        "高压": " high voltage",
        "电压": " voltage volts",
        "绝缘": " insulation electrical isolation isolation",
        "绝缘电阻": " isolation resistance insulation resistance ohm",
        "电气安全": " electrical safety",
        "充电": " charging charge",
        "电池": " battery rechargeable energy storage ress",
        "对应": " correspond corresponding equivalent maps to",
        "对应关系": " correspondence corresponding equivalent",
    }
    expanded = text
    for term, addition in mapping.items():
        if term in text:
            expanded += addition
    return expanded


def main() -> None:
    host = os.environ.get("REG_ASSISTANT_HOST", "127.0.0.1")
    port = int(os.environ.get("REG_ASSISTANT_PORT", "8000"))
    threading.Thread(target=warm_corpus_cache, daemon=True).start()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"法规对比原型已启动：http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
