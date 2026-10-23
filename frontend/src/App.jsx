import React, { useEffect, useState } from "react";
import { api, parseAttributes, CATEGORIES } from "./api";
import "./styles.css";

const TABS = ["Review", "Batch", "Compare", "History", "Ask"];

function Outcome({ value }) {
  const cls = value === "Approved" ? "Approved" : value === "Rejected" ? "Rejected" : "Needs";
  return <span className={`badge ${cls}`}>Outcome: {value}</span>;
}

function FindingCard({ bundle, finding, reviewer, onDecide }) {
  const [text, setText] = useState(finding.suggested_wording || finding.quote || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const done = (bundle.decisions || {})[finding.id];
  const rules = safeRules(finding.rule_ids);
  const evidence = finding.quote
    ? String(bundle.original?.description || "").split(finding.quote)
    : null;

  async function act(action) {
    if (!reviewer.trim()) { setErr("Enter reviewer name first."); return; }
    setBusy(true); setErr("");
    try {
      const out = await api.decide({
        review_id: bundle.review_id, finding_id: finding.id,
        action, revised_text: text, reviewer,
      });
      onDecide(finding.id, action, text, out.outcome, out.decisions);
    } catch (e) { setErr(e.message); }
    setBusy(false);
  }

  return (
    <div className={`card finding ${finding.severity}`}>
      <strong>[{finding.severity}] {finding.field} — {finding.issue_type || finding.kind}</strong>
      <div className="muted">{finding.kind === "deterministic" ? "Rule check (no AI)" : "AI finding"}</div>
      {finding.quote && <div className="evidence">Evidence: {evidence && evidence.length > 1
        ? <>{evidence[0]}<mark>{finding.quote}</mark>{evidence.slice(1).join(finding.quote)}</>
        : <i>{finding.quote}</i>}</div>}
      {finding.explanation && <p>{finding.explanation}</p>}
      <div>{rules.map((r) => <span key={r} className="chip">{r}</span>)}</div>
      {finding.suggested_wording && <p>Suggestion: {finding.suggested_wording}</p>}
      {done && <div className="muted">Decided: <b>{done.action}</b></div>}
      <label>Fixed text</label>
      <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} />
      {err && <div className="err">{err}</div>}
      <div className="btnrow">
        <button className="btn" disabled={busy} onClick={() => act("approve")}>Approve</button>
        <button className="btn" disabled={busy} onClick={() => act("edit")}>Save edit</button>
        <button className="btn" disabled={busy} onClick={() => act("reject")}>Reject</button>
      </div>
    </div>
  );
}

function safeRules(ruleIds) {
  if (Array.isArray(ruleIds)) return ruleIds;
  try { return JSON.parse(ruleIds || "[]"); } catch { return []; }
}

