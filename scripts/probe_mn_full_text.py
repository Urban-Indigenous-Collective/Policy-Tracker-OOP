#!/usr/bin/env python3
"""Deep probe: full bill text vs metadata excerpt for MN false positives."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from api_client import APIClient
from content_guard import check_legiscan_document_text
from discovery.queries import keyword_prescreen, strip_mmip_query_contamination
from document_processor import DocumentProcessor
from legiscan_processor import LegiScanProcessor
from llm.factory import get_llm_provider

URLS = [
    ("HF32", "https://legiscan.com/MN/bill/HF32/2020/X7"),
    ("SF25", "https://legiscan.com/MN/bill/SF25/2020/X7"),
]

api = APIClient(os.environ["LEGISCAN_KEY"])
proc = LegiScanProcessor(None, api_client=api)
doc = DocumentProcessor(get_llm_provider())

for label, url in URLS:
    bid = proc.resolve_bill_id(url)
    details = api.get_bill_details(bid)
    title = (details.get("bill") or {}).get("title", "")
    ex_meta = proc.get_bill_excerpt_for_relevance(url, bill_id=bid)
    ex_full = proc.get_bill_excerpt_for_relevance(url, bill_id=bid, document_processor=doc)
    text, _ = proc.get_bill_id_and_text(bid, document_processor=doc)
    print(f"=== {label} ===")
    print(f"title: {title[:100]}")
    for name, ex in [("meta", ex_meta), ("full", ex_full)]:
        clean = strip_mmip_query_contamination(ex)
        print(f"  {name}: len={len(ex)} kp={keyword_prescreen(clean)}")
    if isinstance(text, str) and not text.startswith("Error"):
        clean = strip_mmip_query_contamination(text)
        print(f"  decoded: len={len(text)} kp={keyword_prescreen(clean)}")
        print(f"  guard: {check_legiscan_document_text(text, url, title=title)}")
        for term in ("indigenous", "missing", "murdered", "mmip", "mmiw", "task force"):
            if term in clean.lower():
                i = clean.lower().find(term)
                print(f"    {term}: {clean[max(0,i-50):i+70]!r}")