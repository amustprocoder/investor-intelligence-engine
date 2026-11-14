/* Investor Finder - static, runs fully in the browser.
   Data: window.INVESTORS (verified firms, site/investors.js) and window.PROOF (site/proof.js). */
(function () {
  "use strict";

  const INV = window.INVESTORS || [];
  const PROOF = window.PROOF || null;
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ------------------------------------------------------------------ vocabulary
  const SECTORS = ["Digital health", "MedTech & devices", "Diagnostics", "AI & software", "Life sciences", "Care delivery"];
  const STAGES = ["Pre-seed", "Seed", "Series A", "Series B", "Growth"];
  const RAISE = [250e3, 500e3, 750e3, 1e6, 1.5e6, 3e6, 5e6, 10e6, 20e6];
  const DACH = ["Germany", "Austria", "Switzerland"];
  const EUROPE = DACH.concat(["France", "Netherlands", "Belgium", "Spain", "Italy", "United Kingdom", "Sweden", "Finland",
    "Denmark", "Norway", "Ireland", "Poland", "Portugal", "Hungary", "Czechia", "Other Europe"]);
  const CODES = { Germany: "DE", Austria: "AT", Switzerland: "CH", France: "FR", Netherlands: "NL", Belgium: "BE", Spain: "ES",
    Italy: "IT", "United Kingdom": "UK", Sweden: "SE", Finland: "FI", Denmark: "DK", Norway: "NO", Ireland: "IE", Poland: "PL",
    Portugal: "PT", Hungary: "HU", Czechia: "CZ", Japan: "JP", "United States": "US" };
  const USER_COUNTRIES = ["Germany", "Austria", "Switzerland", "France", "Netherlands", "Belgium", "Spain", "Italy",
    "United Kingdom", "Sweden", "Finland", "Denmark", "Norway", "Ireland", "Poland", "Portugal", "Hungary", "Czechia",
    "Other Europe", "Outside Europe"];
  // public regional mandates -> the only country that can pass them
  const GATES = [[/bavaria|berlin/i, "Germany"], [/upper austria|lower austria|styria/i, "Austria"], [/switzerland/i, "Switzerland"]];
  // the four questions; hand-set weights (held-out within one point of the tuned version)
  const W = { field: 0.40, stage: 0.25, cheque: 0.20, place: 0.15 };
  const EXAMPLE = { sectors: ["Digital health", "AI & software"], stage: "Seed", raise: 3, country: "Germany", types: null };
  const TYPES = [...new Set(INV.map((i) => i.type))].sort();

  const eur = (n) => n >= 1e6 ? "€" + (+(n / 1e6).toFixed(1)) + "M" : "€" + Math.round(n / 1e3) + "K";
  const range = (lo, hi) => lo != null && hi != null ? (lo === hi ? eur(lo) : `${eur(lo)}–${eur(hi)}`) :
    lo != null ? `from ${eur(lo)}` : hi != null ? `up to ${eur(hi)}` : "not published";
  const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch (e) { return u; } };
  const nice = (sector) => sector.replace(/^(\w)(\w*)/, (m, a, b) => (b === b.toLowerCase() ? a.toLowerCase() : a) + b);
  const stageSpan = (st) => st.length ? (st.length === 1 ? st[0] : `${st[0]} – ${st[st.length - 1]}`) : "n/a";

  // ------------------------------------------------------------------ scoring
  function score(inv, s) {
    const R = RAISE[s.raise];
    const checks = [];
    // 1. field
    const overlap = inv.focus.filter((f) => s.sectors.includes(f));
    let field;
    // specialists start higher; a generalist tops out at 60 however many tags overlap
    if (!s.sectors.length) field = inv.health_specialist ? 70 : 30;
    else field = inv.health_specialist ? Math.min(100, 50 + 25 * overlap.length) : Math.min(50, 20 + 15 * overlap.length);
    checks.push(overlap.length
      ? { k: field >= 75 ? "yes" : "part", t: `${inv.health_specialist ? "Backs" : "Some"} ${overlap.slice(0, 2).map(nice).join(" + ")}` }
      : inv.health_specialist ? { k: "part", t: "Health specialist" } : { k: "no", t: "Generalist, some health" });
    // 2. stage
    const si = STAGES.indexOf(s.stage), idx = inv.stages.map((x) => STAGES.indexOf(x));
    let stage = 0;
    if (idx.includes(si)) { stage = 100; checks.push({ k: "yes", t: `Invests at ${s.stage}` }); }
    else if (idx.some((i) => Math.abs(i - si) === 1)) { stage = 50; checks.push({ k: "part", t: `Usually ${stageSpan(inv.stages)}` }); }
    else checks.push({ k: "no", t: `Invests at ${stageSpan(inv.stages)}` });
    // 3. cheque
    const lo = inv.ticket_min_eur, hi = inv.ticket_max_eur;
    let cheque;
    if (lo == null && hi == null) { cheque = 50; checks.push({ k: "part", t: "Cheque size not published" }); }
    else if ((lo ?? 0) > R) {
      cheque = lo <= 2 * R ? 35 : 0;
      checks.push({ k: cheque ? "part" : "no", t: `Cheques from ${eur(lo)}${cheque ? "" : ", too big"}` });
    } else if (hi != null && hi < 0.05 * R) { cheque = 45; checks.push({ k: "part", t: `Small cheques, up to ${eur(hi)}` }); }
    else { cheque = 100; checks.push({ k: "yes", t: `Cheques ${range(lo, hi)}` }); }
    // 4. place
    let place, gatedOut = false;
    const gate = inv.requirement && GATES.find(([re]) => re.test(inv.requirement));
    const userEU = EUROPE.includes(s.country);
    if (gate && gate[1] !== s.country) { place = 0; gatedOut = true; checks.push({ k: "no", t: "Regional mandate" }); }
    else if (inv.country === s.country) { place = 100; checks.push({ k: "yes", t: `Based in ${s.country}` }); }
    else if (DACH.includes(inv.country) && DACH.includes(s.country)) { place = 85; checks.push({ k: "yes", t: `DACH (${CODES[inv.country]})` }); }
    else if (inv.region !== "Global" && userEU) { place = 65; checks.push({ k: "part", t: `Europe (${CODES[inv.country] || inv.country})` }); }
    else if (inv.region === "Global") { place = 45; checks.push({ k: "part", t: "Global fund" }); }
    else { place = 30; checks.push({ k: "no", t: "Europe only" }); }
    let total = W.field * field + W.stage * stage + W.cheque * cheque + W.place * place;
    if (gatedOut) total *= 0.5;
    return { inv, total: Math.round(total), parts: { field, stage, cheque, place }, checks, overlap, gatedOut };
  }
  const rank = (s) => INV.filter((i) => !s.types || s.types.includes(i.type)).map((i) => score(i, s))
    .sort((a, b) => b.total - a.total || b.overlap.length - a.overlap.length || a.inv.name.localeCompare(b.inv.name));
  const tier = (t) => (t >= 85 ? "hi" : t >= 65 ? "mid" : "lo");

  // ------------------------------------------------------------------ state + form
  const state = { ...EXAMPLE, sectors: [...EXAMPLE.sectors], shown: 10, name: "", pitch: "", sender: "" };
  let results = [];

  function buildForm() {
    $("#f-sector").innerHTML = SECTORS.map((x) => `<button type="button" class="chip" data-v="${x}">${x}</button>`).join("");
    $("#f-stage").innerHTML = STAGES.map((x) => `<button type="button" data-v="${x}">${x}</button>`).join("");
    $("#f-country").innerHTML = USER_COUNTRIES.map((c) => `<option>${c}</option>`).join("");
    $("#f-types").innerHTML = TYPES.map((x) => `<button type="button" class="chip" data-v="${x}">${x}</button>`).join("");

    $("#f-sector").addEventListener("click", (e) => {
      const b = e.target.closest(".chip"); if (!b) return;
      const v = b.dataset.v;
      state.sectors = state.sectors.includes(v) ? state.sectors.filter((x) => x !== v) : [...state.sectors, v];
      update();
    });
    $("#f-stage").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { state.stage = b.dataset.v; update(); } });
    $("#f-raise").addEventListener("input", (e) => { state.raise = +e.target.value; update(); });
    $("#f-country").addEventListener("change", (e) => { state.country = e.target.value; update(); });
    $("#f-types").addEventListener("click", (e) => {
      const b = e.target.closest(".chip"); if (!b) return;
      const cur = state.types || [...TYPES];
      const next = cur.includes(b.dataset.v) ? cur.filter((x) => x !== b.dataset.v) : [...cur, b.dataset.v];
      state.types = next.length === TYPES.length || !next.length ? null : next;
      update();
    });
    ["name", "pitch", "sender"].forEach((k) => $("#f-" + k).addEventListener("input", (e) => { state[k] = e.target.value.trim(); }));
    $("#f-reset").addEventListener("click", () => {
      Object.assign(state, { ...EXAMPLE, sectors: [...EXAMPLE.sectors], shown: 10 });
      update();
    });
    $("#r-more").addEventListener("click", () => { state.shown = state.shown >= results.length ? 10 : results.length; renderResults(false); });
    $("#r-export").addEventListener("click", exportCSV);
    $("#r-list").addEventListener("click", (e) => {
      const b = e.target.closest("[data-mail]"); if (b) openMail(results[+b.dataset.mail]);
      const s = e.target.closest("[data-save]");
      if (s) {
        const r = results[+s.dataset.save];
        if (inPipe(r.inv.name)) { pipeRemove(r.inv.name); toast("Removed from your pipeline"); }
        else { pipeAdd(r, "To contact"); toast(`${r.inv.name} saved to your pipeline`); }
        s.setAttribute("aria-pressed", inPipe(r.inv.name));
        s.textContent = inPipe(r.inv.name) ? "✓ Saved" : "☆ Save";
      }
    });
  }

  function syncForm() {
    document.querySelectorAll("#f-sector .chip").forEach((b) => b.setAttribute("aria-pressed", state.sectors.includes(b.dataset.v)));
    document.querySelectorAll("#f-stage button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.v === state.stage));
    document.querySelectorAll("#f-types .chip").forEach((b) => b.setAttribute("aria-pressed", !state.types || state.types.includes(b.dataset.v)));
    $("#f-raise").value = state.raise;
    $("#raise-val").textContent = eur(RAISE[state.raise]);
    $("#f-country").value = state.country;
  }

  function update() {
    state.shown = 10;
    syncForm();
    results = rank(state);
    renderResults(true);
  }

  // ------------------------------------------------------------------ results
  const CK_ICON = { yes: '<path d="M5 12.5l4.5 4.5L19 7.5"/>', part: '<path d="M6 12h12"/>', no: '<path d="M7 7l10 10M17 7L7 17"/>' };
  function ring(t) {
    const c = 2 * Math.PI * 26;
    return `<div class="ring ${tier(t)}"><svg viewBox="0 0 64 64"><circle class="track" cx="32" cy="32" r="26"/>
      <circle class="val" cx="32" cy="32" r="26" stroke-dasharray="${c}" stroke-dashoffset="${c}" data-off="${c * (1 - t / 100)}"/></svg><b>${t}%</b></div>`;
  }
  function renderResults(animate) {
    const strong = results.filter((r) => tier(r.total) === "hi").length, possible = results.filter((r) => tier(r.total) === "mid").length;
    $("#r-title").textContent = strong ? `${strong} strong matches for you` : "Your best matches";
    $("#r-sub").textContent = `${possible} more possible · ranked from ${results.length} verified investors`;
    const list = results.slice(0, state.shown);
    $("#r-list").innerHTML = list.map((r, i) => {
      const v = r.inv;
      return `<li class="card" style="animation-delay:${animate ? Math.min(i, 10) * 40 : 0}ms">
        ${ring(r.total)}
        <div>
          <div class="c-top"><span class="c-rank">#${i + 1}</span><span class="c-name">${esc(v.name)}</span></div>
          <div class="c-meta"><span class="cc">${CODES[v.country] || "–"}</span>${esc(v.type)} · ${esc(v.country)}</div>
          <div class="checks">${r.checks.map((c) => `<span class="ck ${c.k}"><svg viewBox="0 0 24 24">${CK_ICON[c.k]}</svg>${esc(c.t)}</span>`).join("")}</div>
          ${v.requirement ? `<div class="req">⚠ ${esc(v.requirement)}</div>` : ""}
          ${v.note ? `<div class="req">ⓘ ${esc(v.note)}</div>` : ""}
          ${v.description ? `<p class="desc">“${esc(v.description.length > 150 ? v.description.slice(0, 147).trim() + "…" : v.description)}”</p>` : ""}
        </div>
        <div class="c-actions">
          <button class="btn btn-primary btn-sm" type="button" data-mail="${i}">Write email</button>
          <button class="btn btn-ghost btn-sm btn-save" type="button" data-save="${i}" aria-pressed="${inPipe(v.name)}">${inPipe(v.name) ? "✓ Saved" : "☆ Save"}</button>
          <a class="btn btn-ghost btn-sm" href="${esc(v.website)}" target="_blank" rel="noopener">${esc(host(v.website))} ↗</a>
        </div>
      </li>`;
    }).join("");
    $("#r-more").textContent = state.shown >= results.length ? "Show top 10 only" : `Show all ${results.length}`;
    requestAnimationFrame(() => requestAnimationFrame(() =>
      document.querySelectorAll("#r-list .ring .val").forEach((c) => { c.style.strokeDashoffset = c.dataset.off; })));
  }

  function exportCSV() {
    const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const head = ["rank", "match_%", "investor", "type", "country", "stages", "ticket", "website", "public_inbox", "requirement", "field", "stage", "cheque", "location"];
    const rows = results.map((r, i) => [i + 1, r.total, r.inv.name, r.inv.type, r.inv.country, r.inv.stages.join(" / "),
      range(r.inv.ticket_min_eur, r.inv.ticket_max_eur), r.inv.website, r.inv.email, r.inv.requirement, ...r.checks.map((c) => c.t)].map(q).join(","));
    const blob = new Blob([[head.join(","), ...rows].join("\n")], { type: "text/csv" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "investor_shortlist.csv" });
    a.click(); URL.revokeObjectURL(a.href);
    toast("Shortlist downloaded");
  }

  // ------------------------------------------------------------------ email drafts
  function draft(r) {
    const v = r.inv, R = RAISE[state.raise];
    const me = state.sender || "[your name]", co = state.name || "[startup name]";
    const what = state.pitch || "[one line about what you build]";
    const reasons = [];
    if (r.overlap.length) reasons.push(`backs ${r.overlap.map(nice).join(" and ")}`);
    else if (v.health_specialist) reasons.push("focuses on health");
    if (r.parts.stage === 100) reasons.push(`invests at the ${state.stage.toLowerCase()} stage`);
    if (r.parts.cheque === 100 && v.ticket_min_eur != null) reasons.push(`writes cheques of ${range(v.ticket_min_eur, v.ticket_max_eur)}`);
    const why = reasons.length ? `I'm reaching out because ${v.name} ${reasons.join(", ").replace(/, ([^,]*)$/, " and $1")}.` : "";
    return {
      to: v.email,
      subject: `${state.name || "Intro"}: raising ${eur(R)} ${state.stage}${state.sectors.length ? " · " + state.sectors[0] : ""}`,
      body: `Hi ${v.name} team,\n\nI'm ${me}, founder of ${co}. We're building ${what}.\n\n${why}${why ? " " : ""}` +
        `We're raising ${eur(R)} at ${state.stage} and are based in ${state.country}.\n\n` +
        `Would you be open to a short call? Happy to send our deck.\n\nBest regards,\n${me}`,
    };
  }
  let mailFocus = null, mailFor = null;
  function openMail(r) {
    const d = draft(r);
    mailFocus = document.activeElement;
    mailFor = r;
    setStatus("#m-status", "");
    $("#m-title").textContent = r.inv.name;
    $("#m-kicker").textContent = `Email draft · ${r.total}% match`;
    $("#m-to").value = d.to;
    $("#m-to").placeholder = "No public inbox: use the contact form on their website";
    $("#m-subject").value = d.subject;
    $("#m-body").value = d.body;
    syncMailto();
    $("#scrim").hidden = false; $("#modal").hidden = false;
    $("#m-body").focus();
  }
  function closeMail() { $("#scrim").hidden = true; $("#modal").hidden = true; if (mailFocus) mailFocus.focus(); }
  function syncMailto() {
    $("#m-mail").href = `mailto:${encodeURIComponent($("#m-to").value)}?subject=${encodeURIComponent($("#m-subject").value)}&body=${encodeURIComponent($("#m-body").value)}`;
  }
  function initMail() {
    ["#m-to", "#m-subject", "#m-body"].forEach((s) => $(s).addEventListener("input", syncMailto));
    $("#m-close").addEventListener("click", closeMail);
    $("#scrim").addEventListener("click", closeMail);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#modal").hidden) closeMail(); });
    $("#m-copy").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(`Subject: ${$("#m-subject").value}\n\n${$("#m-body").value}`); toast("Draft copied"); }
      catch (e) { toast("Couldn't copy: select the text and copy it"); }
    });
    // sending = the real-life moment: log it in the pipeline (don't block the mailto link)
    $("#m-mail").addEventListener("click", () => {
      if (!mailFor) return;
      const name = mailFor.inv.name, cur = pipe.find((p) => p.name === name);
      if (!cur) pipeAdd(mailFor, "Emailed");
      else if (cur.status === "To contact") pipeMove(name, "Emailed");
      toast(`${name} → Emailed · follow-up in 7 days`);
      renderResults(false);
    });
    $("#m-ai").addEventListener("click", aiPersonalize);
  }
  let toastT;
  function toast(msg) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, 2200); }

  function setStatus(sel, msg, kind) { const s = $(sel); s.textContent = msg; s.className = "ai-status" + (kind ? " " + kind : ""); }

  // ------------------------------------------------------------------ storage (never required to work)
  const store = {
    get(k, session) { try { return JSON.parse((session ? sessionStorage : localStorage).getItem(k)); } catch (e) { return null; } },
    set(k, v, session) { try { (session ? sessionStorage : localStorage).setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; } },
    del(k, which) {
      try { if (which !== "session") localStorage.removeItem(k); } catch (e) {}
      try { if (which !== "local") sessionStorage.removeItem(k); } catch (e) {}
    },
  };

  // ------------------------------------------------------------------ AI (Gemini, bring your own key)
  // Calls go straight from this browser to Google; the key is never sent anywhere else.
  const MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"];
  const KEY = "ifinder-gemini-key";
  let memKey = "";
  const getKey = () => ($("#ai-key").value.trim() || memKey || store.get(KEY) || store.get(KEY, true) || "");

  // remembered = localStorage; otherwise only for this tab (sessionStorage)
  function rememberKey() {
    const k = $("#ai-key").value.trim() || memKey;
    if (!k) return;
    memKey = k;
    if ($("#ai-remember").checked) { store.set(KEY, k); store.del(KEY, "session"); }
    else { store.set(KEY, k, true); store.del(KEY, "local"); }
    $("#ai-forget").hidden = false;
  }

  async function gemini(system, user, { schema = null, url = false } = {}) {
    const key = getKey();
    if (!key) throw new Error("NO_KEY");
    let last = new Error("No Gemini model was available for this key.");
    for (const model of MODELS) {
      const body = {
        systemInstruction: { parts: [{ text: system }] },
        contents: [{ role: "user", parts: [{ text: user }] }],
        // JSON mode and tools can't be combined, so the URL path parses JSON out of plain text
        generationConfig: url ? { temperature: 0.2 } : { temperature: 0.3, responseMimeType: "application/json", ...(schema ? { responseSchema: schema } : {}) },
        ...(url ? { tools: [{ url_context: {} }] } : {}),
      };
      let res;
      try {
        res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
          method: "POST", headers: { "Content-Type": "application/json", "x-goog-api-key": key }, body: JSON.stringify(body) });
      } catch (e) { throw new Error("Couldn't reach Gemini. Check your connection."); }
      if (res.status === 404) { last = new Error(`Model ${model} isn't available.`); continue; }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = (data.error && data.error.message) || `HTTP ${res.status}`;
        if (/api key/i.test(msg) || res.status === 401 || res.status === 403) throw new Error("Gemini rejected this API key. Check it at aistudio.google.com/apikey.");
        if (res.status === 429) throw new Error("Free-tier limit reached for now. Wait a minute and try again.");
        throw new Error(msg);
      }
      const text = ((data.candidates && data.candidates[0] && data.candidates[0].content && data.candidates[0].content.parts) || [])
        .map((p) => p.text || "").join("");
      const a = text.indexOf("{"), b = text.lastIndexOf("}");
      if (a < 0 || b < a) throw new Error("The AI reply had no usable answer. Try again.");
      try { return JSON.parse(text.slice(a, b + 1)); } catch (e) { throw new Error("The AI reply was malformed. Try again."); }
    }
    throw last;
  }

  const FILL_SYSTEM = `You read a startup description (or the startup's website) and extract its fundraising profile.
Use ONLY facts stated in the source. Never guess numbers. Unknown fields must be null.
Return JSON: {"name": string|null, "one_liner": string|null (what they build, max 15 words, starts with a lowercase verb or noun phrase),
"sectors": array of zero or more of ${JSON.stringify(SECTORS)},
"stage": one of ${JSON.stringify(STAGES)} or null, "raise_eur": number|null, "country": one of ${JSON.stringify(USER_COUNTRIES)} or null}`;
  const FILL_SCHEMA = { type: "OBJECT", properties: {
    name: { type: "STRING", nullable: true }, one_liner: { type: "STRING", nullable: true },
    sectors: { type: "ARRAY", items: { type: "STRING", enum: SECTORS } },
    stage: { type: "STRING", enum: STAGES, nullable: true }, raise_eur: { type: "NUMBER", nullable: true },
    country: { type: "STRING", enum: USER_COUNTRIES, nullable: true } }, required: ["sectors"] };

  function applyProfile(p) {
    const filled = [];
    const sectors = (p.sectors || []).filter((s) => SECTORS.includes(s));
    if (sectors.length) { state.sectors = sectors; filled.push("field"); }
    if (STAGES.includes(p.stage)) { state.stage = p.stage; filled.push("stage"); }
    if (typeof p.raise_eur === "number" && p.raise_eur > 0) {
      state.raise = RAISE.reduce((best, v, i) => (Math.abs(Math.log(v / p.raise_eur)) < Math.abs(Math.log(RAISE[best] / p.raise_eur)) ? i : best), 0);
      filled.push("raise");
    }
    if (USER_COUNTRIES.includes(p.country)) { state.country = p.country; filled.push("country"); }
    if (p.name) { state.name = p.name; $("#f-name").value = p.name; filled.push("name"); }
    if (p.one_liner) { state.pitch = p.one_liner; $("#f-pitch").value = p.one_liner; filled.push("pitch"); }
    update();
    return filled;
  }

  async function aiFill() {
    const text = $("#ai-text").value.trim();
    if (!text) { setStatus("#ai-status", "Write a few lines about your startup first.", "err"); return; }
    if (!getKey()) { setStatus("#ai-status", "Paste your free Gemini key first.", "err"); $("#ai-key").focus(); return; }
    rememberKey();
    const isUrl = /^https?:\/\/\S+$/i.test(text) || /^[\w-]+(\.[\w-]+)+(\/\S*)?$/.test(text);
    const btn = $("#ai-fill"); btn.disabled = true;
    setStatus("#ai-status", isUrl ? "Reading your website…" : "Reading your description…");
    try {
      const src = isUrl ? `Startup website: ${/^https?:/i.test(text) ? text : "https://" + text}` : `Startup description:\n${text}`;
      const p = await gemini(FILL_SYSTEM, src, isUrl ? { url: true } : { schema: FILL_SCHEMA });
      const filled = applyProfile(p);
      setStatus("#ai-status", filled.length ? `Filled: ${filled.join(", ")}. Check it, then look at your list →` : "Couldn't find usable details. Try a longer description.", filled.length ? "ok" : "err");
    } catch (e) {
      setStatus("#ai-status", e.message === "NO_KEY" ? "Paste your free Gemini key first." : e.message, "err");
    } finally { btn.disabled = false; }
  }

  const MAIL_SYSTEM = `You write short cold emails from a startup founder to an investor.
Use ONLY the facts given. Never invent traction, metrics, customers, team details or portfolio companies.
If the founder's name, startup name or pitch is missing, keep a [bracketed placeholder].
120-160 words, plain professional English, no hype words, one specific reason this investor fits,
end with a soft ask for a short call. Return JSON {"subject": string, "body": string}.`;

  async function aiPersonalize() {
    if (!mailFor) return;
    if (!getKey()) {
      setStatus("#m-status", "Add your free Gemini key in “Let AI fill this in” (in the finder) first.", "err");
      return;
    }
    const r = mailFor, v = r.inv, btn = $("#m-ai");
    btn.disabled = true; setStatus("#m-status", "Writing a personal draft…");
    const facts = {
      founder: { name: state.sender || null, startup: state.name || null, what_we_build: state.pitch || null,
        sectors: state.sectors, stage: state.stage, raising: eur(RAISE[state.raise]), based_in: state.country },
      investor: { name: v.name, type: v.type, country: v.country, focus: v.focus, stages: v.stages,
        typical_cheque: range(v.ticket_min_eur, v.ticket_max_eur), in_their_own_words: v.description || null },
      why_they_match: r.checks.filter((c) => c.k === "yes").map((c) => c.t),
    };
    try {
      const out = await gemini(MAIL_SYSTEM, JSON.stringify(facts, null, 1), {
        schema: { type: "OBJECT", properties: { subject: { type: "STRING" }, body: { type: "STRING" } }, required: ["subject", "body"] } });
      if (!out.subject || !out.body) throw new Error("The AI reply was incomplete. Try again.");
      $("#m-subject").value = out.subject; $("#m-body").value = out.body; syncMailto();
      setStatus("#m-status", "Personalized. Read it once before sending: AI can still be wrong.", "ok");
    } catch (e) { setStatus("#m-status", e.message, "err"); }
    finally { btn.disabled = false; }
  }

  function initAI() {
    const saved = store.get(KEY) || store.get(KEY, true);
    if (saved) { memKey = saved; $("#ai-key").placeholder = "Key saved ✓ (paste a new one to replace)"; $("#ai-forget").hidden = false; $("#ai-remember").checked = !!store.get(KEY); }
    $("#ai-fill").addEventListener("click", aiFill);
    $("#ai-key").addEventListener("change", rememberKey);
    $("#ai-remember").addEventListener("change", rememberKey);
    $("#ai-forget").addEventListener("click", () => {
      store.del(KEY); memKey = ""; $("#ai-key").value = ""; $("#ai-key").placeholder = "Paste your key";
      $("#ai-forget").hidden = true; setStatus("#ai-status", "Key removed from this browser.", "ok");
    });
  }

  // ------------------------------------------------------------------ pipeline tracker
  const COLS = [["To contact", "var(--muted)"], ["Emailed", "var(--accent)"], ["Replied", "#eda100"], ["Meeting", "var(--good)"], ["Passed", "var(--lo)"]];
  const PIPE_KEY = "ifinder-pipeline";
  const FOLLOW_DAYS = { Emailed: 7, Replied: 3 };
  const today = () => new Date().toISOString().slice(0, 10);
  const addDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
  let pipe = store.get(PIPE_KEY) || [];
  const inPipe = (name) => pipe.some((p) => p.name === name);
  const savePipe = () => { if (!store.set(PIPE_KEY, pipe)) toast("Couldn't save in this browser: export your pipeline to keep it"); renderPipe(); };

  function pipeAdd(r, status) {
    if (inPipe(r.inv.name)) return;
    pipe.push({ name: r.inv.name, type: r.inv.type, country: r.inv.country, website: r.inv.website, email: r.inv.email,
      match: r.total, status, follow: FOLLOW_DAYS[status] ? addDays(FOLLOW_DAYS[status]) : "", notes: "",
      history: [{ status, date: today() }] });
    savePipe();
  }
  function pipeRemove(name) { pipe = pipe.filter((p) => p.name !== name); savePipe(); renderResults(false); }
  function pipeMove(name, status) {
    const p = pipe.find((x) => x.name === name); if (!p || p.status === status) return;
    p.status = status; p.history.push({ status, date: today() });
    p.follow = FOLLOW_DAYS[status] ? addDays(FOLLOW_DAYS[status]) : (status === "Passed" ? "" : p.follow);
    savePipe();
  }
  const dueState = (p) => (!p.follow || p.status === "Passed" ? "" : p.follow < today() ? "overdue" : p.follow === today() ? "today" : "");

  function renderPipe() {
    const due = pipe.filter((p) => dueState(p)).length;
    const nc = $("#nav-count");
    nc.hidden = !pipe.length; nc.textContent = due || pipe.length; nc.classList.toggle("due", !!due);
    nc.title = due ? `${due} follow-ups due` : `${pipe.length} saved`;
    $("#p-empty").hidden = pipe.length > 0;
    $("#board").hidden = !pipe.length;
    document.querySelector(".pipe-bar").hidden = !pipe.length;
    const active = pipe.filter((p) => p.status !== "Passed").length, meetings = pipe.filter((p) => p.status === "Meeting").length;
    $("#p-stats").innerHTML = `<span class="pill"><b>${pipe.length}</b> saved</span><span class="pill"><b>${active}</b> active</span>` +
      `<span class="pill"><b>${meetings}</b> meeting${meetings === 1 ? "" : "s"}</span>` + (due ? `<span class="pill due">${due} follow-up${due > 1 ? "s" : ""} due</span>` : "");
    $("#board").innerHTML = COLS.map(([col, color]) => {
      const items = pipe.filter((p) => p.status === col);
      return `<div class="col" data-col="${col}">
        <div class="col-head"><span><i class="dot" style="background:${color}"></i>${col}</span><span>${items.length}</span></div>
        <div class="col-list">${items.length ? items.map(pcard).join("") : `<div class="col-empty">Drop here</div>`}</div>
      </div>`;
    }).join("");
  }
  function pcard(p) {
    const d = dueState(p);
    return `<article class="pcard" draggable="true" data-name="${esc(p.name)}">
      <div class="p-top"><span class="p-name">${esc(p.name)}</span><span class="p-match">${p.match}%</span></div>
      <div class="p-meta">${esc(p.type)} · ${esc(p.country)}</div>
      ${d ? `<span class="p-due ${d === "today" ? "today" : ""}">${d === "today" ? "Follow up today" : "Follow-up overdue"}</span>` : ""}
      ${p.status !== "Passed" ? `<label class="p-follow">Follow up <input type="date" value="${p.follow}" data-follow></label>` : ""}
      <textarea placeholder="Notes: who you spoke to, next step…" data-notes>${esc(p.notes)}</textarea>
      <div class="p-actions">
        <select data-status aria-label="Move ${esc(p.name)} to">${COLS.map(([c]) => `<option${c === p.status ? " selected" : ""}>${c}</option>`).join("")}</select>
        <button class="mini" type="button" data-pmail>Email</button>
        <button class="mini x" type="button" data-premove aria-label="Remove ${esc(p.name)}">✕</button>
      </div>
    </article>`;
  }

  function exportPipe() {
    const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const head = ["investor", "status", "match_%", "follow_up", "notes", "type", "country", "website", "public_inbox", "history"];
    const rows = pipe.map((p) => [p.name, p.status, p.match, p.follow, p.notes, p.type, p.country, p.website, p.email,
      p.history.map((h) => `${h.date} ${h.status}`).join(" → ")].map(q).join(","));
    const blob = new Blob([[head.join(","), ...rows].join("\n")], { type: "text/csv" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "investor_pipeline.csv" });
    a.click(); URL.revokeObjectURL(a.href);
    toast("Pipeline downloaded");
  }

  function initPipe() {
    const board = $("#board");
    const nameOf = (el) => el.closest(".pcard") && el.closest(".pcard").dataset.name;
    board.addEventListener("change", (e) => {
      const name = nameOf(e.target); if (!name) return;
      const p = pipe.find((x) => x.name === name);
      if (e.target.matches("[data-status]")) { pipeMove(name, e.target.value); toast(`${name} → ${e.target.value}`); }
      if (e.target.matches("[data-follow]")) { p.follow = e.target.value; savePipe(); }
    });
    board.addEventListener("input", (e) => {   // notes save quietly, without re-rendering under the cursor
      if (!e.target.matches("[data-notes]")) return;
      const p = pipe.find((x) => x.name === nameOf(e.target)); p.notes = e.target.value; store.set(PIPE_KEY, pipe);
    });
    board.addEventListener("click", (e) => {
      const name = nameOf(e.target); if (!name) return;
      if (e.target.matches("[data-premove]")) { pipeRemove(name); toast(`${name} removed`); }
      if (e.target.matches("[data-pmail]")) {
        const inv = INV.find((i) => i.name === name);
        if (inv) openMail(score(inv, state));
      }
    });
    board.addEventListener("dragstart", (e) => {
      const c = e.target.closest(".pcard"); if (!c) return;
      e.dataTransfer.setData("text/plain", c.dataset.name); e.dataTransfer.effectAllowed = "move"; c.classList.add("dragging");
    });
    board.addEventListener("dragend", (e) => { const c = e.target.closest(".pcard"); if (c) c.classList.remove("dragging"); });
    board.addEventListener("dragover", (e) => {
      const col = e.target.closest(".col"); if (!col) return;
      e.preventDefault(); board.querySelectorAll(".col.over").forEach((c) => c !== col && c.classList.remove("over")); col.classList.add("over");
    });
    board.addEventListener("dragleave", (e) => { const col = e.target.closest(".col"); if (col && !col.contains(e.relatedTarget)) col.classList.remove("over"); });
    board.addEventListener("drop", (e) => {
      const col = e.target.closest(".col"); if (!col) return;
      e.preventDefault(); col.classList.remove("over");
      const name = e.dataTransfer.getData("text/plain");
      if (name) { pipeMove(name, col.dataset.col); toast(`${name} → ${col.dataset.col}`); }
    });
    $("#p-export").addEventListener("click", exportPipe);
    $("#p-clear").addEventListener("click", () => {
      if (!confirm("Remove every investor from your pipeline? Export it first if you want a copy.")) return;
      pipe = []; savePipe(); renderResults(false); toast("Pipeline cleared");
    });
    renderPipe();
  }

  // ------------------------------------------------------------------ hero swarm
  function swarm() {
    const svg = $("#swarm"), NS = "http://www.w3.org/2000/svg";
    const ranked = rank({ ...EXAMPLE, sectors: [...EXAMPLE.sectors] });
    let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    const scatter = ranked.map(() => [14 + rnd() * 372, 14 + rnd() * 212]);
    const cols = 11, gap = 35, x0 = 25, y0 = 22;
    const dots = ranked.map((r, i) => {
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("r", 7); c.setAttribute("cx", scatter[i][0]); c.setAttribute("cy", scatter[i][1]);
      c.style.fill = "var(--lo)";
      svg.appendChild(c);
      return c;
    });
    const labels = ranked.slice(0, 3).map((r, i) => {
      const t = document.createElementNS(NS, "text");
      t.setAttribute("x", 6); t.setAttribute("y", 268 + i * 22); t.style.opacity = 0;
      t.textContent = `${i + 1}. ${r.inv.name} · ${r.total}%`;
      svg.appendChild(t);
      return t;
    });
    const lab = $("#swarm-label");
    let sorted = false;
    function sort() {
      ranked.forEach((r, i) => {
        const d = dots[i];
        d.setAttribute("cx", x0 + (i % cols) * gap); d.setAttribute("cy", y0 + Math.floor(i / cols) * 27);
        d.style.fill = `var(--${tier(r.total)})`; d.setAttribute("r", i < 3 ? 9 : 7);
      });
      labels.forEach((t) => { t.style.opacity = 1; });
      lab.textContent = `Ranked for an example: digital health · Seed · €1M · Germany`;
      sorted = true;
    }
    function unsort() {
      dots.forEach((d, i) => { d.setAttribute("cx", scatter[i][0]); d.setAttribute("cy", scatter[i][1]); d.style.fill = "var(--lo)"; d.setAttribute("r", 7); });
      labels.forEach((t) => { t.style.opacity = 0; });
      lab.textContent = `${ranked.length} investors, unsorted`;
      sorted = false;
    }
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { sort(); return; }
    setTimeout(sort, 1200);
    setInterval(() => { sorted ? unsort() : sort(); }, 4200);
  }

  // ------------------------------------------------------------------ proof + data
  function renderProof() {
    if (!PROOF) { $("#proof").hidden = true; return; }
    const tool = Math.round(PROOF.held_out * 10), self = Math.round(PROOF.noise_ceiling * 10);
    $("#proof-text").innerHTML =
      `We tested the method on ${PROOF.n_test_profiles} practice investor profiles against an expert's shortlist, tuning on one half and testing on the half it had never seen, ${PROOF.n_splits} times over. ` +
      `About <b>${tool} in 10</b> of the tool's top picks were also the expert's. When the expert re-did their own shortlist, they agreed with themselves about <b>${self} in 10</b> times. ` +
      `So the ranking is as consistent as the expert, in seconds instead of weeks.`;
    $("#proof-tech").innerHTML = [
      `Held-out precision ${Math.round(PROOF.held_out * 100)}% ± ${Math.round(PROOF.held_out_std * 100)}% over ${PROOF.n_splits} stratified 50/50 splits.`,
      `Expert re-run agreement (noise ceiling): ${Math.round(PROOF.noise_ceiling * 100)}%. Past this, tuning only fits the expert's gut feel.`,
      `Tuning and testing on the same data looked like ${Math.round(PROOF.in_sample_best * 100)}%; the ${Math.round(PROOF.optimism_gap * 100)}-point gap was overfitting, so the simpler hand-set weights are used here.`,
      `ROC-AUC ${PROOF.roc_auc.toFixed(2)} at separating the expert's picks from the rest.`,
      `The practice profiles and the expert were simulated so the test could be repeated; the ${INV.length} investors in the finder are real and scored on the same four questions.`,
    ].map((x) => `<li>${x}</li>`).join("");
    const matchAt = [0, 1, 2, 4, 5, 7, 8, 3, 6, 9].slice(0, tool);
    const dotsA = [], dotsB = [];
    for (let i = 0; i < 10; i++) {
      const m = matchAt.includes(i);
      dotsA.push(`<i class="${m ? "match" : ""}" style="transition-delay:${i * 50}ms"></i>`);
      dotsB.push(`<i class="${m ? "match" : ""}" style="transition-delay:${300 + i * 50}ms"></i>`);
    }
    $("#pv-a").innerHTML = dotsA.join(""); $("#pv-b").innerHTML = dotsB.join("");
    $("#pv-links").innerHTML = matchAt.map((i) => { const x = ((i + 0.5) / 10) * 400; return `<line x1="${x}" y1="4" x2="${x}" y2="56" style="transition-delay:${700 + i * 60}ms"/>`; }).join("");
    $("#pv-n").textContent = tool;
    $("#pv-self").textContent = self;
  }

  function bars(el, entries) {
    const max = Math.max(...entries.map((e) => e[1]));
    $(el).innerHTML = entries.map(([k, v]) => `<div class="bar"><span title="${esc(k)}">${esc(k)}</span><span class="tr"><span class="fl" data-w="${(v / max) * 100}"></span></span><b>${v}</b></div>`).join("");
  }
  function renderData() {
    const count = (arr) => Object.entries(arr.reduce((m, k) => ((m[k] = (m[k] || 0) + 1), m), {})).sort((a, b) => b[1] - a[1]);
    const byCountry = count(INV.map((i) => i.country));
    const top = byCountry.slice(0, 6), rest = byCountry.slice(6).reduce((s, e) => s + e[1], 0);
    bars("#d-country", rest ? [...top, [`Other (${byCountry.length - 6})`, rest]] : top);
    bars("#d-type", count(INV.map((i) => i.type)));
    bars("#d-stage", STAGES.map((s) => [s, INV.filter((i) => i.stages.includes(s)).length]));
    const n = INV.length, nc = byCountry.length;
    ["#n-inv", "#n-inv2"].forEach((s) => { $(s).textContent = n; });
    $("#n-countries").textContent = nc;
  }

  // ------------------------------------------------------------------ chrome
  function chrome() {
    $("#theme-toggle").addEventListener("click", () => {
      const root = document.documentElement;
      const dark = root.getAttribute("data-theme") === "dark" || (!root.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
      root.setAttribute("data-theme", dark ? "light" : "dark");
      try { localStorage.setItem("ifinder-theme", dark ? "light" : "dark"); } catch (e) {}
    });
    const bar = $("#progress");
    addEventListener("scroll", () => {
      const h = document.documentElement.scrollHeight - innerHeight;
      bar.style.width = (h > 0 ? (scrollY / h) * 100 : 0) + "%";
    }, { passive: true });
    if (!("IntersectionObserver" in window)) {
      document.querySelectorAll(".reveal").forEach((n) => n.classList.add("in"));
      document.querySelectorAll(".fl").forEach((f) => { f.style.width = f.dataset.w + "%"; });
      return;
    }
    const links = [...document.querySelectorAll(".nav-links a")];
    const spy = new IntersectionObserver((es) => es.forEach((e) => {
      if (e.isIntersecting) links.forEach((a) => a.classList.toggle("on", a.getAttribute("href") === "#" + e.target.id));
    }), { rootMargin: "-45% 0px -50% 0px" });
    document.querySelectorAll("main section[id]").forEach((s) => spy.observe(s));
    const rev = new IntersectionObserver((es) => es.forEach((e) => {
      if (!e.isIntersecting) return;
      e.target.classList.add("in");
      e.target.querySelectorAll(".fl").forEach((f) => { f.style.width = f.dataset.w + "%"; });
      rev.unobserve(e.target);
    }), { rootMargin: "0px 0px -10% 0px" });
    document.querySelectorAll(".reveal").forEach((n) => rev.observe(n));
  }
  // ------------------------------------------------------------------ boot
  buildForm();
  initMail();
  initAI();
  initPipe();
  update();
  renderProof();
  renderData();
  swarm();
  chrome();
})();