function ReviewResult({ bundle, reviewer, onDecide }) {
  if (!bundle) return <p className="muted">Fill the form and click “Review listing”.</p>;
  const ai = bundle.ai;
  return (
    <div>
      <div className="outcome-panel" aria-live="polite">
        <Outcome value={bundle.outcome} />
        <span className="muted">{bundle.failed?.length || bundle.findings?.length
          ? `${bundle.findings?.filter((f) => f.severity === "Critical").length || 0} critical or major finding(s) open`
          : "No open findings"}</span>
      </div>
      <h4>Rule checks (no AI)</h4>
      {(bundle.failed || []).length === 0
        ? <div className="ok">All deterministic checks passed.</div>
        : bundle.failed.map((c, i) => (
          <div key={i} className="err"><b>{c.check}</b> ({(c.rules || []).join(", ")}): {c.message}</div>
        ))}
      {(bundle.triggers || []).length > 0 && (
        <div className="warn">Phrases sent for AI review: {bundle.triggers.map((t) => `${t.phrase} (${t.field})`).join(", ")}</div>
      )}
      <h4>AI review</h4>
      {bundle.error && <div className="err">{bundle.error}</div>}
      {ai && (
        <>
          {(ai.findings || []).length === 0 && <div className="ok">No policy findings from the AI.</div>}
          {(ai.assumptions || []).length > 0 && (
            <div className="card"><strong>Assumptions</strong>
              <ul>{ai.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul></div>
          )}
          {(ai.style_suggestions || []).length > 0 && (
            <div className="card"><strong>Style suggestions (no rule cited)</strong>
              <ul>{ai.style_suggestions.map((s, i) => <li key={i}>{s}</li>)}</ul></div>
          )}
        </>
      )}
      <h4>Field-by-field decisions</h4>
      {(bundle.findings || []).length === 0 && <div className="ok">No findings — Approved.</div>}
      {(bundle.findings || []).map((f) => (
        <FindingCard key={f.id} bundle={bundle} finding={f} reviewer={reviewer} onDecide={onDecide} />
      ))}
    </div>
  );
}

function simpleDiff(a, b) {
  if (a === b) return null;
  const al = a.split("\n"), bl = b.split("\n");
  const out = [];
  const n = Math.max(al.length, bl.length);
  for (let i = 0; i < n; i++) {
    if (al[i] !== bl[i]) {
      if (al[i] !== undefined) out.push(`- ${al[i]}`);
      if (bl[i] !== undefined) out.push(`+ ${bl[i]}`);
    } else out.push(`  ${al[i]}`);
  }
  return out.join("\n");
}

function CompareView({ bundle }) {
  const [data, setData] = useState(null);
  const signature = JSON.stringify((bundle?.decisions || {}));
  useEffect(() => {
    let active = true;
    if (bundle?.review_id) {
      api.getReview(bundle.review_id).then((d) => { if (active) setData(d); }).catch(() => {});
    }
    return () => { active = false; };
  }, [bundle?.review_id, signature]);
  const view = data || bundle;
  if (!view) return <p className="muted">Review a listing first — original vs revised appears here.</p>;
  const original = view.original || {};
  const revised = view.revised || {};
  return (
    <div>
      <Outcome value={view.outcome} />
      <div className="grid2" style={{ marginTop: 12 }}>
        <div className="card"><strong>Original</strong>
          {["title", "description", "tags"].map((f) => (
            <div key={f}><label>{f}</label><textarea rows={3} disabled value={original[f] || ""} /></div>
          ))}
        </div>
        <div className="card"><strong>Revised (approved + edited fixes)</strong>
          {["title", "description", "tags"].map((f) => (
            <div key={f}><label>{f}</label><textarea rows={3} disabled value={revised[f] || ""} /></div>
          ))}
        </div>
      </div>
      <div className="card"><strong>Word diff</strong>
        {["title", "description", "tags"].map((f) => {
          const d = simpleDiff(original[f] || "", revised[f] || "");
          return d ? <div key={f}><p><b>{f}</b></p><pre className="diff">{d}</pre></div> : null;
        })}
        {["title", "description", "tags"].every((f) => (original[f] || "") === (revised[f] || "")) &&
          <p className="muted">No changes — original and revised are identical.</p>}
      </div>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState("Review");
  const [ready, setReady] = useState(false);
  const [reviewer, setReviewer] = useState("");
  const [categories, setCategories] = useState([]);
  const [form, setForm] = useState({ title: "", description: "", category: "", price: "", attributes: "", seller: "", tags: "" });
  const [bundle, setBundle] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [batch, setBatch] = useState([]);
  const [batchIdx, setBatchIdx] = useState(0);
  const [batchResults, setBatchResults] = useState({});
  const [listings, setListings] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [decisions, setDecisions] = useState([]);
  const [filterListing, setFilterListing] = useState("");
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [chunks, setChunks] = useState([]);

  useEffect(() => {
    api.health()
      .then((h) => setReady(h.models_loaded))
      .catch(() => setErr("Backend not reachable. Start it with: uvicorn backend.app:app --port 8000"));
    api.categories()
      .then((c) => {
        setCategories(c.categories);
        setForm((f) => ({ ...f, category: f.category || c.categories[0] || "" }));
      })
      .catch(() => {
        setCategories(CATEGORIES);
        setForm((f) => ({ ...f, category: f.category || CATEGORIES[0] }));
      });
  }, []);

  useEffect(() => {
    function onKeyDown(event) {
      if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) return;
      const index = TABS.indexOf(tab);
      if (event.key === "?" ) {
        setErr("Shortcuts: j/k move between findings; a/e/r are available on each finding.");
      } else if (event.key === "ArrowRight") {
        setTab(TABS[(index + 1) % TABS.length]);
      } else if (event.key === "ArrowLeft") {
        setTab(TABS[(index - 1 + TABS.length) % TABS.length]);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [tab]);

  async function init() {
    setLoading(true); setErr("");
    try { await api.init(); setReady(true); }
    catch (e) { setErr(e.message); }
    setLoading(false);
  }

  async function reviewSingle(listing, others = []) {
    setLoading(true); setErr("");
    try {
      const out = await api.review({ listing, others, reviewer, top_n: 6 });
      setBundle(out);
    } catch (e) { setErr(e.message); }
    setLoading(false);
  }

  function onDecide(fid, action, revised, outcome, decisions) {
    setBundle((b) => ({ ...b, outcome, decisions: mapDecisions(b, decisions) }));
  }

  function mapDecisions(b, dec) {
    const m = {};
    Object.entries(dec || {}).forEach(([k, v]) => { m[k] = v; });
    return { ...(b.decisions || {}), ...m };
  }

  function submitForm() {
    reviewSingle({
      title: form.title, description: form.description, category: form.category,
      price: form.price, attributes: parseAttributes(form.attributes),
      seller: form.seller, tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
    });
  }

  function loadBatchFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        let items;
        if (file.name.endsWith(".csv")) {
          const [head, ...rows] = String(reader.result).trim().split("\n");
          const cols = head.split(",").map((c) => c.trim());
          items = rows.map((r) => {
            const vals = r.split(",");
            const o = {};
            cols.forEach((c, i) => { o[c] = (vals[i] || "").trim(); });
            return {
              title: o.title || "", description: o.description || "", category: o.category || "",
              price: o.price || "", attributes: parseAttributes(o.attributes || ""),
              seller: o.seller || "", tags: String(o.tags || "").split(";").map((t) => t.trim()).filter(Boolean),
            };
          });
        } else {
          const parsed = JSON.parse(String(reader.result));
          items = Array.isArray(parsed) ? parsed : parsed.listings || [];
        }
        setBatch(items); setBatchResults({}); setBatchIdx(0);
      } catch (ex) { setErr("Could not parse file: " + ex.message); }
    };
    reader.readAsText(file);
  }

  async function refreshHistory() {
    setLoading(true);
    try {
      const [l, r, d] = await Promise.all([
        api.listListings(), api.listReviews(filterListing || null), api.listDecisions(filterListing || null),
      ]);
      setListings(l.listings); setReviews(r.reviews); setDecisions(d.decisions);
    } catch (e) { setErr(e.message); }
    setLoading(false);
  }

  async function ask() {
    if (!query.trim()) return;
    setLoading(true); setErr("");
    try {
      const out = await api.ask({ query, top_n: 6 });
      setAnswer(out.answer); setChunks(out.chunks);
    } catch (e) { setErr(e.message); }
    setLoading(false);
  }

  const cur = batch[batchIdx];
  const curBundle = batchResults[batchIdx];

  return (
    <>
      <div className="header">
        <h1>Marketplace Listing Reviewer</h1>
        <span className="muted">{ready ? "Models ready" : "Models not loaded"}</span>
        {!ready && <button className="btn" onClick={init} disabled={loading}>Initialize models</button>}
        <span className="spacer" />
        <input
          type="text" placeholder="Reviewer name (must differ from seller)" value={reviewer}
          onChange={(e) => setReviewer(e.target.value)} style={{ maxWidth: 300 }}
        />
      </div>
      <div className="layout">
        {err && <div className="err">{err}</div>}
        {!ready && <div className="warn">Initialize models from the header before reviewing.</div>}
        <div className="tabs" role="tablist" aria-label="Reviewer views">
          {TABS.map((t) => <button key={t} role="tab" aria-selected={tab === t}
            className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{t}</button>)}
        </div>

        {tab === "Review" && (
          <div className="grid2">
            <div className="card">
              <h3>Listing</h3>
              <label>Title</label>
              <input type="text" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              <label>Description</label>
              <textarea rows={5} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              <label>Category</label>
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                {categories.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <label>Price (e.g. 49.99)</label>
              <input type="text" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />
              <label>Attributes (one per line: key: value)</label>
              <textarea rows={4} value={form.attributes} onChange={(e) => setForm({ ...form, attributes: e.target.value })} />
              <label>Seller</label>
              <input type="text" value={form.seller} onChange={(e) => setForm({ ...form, seller: e.target.value })} />
              <label>Tags (comma separated)</label>
              <input type="text" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
              <div className="btnrow">
                <button className="btn primary" onClick={submitForm} disabled={loading || !ready}>
                  {loading ? "Reviewing…" : "Review listing"}
                </button>
              </div>
            </div>
            <div className="card">
              <h3>Review result</h3>
              <ReviewResult bundle={bundle} reviewer={reviewer} onDecide={onDecide} />
            </div>
          </div>
        )}

        {tab === "Batch" && (
          <div className="card">
            <h3>Batch review (up to 100 listings, CSV or JSON)</h3>
            <input type="file" accept=".csv,.json" onChange={loadBatchFile} />
            {batch.length > 0 && (
              <>
                <p><b>{batchIdx + 1} / {batch.length}</b> — {cur?.title} (seller: {cur?.seller})</p>
                <div className="btnrow">
                  <button className="btn" disabled={!(batchIdx > 0)} onClick={() => setBatchIdx(batchIdx - 1)}>Previous</button>
                  <button className="btn" disabled={!(batchIdx < batch.length - 1)} onClick={() => setBatchIdx(batchIdx + 1)}>Next</button>
                  <button className="btn primary" disabled={loading} onClick={async () => {
                    setLoading(true);
                    try {
                      const others = batch.filter((_, j) => j !== batchIdx);
                      const out = await api.review({ listing: cur, others, reviewer, top_n: 6 });
                      setBatchResults((m) => ({ ...m, [batchIdx]: out }));
                      setBundle(out);
                    } catch (e) { setErr(e.message); }
                    setLoading(false);
                  }}>Review this listing</button>
                </div>
                {curBundle && <ReviewResult bundle={curBundle} reviewer={reviewer} onDecide={(fid, a, t, o, d) => {
                  setBatchResults((m) => ({ ...m, [batchIdx]: { ...m[batchIdx], outcome: o, decisions: { ...m[batchIdx].decisions, ...d } } }));
                }} />}
                <h4>Summary</h4>
                <table><thead><tr><th>#</th><th>Title</th><th>Seller</th><th>Rule fails</th><th>AI findings</th><th>Outcome</th></tr></thead>
                  <tbody>{batch.map((item, j) => {
                    const b = batchResults[j];
                    return <tr key={j}><td>{j + 1}</td><td>{item.title}</td><td>{item.seller}</td>
                      <td>{b ? b.failed.length : "–"}</td><td>{b ? (b.ai?.findings?.length ?? "–") : "–"}</td>
                      <td>{b ? b.outcome : "Not reviewed"}</td></tr>;
                  })}</tbody></table>
              </>
            )}
          </div>
        )}

        {tab === "Compare" && <CompareView bundle={bundle || (curBundle ?? null)} />}

        {tab === "History" && (
          <div className="card">
            <h3>History</h3>
            <div className="btnrow">
              <button className="btn primary" onClick={refreshHistory} disabled={loading}>Load history</button>
              <select value={filterListing} onChange={(e) => setFilterListing(e.target.value)} style={{ maxWidth: 320 }}>
                <option value="">All listings</option>
                {listings.map((l) => <option key={l.id} value={l.id}>#{l.id} {(l.title || "").slice(0, 50)}</option>)}
              </select>
            </div>
            <h4>Reviews ({reviews.length})</h4>
            <table><thead><tr><th>ID</th><th>Listing</th><th>Reviewer</th><th>Outcome</th><th>Created</th></tr></thead>
              <tbody>{reviews.map((r) => (
                <tr key={r.id}><td>{r.id}</td><td>#{r.listing_id}</td><td>{r.reviewer || "–"}</td><td>{r.outcome}</td><td>{r.created_at}</td></tr>
              ))}</tbody></table>
            <h4>Decisions (append-only audit log)</h4>
            <button className="btn" onClick={() => api.auditVerify().then((r) => setErr(r.valid ? "" : "Audit chain verification failed."))
              .catch((e) => setErr(e.message))}>Verify audit chain</button>
            <table><thead><tr><th>ID</th><th>Review</th><th>Field</th><th>Action</th><th>Reviewer</th><th>Created</th></tr></thead>
              <tbody>{decisions.map((d) => (
                <tr key={d.id}><td>{d.id}</td><td>{d.review_id}</td><td>{d.field}</td><td>{d.action}</td><td>{d.reviewer_name}</td><td>{d.created_at}</td></tr>
              ))}</tbody></table>
          </div>
        )}

        {tab === "Ask" && (
          <div className="card">
            <h3>Ask the policy</h3>
            <textarea rows={3} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ask a question about the policy…" />
            <div className="btnrow">
              <button className="btn primary" onClick={ask} disabled={loading || !ready}>Search</button>
              <button className="btn" onClick={() => { setAnswer(""); setChunks([]); setQuery(""); }}>Clear</button>
            </div>
            {answer && <><h4>Answer</h4><p>{answer}</p></>}
            {chunks.length > 0 && (
              <><h4>Retrieved chunks</h4>
                {chunks.map((c, i) => (
                  <div key={i} className="card"><b>#{i + 1} {c.label}</b> <span className="muted">({c.via})</span>
                    <p>{c.text}</p></div>
                ))}</>
            )}
          </div>
        )}
      </div>
    </>
  );
}
