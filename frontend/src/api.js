const BASE = "";

// Fallback so the category dropdown still works if the API is unreachable.
export const CATEGORIES = [
  "Electronics",
  "Home & Kitchen",
  "Fashion & Apparel",
  "Beauty & Personal Care",
  "Sports & Outdoors",
  "Books & Media",
  "Toys & Games",
  "Home Services",
  "Professional Services",
  "Digital Products",
];

async function call(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

export const api = {
  health: () => call("/api/health"),
  init: () => call("/api/init", { method: "POST" }),
  categories: () => call("/api/categories"),
  review: (body) => call("/api/reviews", { method: "POST", body: JSON.stringify(body) }),
  getReview: (id) => call(`/api/reviews/${id}`),
  listReviews: (listingId) =>
    call(listingId ? `/api/reviews?listing_id=${listingId}` : "/api/reviews"),
  listListings: () => call("/api/listings"),
  listDecisions: (listingId) =>
    call(listingId ? `/api/decisions?listing_id=${listingId}` : "/api/decisions"),
  decide: (body) => call("/api/decisions", { method: "POST", body: JSON.stringify(body) }),
  auditVerify: () => call("/api/audit/verify"),
  ask: (body) => call("/api/ask", { method: "POST", body: JSON.stringify(body) }),
};

export function parseAttributes(text) {
  const attrs = {};
  String(text || "")
    .replace(/;/g, "\n")
    .split("\n")
    .forEach((part) => {
      const i = part.indexOf(":");
      if (i > 0) attrs[part.slice(0, i).trim()] = part.slice(i + 1).trim();
    });
  return attrs;
}
