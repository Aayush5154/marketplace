import json
import pickle

from llm.chat import format_context, review_listing_with_ai
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
    with open("data/bm25.pkl", "rb") as f:
        keyword_search = pickle.load(f)
    semantic_search = SemanticSearch()
    hybrid_search = CombinedSearch(keyword_search=keyword_search, vector_search=semantic_search)
    return keyword_search, hybrid_search


def ask_policy(hybrid_search):
    query = input("Policy question: ").strip()
    if not query:
        return
    results = hybrid_search.search(query=query, top_n=5)
    format_context(results)          # (score, {"text", "metadata"}) -> text


    for _rank, (_score, item) in enumerate(results, start=1):
        item.get("metadata", {})


def review_listing(keyword_search, hybrid_search):
    path = input("Listing JSON file (Enter = sample listing): ").strip()
    if path:
        with open(path, encoding="utf-8") as f:
            listing = json.load(f)
    else:
        listing = SAMPLE_LISTING

    out = review_listing_with_ai(listing, [], keyword_search, hybrid_search)

    for _c in out["failed"]:
        pass

    if out["error"]:
        return
    ai = out["ai"]
    for f in ai["findings"]:
        pass
    if ai["assumptions"]:
        for _a in ai["assumptions"]:
            pass
    if ai["style_suggestions"]:
        for _s in ai["style_suggestions"]:
            pass
    if ai["revised_listing"]:
        pass


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
