import json
import pickle

from llm.chat import format_context, generate_answer, review_listing_with_ai
from pro.hybrid import CombinedSearch
from pro.semantic import SemanticSearch

SAMPLE_LISTING = {
    "title": "BEST EVER Headphones!!! LIMITED TIME SALE",
    "description": "Genuine leather case, 100% guaranteed sound. Doctor recommended for relaxing. "
                   "Call 9876543210 to get the lowest price today only.",
    "category": "Electronics",
    "price": "$49.99",
    "attributes": {"brand": "Aurora", "condition": "New"},
    "seller": "Aurora Store",
    "tags": ["headphones", "sale"],
}


def load_search():
    print("Initializing BM25...")
    with open("data/bm25.pkl", "rb") as f:
        keyword_search = pickle.load(f)
    print("Connecting to Pinecone...")
    semantic_search = SemanticSearch()
    print("Initializing Hybrid Search...")
    hybrid_search = CombinedSearch(keyword_search=keyword_search, vector_search=semantic_search)
    return keyword_search, hybrid_search


def ask_policy(hybrid_search):
    query = input("Policy question: ").strip()
    if not query:
        return
    results = hybrid_search.search(query=query, top_n=5)
    context = format_context(results)          # (score, {"text", "metadata"}) -> text

    print("Generating answer with Groq...")
    print("\n" + generate_answer(query, context))

    print("\n" + "=" * 80 + "\nRETRIEVED CHUNKS\n" + "=" * 80)
    for rank, (score, item) in enumerate(results, start=1):
        meta = item.get("metadata", {})
        print(f"Rank {rank} | Score: {score:.4f} | {meta.get('rule_id', meta.get('chunk_type'))}")
        print(item["text"])
        print("-" * 80)


def review_listing(keyword_search, hybrid_search):
    path = input("Listing JSON file (Enter = sample listing): ").strip()
    if path:
        with open(path, encoding="utf-8") as f:
            listing = json.load(f)
    else:
        listing = SAMPLE_LISTING
    print(json.dumps(listing, indent=2, ensure_ascii=False))

    out = review_listing_with_ai(listing, [], keyword_search, hybrid_search)

    print("\n" + "=" * 80 + "\nDETERMINISTIC CHECKS\n" + "=" * 80)
    for c in out["failed"]:
        print(f"FAIL {c['check']:<20} {c['rules']}  {c['message']}")
    print(f"Passed {len(out['checks']) - len(out['failed'])} of {len(out['checks'])}")
    print("Model triggers:", [f"{t['field']}:{t['phrase']}" for t in out["triggers"]])

    print("\n" + "=" * 80 + "\nAI REVIEW\n" + "=" * 80)
    if out["error"]:
        print(out["error"])
        return
    ai = out["ai"]
    for f in ai["findings"]:
        print(f"\n[{f['severity']}] {f['field']} | {', '.join(f['rule_ids'])} | {f['issue_type']}")
        print(f"  Quote      : {f['quote']}")
        print(f"  Why        : {f['explanation']}")
        print(f"  Suggestion : {f['suggested_wording']}")
    if ai["assumptions"]:
        print("\nAssumptions:")
        for a in ai["assumptions"]:
            print(" -", a)
    if ai["style_suggestions"]:
        print("\nStyle suggestions (no rule cited):")
        for s in ai["style_suggestions"]:
            print(" -", s)
    if ai["revised_listing"]:
        print("\nSuggested revision:", json.dumps(ai["revised_listing"], indent=2, ensure_ascii=False))


def main():
    keyword_search, hybrid_search = load_search()
    while True:
        choice = input("\n1) Ask policy question   2) Review a listing   exit) quit : ").strip().lower()
        if choice == "exit":
            break
        if choice == "1":
            ask_policy(hybrid_search)
        elif choice == "2":
            review_listing(keyword_search, hybrid_search)


if __name__ == "__main__":
    main()
