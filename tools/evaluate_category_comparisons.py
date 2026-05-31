from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict
from itertools import combinations
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import Clause, ROOT, build_compare_conclusion, compare_clauses, extract_pdf, split_clauses, split_long_text


REGULATIONS = ROOT / "data" / "regulations"
OUT_DIR = ROOT / "data" / "evaluations"
MAX_CLAUSES_PER_DOC = 260


def load_manifest() -> list[dict[str, Any]]:
    return json.loads((REGULATIONS / "manifest.json").read_text(encoding="utf-8"))


def load_clauses(entry: dict[str, Any]) -> list[Clause]:
    path = ROOT / entry["path"]
    if not path.exists():
        return []
    try:
        if path.suffix.lower() == ".pdf":
            clauses = split_clauses(extract_pdf(path))
        elif path.suffix.lower() == ".xml":
            text = " ".join(ET.parse(path).getroot().itertext())
            chunks = split_long_text(text, size=1400, overlap=180)
            clauses = [
                Clause(
                    id=f"X{index:04d}",
                    heading=f"{entry['code']} chunk {index}",
                    text=chunk,
                    start_page=0,
                    end_page=0,
                )
                for index, chunk in enumerate(chunks, start=1)
            ]
        else:
            return []
    except Exception as exc:
        print(f"SKIP bad source: {entry['code']} {entry['path']} ({exc})")
        return []
    return filter_useful_clauses(clauses)[:MAX_CLAUSES_PER_DOC]


def filter_useful_clauses(clauses: list[Clause]) -> list[Clause]:
    useful = []
    for clause in clauses:
        text = clause.text.strip()
        if len(text) < 50:
            continue
        if text.count(".") > len(text) * 0.35:
            continue
        useful.append(clause)
    return useful


def summarize_pair(left: dict[str, Any], right: dict[str, Any], left_clauses: list[Clause], right_clauses: list[Clause]) -> dict[str, Any]:
    results = compare_clauses(left_clauses, right_clauses)
    conclusion = build_compare_conclusion(left["code"], right["code"], results)
    counts = conclusion["counts"]
    substantive = sum(
        counts.get(name, 0)
        for name in ["阈值/数值变化", "测试方法变化", "适用范围变化", "引用标准变化", "定义变化", "内容修改"]
    )
    low_conf = counts.get("疑似无对应条款", 0)
    total = max(1, len(results))
    return {
        "left": left["code"],
        "right": right["code"],
        "left_region": left["region"],
        "right_region": right["region"],
        "left_clauses": len(left_clauses),
        "right_clauses": len(right_clauses),
        "result_count": len(results),
        "substantive_count": substantive,
        "low_confidence_ratio": round(low_conf / total, 3),
        "conclusion": conclusion,
        "top_results": [
            {
                "change_type": item.change_type,
                "risk": item.risk,
                "score": round(item.score, 3),
                "left_heading": item.left.heading if item.left else "",
                "right_heading": item.right.heading if item.right else "",
                "summary": item.summary,
            }
            for item in results[:12]
        ],
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = [
        entry
        for entry in load_manifest()
        if entry.get("status") in {"copied", "exists", "downloaded", "extracted_govinfo_2024"}
        and Path(entry["path"]).suffix.lower() in {".pdf", ".xml"}
    ]
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for entry in manifest:
        by_domain.setdefault(entry["domain"], []).append(entry)

    clause_cache: dict[str, list[Clause]] = {}
    evaluations = []
    for domain, entries in sorted(by_domain.items()):
        for left, right in combinations(entries, 2):
            left_key = left["path"]
            right_key = right["path"]
            clause_cache.setdefault(left_key, load_clauses(left))
            clause_cache.setdefault(right_key, load_clauses(right))
            left_clauses = clause_cache[left_key]
            right_clauses = clause_cache[right_key]
            if not left_clauses or not right_clauses:
                continue
            evaluations.append(
                {
                    "domain": domain,
                    **summarize_pair(left, right, left_clauses, right_clauses),
                }
            )
            print(f"{domain}: {left['code']} vs {right['code']}")

    (OUT_DIR / "category_comparison_report.json").write_text(json.dumps(evaluations, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(evaluations)


def write_markdown(evaluations: list[dict[str, Any]]) -> None:
    lines = ["# Category Comparison Self-Test", ""]
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for item in evaluations:
        by_domain.setdefault(item["domain"], []).append(item)

    for domain, items in sorted(by_domain.items()):
        lines.extend([f"## {domain}", ""])
        for item in items:
            lines.append(f"### {item['left']} vs {item['right']}")
            lines.append("")
            lines.append(item["conclusion"]["headline"])
            lines.append("")
            lines.append(
                f"- Clauses: {item['left_clauses']} vs {item['right_clauses']}; results: {item['result_count']}; substantive: {item['substantive_count']}; low-confidence ratio: {item['low_confidence_ratio']}"
            )
            for result in item["top_results"][:5]:
                lines.append(
                    f"- {result['change_type']} / risk {result['risk']} / score {result['score']}: {result['left_heading'][:80]} -> {result['right_heading'][:80]}"
                )
            lines.append("")

    (OUT_DIR / "category_comparison_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
