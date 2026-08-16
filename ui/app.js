// Upwork Knowledge Assistant — Production UI (REQ-006, REQ-007).
//
// Behaviour summary:
//   * On boot, fetch `/v1/identity` to learn brand + accent + auth state.
//   * If `auth_enabled` is true, surface a token input; persist the token
//     in localStorage and send it as `Authorization: Bearer …` on every
//     API call. Never write the token into the URL, never log it.
//   * Populate the collection selector from `/v1/collections`.
//   * Submit a question via `POST /v1/query` and render one of three
//     explicit states — `answered` (with citations), `refused`
//     (`reason=insufficient_evidence`), or `error` (network/server).
//   * Expose a small `data-ui` marker + `data-identity` JSON attribute on
//     the document so the smoke checks can assert the UI booted.
//
// The script is framework-free so it stays inside a single static bundle
// (nginx serves only HTML/CSS/JS — no Node, no build step). It is also
// defensive: any failure renders a visible error rather than silently
// hanging the page.

(function () {
  "use strict";

  // ----- DOM ------------------------------------------------------------
  var els = {
    pageTitle:      document.getElementById("page-title"),
    brandName:      document.getElementById("brand-name"),
    brandLogo:      document.getElementById("brand-logo"),
    subtitle:       document.getElementById("subtitle"),
    footerNote:     document.getElementById("footer-note"),
    authPill:       document.getElementById("auth-pill"),
    authToggle:     document.getElementById("auth-toggle"),
    authPanel:      document.getElementById("auth-panel"),
    authToken:      document.getElementById("auth-token"),
    authSave:       document.getElementById("auth-save"),
    authClear:      document.getElementById("auth-clear"),
    authMsg:        document.getElementById("auth-msg"),
    workspaceCurrent: document.getElementById("workspace-current"),
    workspaceInput:   document.getElementById("workspace-input"),
    workspaceApply:   document.getElementById("workspace-apply"),
    collection:     document.getElementById("collection-select"),
    question:       document.getElementById("question"),
    ask:            document.getElementById("ask"),
    clear:          document.getElementById("clear"),
    status:         document.getElementById("status"),
    answer:         document.getElementById("answer"),
    answerState:    document.getElementById("answer-state"),
    citations:      document.getElementById("citations"),
  };

  // ----- Constants ------------------------------------------------------
  var TOKEN_KEY = "upworkkb.bearer.v1";
  var WORKSPACE_KEY = "upworkkb.workspace.v1";
  var DEFAULT_WORKSPACE = "default";
  var WORKSPACE_PATTERN = /^[a-zA-Z0-9._-]{1,64}$/;
  // Workspace resolution order: URL query (?workspace=) wins, then
  // localStorage, then the dev default. The workspace switcher in the
  // toolbar persists the choice to localStorage.
  function readWorkspace() {
    try {
      var url = new URL(window.location.href);
      var q = url.searchParams.get("workspace");
      if (q && WORKSPACE_PATTERN.test(q)) return q;
      var stored = window.localStorage.getItem(WORKSPACE_KEY);
      if (stored && WORKSPACE_PATTERN.test(stored)) return stored;
    } catch (_e) { /* fall through */ }
    return DEFAULT_WORKSPACE;
  }
  function writeWorkspace(value) {
    try {
      if (value && WORKSPACE_PATTERN.test(value)) {
        window.localStorage.setItem(WORKSPACE_KEY, value);
      }
    } catch (_e) { /* noop */ }
  }
  var WORKSPACE = readWorkspace();

  // ----- State ----------------------------------------------------------
  var state = {
    identity: null,
    collections: [],
    pending: false,
    lastQuestion: null, // M-2: last submitted question (for retry).
    lastError: null,    // M-2: last rendered error (for retry).
  };

  // M-4: configurable citation-collapse thresholds. We collapse the
  // overflow of citations when the answer carries more than the
  // "expandTop" count; on mobile we keep only the top one expanded to
  // free vertical real estate. The thresholds are exposed as a window
  // global so the E2E tests can pin them deterministically.
  function getCitationCollapseMode() {
    var defaults = { expandTop: 3, collapseAfter: 3 };
    var mobile = { expandTop: 1, collapseAfter: 1 };
    var cfg = (window.UPWORKKB_CITATION_LAYOUT === "expand-all")
      ? { expandTop: 9999, collapseAfter: 9999 }
      : (window.UPWORKKB_CITATION_LAYOUT === "collapse-desktop")
        ? defaults
        : defaults;
    // Mobile browsers expose a narrow viewport — combine with the
    // user-agent signal so the rules are robust to resize.
    var isMobile = (typeof window.matchMedia === "function" &&
      window.matchMedia("(max-width: 520px)").matches);
    return isMobile ? mobile : cfg;
  }

  // M-1: convert inline `[N]` markers in the server-rendered answer
  // body into anchor links that jump to the matching citation card.
  // We do this on the already-escaped HTML string so the server text
  // remains the source of truth and we never re-introduce raw HTML.
  function linkifyInlineCitations(answerHtml, citations) {
    if (!answerHtml || !citations || !citations.length) return answerHtml;
    var max = citations.length;
    // Match "[N]" where N is 1..max, but not part of a longer
    // alphanumeric token (e.g. version-like "[v1.2]" or "[N/A]").
    // Non-greedy, scoped to single digits 1..9 OR multi-digit 1..max.
    var re = /\[(\d{1,2})\]/g;
    return answerHtml.replace(re, function (m, numStr) {
      var n = parseInt(numStr, 10);
      if (n < 1 || n > max) return m;
      return '<a class="citation-link" href="#citation-' + n + '">[' + n + ']</a>';
    });
  }

  // Pluralisation helper. `"1 citation"` / `"2 citations"` so the
  // overflow <summary> and the post-answer status line read correctly
  // without the awkward `"citation(s)"` placeholder.
  function pluralize(n, singular, plural) {
    return n + " " + (n === 1 ? singular : (plural || singular + "s"));
  }

  // M-4: collapse overflow citations inside a <details>/<summary> for
  // long-answer responses. Top `expandTop` are always expanded; the
  // rest collapse under "Show N more citation(s)".
  function buildOverflowHtml(extraCitations, totalExtra) {
    if (!extraCitations.length || totalExtra < 1) return "";
    return (
      '<details class="citations-overflow">' +
        '<summary>Show ' + pluralize(totalExtra, "more citation", "more citations") + '</summary>' +
        '<ol class="citations citations-overflow-list">' +
          extraCitations.join("") +
        '</ol>' +
      '</details>'
    );
  }

  function collapseCitations(items) {
    var mode = getCitationCollapseMode();
    if (items.length <= mode.collapseAfter) {
      return items.join("");
    }
    var expanded = items.slice(0, mode.expandTop);
    var extra = items.slice(mode.expandTop);
    return expanded.join("") + buildOverflowHtml(extra, extra.length);
  }

  // ----- Helpers --------------------------------------------------------
  function escapeText(value) {
    if (value == null) return "";
    return String(value);
  }

  function escapeAttr(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function setStatus(message, kind) {
    if (!els.status) return;
    els.status.textContent = message;
    els.status.dataset.kind = kind || "info";
  }

  function setAuthMsg(message, kind) {
    if (!els.authMsg) return;
    els.authMsg.textContent = message;
    els.authMsg.dataset.kind = kind || "info";
  }

  function apiHeaders(extra) {
    var headers = Object.assign({ "Accept": "application/json" }, extra || {});
    var token = readToken();
    if (token) {
      headers["Authorization"] = "Bearer " + token;
    }
    return headers;
  }

  function readToken() {
    try {
      return window.localStorage.getItem(TOKEN_KEY) || "";
    } catch (_e) {
      return "";
    }
  }

  function writeToken(value) {
    try {
      if (value) {
        window.localStorage.setItem(TOKEN_KEY, value);
      } else {
        window.localStorage.removeItem(TOKEN_KEY);
      }
    } catch (_e) { /* localStorage disabled — surface banner later */ }
  }

  // ----- API calls ------------------------------------------------------
  function fetchJson(path, init) {
    init = init || {};
    init.headers = apiHeaders(
      Object.assign({ "Content-Type": "application/json" }, init.headers || {})
    );
    return fetch(path, init).then(function (resp) {
      var ct = resp.headers.get("content-type") || "";
      var body = ct.indexOf("application/json") !== -1 ? resp.json() : resp.text();
      return body.then(function (data) {
        if (!resp.ok) {
          var detail =
            (data && data.error && data.error.message) ||
            (typeof data === "string" ? data : "") ||
            ("HTTP " + resp.status);
          var err = new Error(detail);
          err.status = resp.status;
          err.payload = data;
          throw err;
        }
        return data;
      });
    });
  }

  // ----- Renderers ------------------------------------------------------
  function applyIdentity(identity) {
    state.identity = identity;
    var brandName = escapeText(identity.brand_name || "Upwork Knowledge Assistant");
    if (els.pageTitle) els.pageTitle.textContent = brandName;
    if (els.brandName) els.brandName.textContent = brandName;
    if (els.subtitle)  els.subtitle.textContent  = identity.tagline || "";
    if (els.footerNote) els.footerNote.textContent = identity.footer_note || "";

    // Accent colour — server-side validated but we re-check defensively.
    var accent = (identity.accent_color || "").trim();
    if (/^(?:#[0-9a-fA-F]{3,8}|rgba?\([^)]+\))$/.test(accent)) {
      document.documentElement.style.setProperty("--accent", accent);
    }

    if (identity.logo_url && els.brandLogo) {
      els.brandLogo.src = identity.logo_url;
      els.brandLogo.hidden = false;
    } else if (els.brandLogo) {
      els.brandLogo.hidden = true;
    }

    // Auth gate UI.
    var authOn = !!identity.auth_enabled;
    if (els.authPill) {
      els.authPill.hidden = false;
      els.authPill.textContent = authOn ? "Auth required" : "Auth disabled";
      els.authPill.classList.toggle("pill-warn", authOn);
      els.authPill.classList.toggle("pill-muted", !authOn);
    }
    if (els.authToggle) {
      els.authToggle.hidden = !authOn;
    }
    // When auth is required, surface the bearer panel immediately so the
    // user knows they need to set a token before querying. The button
    // toggles it thereafter.
    if (els.authPanel) {
      els.authPanel.hidden = !authOn;
    }

    // Workspace switcher: surface the active workspace id.
    if (els.workspaceCurrent) {
      els.workspaceCurrent.textContent = WORKSPACE;
    }
    if (els.workspaceInput && !els.workspaceInput.value) {
      els.workspaceInput.value = WORKSPACE;
    }

    // Surface identity on the root element for smoke checks.
    document.documentElement.setAttribute("data-identity", "ready");
    document.documentElement.setAttribute(
      "data-auth-enabled",
      authOn ? "true" : "false"
    );
    document.documentElement.setAttribute(
      "data-workspace",
      WORKSPACE
    );
  }

  function renderCollections(collections) {
    state.collections = collections || [];
    if (!els.collection) return;
    if (!state.collections.length) {
      els.collection.innerHTML = '<option value="">— no collections —</option>';
      // M-3: actionable empty state when the current workspace has no
      // collections. The pill/placeholder together tell the user the
      // workspace is empty and propose two concrete next steps.
      renderEmptyCollection();
      return;
    }
    var html = state.collections.map(function (c) {
      var label = c.name + " (" + (c.chunk_count || 0) + " chunks)";
      return (
        '<option value="' + escapeAttr(String(c.id)) + '">' +
        escapeHtml(label) + "</option>"
      );
    });
    els.collection.innerHTML = html.join("");
    // Leaving the empty-state placeholder behind is fine because the
    // next renderAnswered() / renderIdle() replaces the answer card.
  }

  // M-3: render an actionable empty-state placeholder in the answer
  // card when the workspace has no collections. The status line carries
  // the same message so a screen reader announces both.
  function renderEmptyCollection() {
    setAnswerState("empty");
    if (els.answer) {
      els.answer.hidden = false;
      els.answer.classList.remove("placeholder", "placeholder-error", "placeholder-refused");
      els.answer.innerHTML = (
        '<p class="empty-state" id="empty-state">' +
          '<strong>This workspace has no collections yet.</strong> ' +
          'You can pick another workspace from the switcher below, or ' +
          'ingest a document via the <code>POST /v1/ingest</code> API.' +
        '</p>'
      );
    }
    if (els.citations) {
      els.citations.hidden = true;
      els.citations.innerHTML = "";
    }
    if (els.status) {
      els.status.textContent =
        "This workspace has no collections yet — pick another workspace or ingest via the API.";
      els.status.dataset.kind = "warn";
    }
    // M-3: open the workspace switcher so the user can switch without
    // hunting for the disclosure.
    var ws = document.querySelector(".ws-switcher");
    if (ws) ws.open = true;
  }

  function setAnswerState(s) {
    if (!els.answerState) return;
    els.answerState.dataset.state = s;
  }

  function renderIdle() {
    setAnswerState("idle");
    els.answer.hidden = false;
    els.answer.textContent =
      "Pick a collection, type a question, and press Ask. " +
      "Answers come with citations you can verify.";
    els.answer.classList.remove("placeholder-error", "placeholder-refused");
    els.answer.classList.add("placeholder");
    els.citations.hidden = true;
    els.citations.innerHTML = "";
  }

  // M-2: renderError accepts an options object so we can attach a
  // friendly title + a primary action button (Open token settings for
  // 401, Retry for 5xx / network). The raw message lives inside a
  // <details> so the friendly headline is what the user sees first.
  // The string form is preserved for backward compatibility with
  // existing callers.
  function renderError(arg) {
    var opts = (arg && typeof arg === "object") ? arg : { raw: arg };
    var title = opts.title || "The assistant could not answer this question.";
    var detail = opts.detail || "";
    var raw = opts.raw || (typeof arg === "string" ? arg : "Request failed.");
    var actionLabel = opts.actionLabel || "";
    var actionId = opts.actionId || ""; // "open-token-settings" | "retry-query"
    var status = opts.status || "error";

    setAnswerState("error");
    if (els.answer) {
      els.answer.hidden = false;
      els.answer.classList.remove("placeholder", "placeholder-refused");
      els.answer.classList.add("placeholder-error");
      var actionHtml = "";
      if (actionLabel) {
        actionHtml = (
          '<div class="error-banner-actions">' +
            '<button type="button" data-action="' + escapeAttr(actionId) + '">' +
              escapeHtml(actionLabel) +
            '</button>' +
          '</div>'
        );
      }
      els.answer.innerHTML = (
        '<div class="error-banner" role="alert" data-status="' + escapeAttr(status) + '">' +
          '<p class="error-banner-title">' + escapeHtml(title) + '</p>' +
          (detail ? '<p class="error-banner-detail">' + escapeHtml(detail) + '</p>' : '') +
          actionHtml +
          '<details class="error-banner-raw">' +
            '<summary>Technical details</summary>' +
            '<pre>' + escapeHtml(raw) + '</pre>' +
          '</details>' +
        '</div>'
      );
      // Wire the action button (M-2). The handler is bound after the
      // innerHTML write so the element exists.
      var btn = els.answer.querySelector("button[data-action]");
      if (btn) {
        btn.addEventListener("click", function () {
          if (actionId === "open-token-settings") {
            if (els.authPanel) {
              els.authPanel.hidden = false;
              if (els.authToken) els.authToken.focus();
            }
          } else if (actionId === "retry-query") {
            if (state.lastQuestion) {
              submitQuery();
            } else {
              setStatus("Nothing to retry — type a question and press Ask.", "warn");
              if (els.question) els.question.focus();
            }
          } else if (actionId === "retry-collections") {
            loadCollections();
          }
        });
      }
    }
    if (els.citations) {
      els.citations.hidden = true;
      els.citations.innerHTML = "";
    }
    state.lastError = opts;
  }

  function renderRefused(payload) {
    setAnswerState("refused");
    var reason = (payload && payload.reason) || "insufficient_evidence";
    var score = (payload && payload.best_score != null)
      ? Number(payload.best_score).toFixed(4)
      : "—";
    var threshold = (payload && payload.threshold != null)
      ? Number(payload.threshold).toFixed(4)
      : "—";
    els.answer.hidden = false;
    els.answer.innerHTML =
      "<strong>The corpus has no answer to this question.</strong> " +
      "<br><span class=\"muted\">Reason: <code>" + escapeHtml(reason) +
      "</code> · best_score=" + escapeHtml(score) +
      " · threshold=" + escapeHtml(threshold) + "</span>";
    els.answer.classList.remove("placeholder", "placeholder-error");
    els.answer.classList.add("placeholder-refused");
    els.citations.hidden = true;
    els.citations.innerHTML = "";
  }

  function renderAnswered(payload) {
    setAnswerState("answered");
    var answer = (payload && payload.answer) || "";
    els.answer.hidden = false;
    // M-1: pre-escape the answer text, then convert inline `[N]`
    // markers into anchor links pointing at the matching citation
    // card. The server text remains the source of truth.
    var escapedAnswer = escapeHtml(answer);
    var linked = linkifyInlineCitations(escapedAnswer, (payload && payload.citations) || []);
    els.answer.innerHTML = "<pre class=\"answer-pre\">" + linked + "</pre>";
    els.answer.classList.remove("placeholder", "placeholder-error", "placeholder-refused");

    var cites = (payload && payload.citations) || [];
    if (!cites.length) {
      els.citations.hidden = true;
      els.citations.innerHTML = "";
      return;
    }
    var items = cites.map(function (c, i) {
      var idx = i + 1;
      var loc = [];
      if (c.section) loc.push("section: " + escapeHtml(c.section));
      if (c.page != null) loc.push("page " + escapeHtml(String(c.page)));
      var locStr = loc.length ? loc.join(" · ") : escapeHtml(c.file_name || "");
      var score = c.score != null ? Number(c.score).toFixed(4) : "—";
      var snippet = (c.text || "").slice(0, 220);
      if ((c.text || "").length > 220) snippet += "…";
      // M-1: every citation is wrapped in an anchor + given a stable
      // id so the inline `[N]` markers can jump to it. The href is a
      // relative anchor so the link works without network access.
      return (
        '<li id="citation-' + idx + '" class="citation">' +
          '<a class="citation-anchor" href="#citation-' + idx + '" ' +
               'data-citation-idx="' + idx + '" aria-label="Jump to citation ' + idx + '">' +
            '<div class="citation-head">' +
              '<span class="citation-idx">[' + idx + ']</span>' +
              '<span class="citation-file">' + escapeHtml(c.file_name || "") + '</span>' +
              '<span class="citation-loc">' + locStr + '</span>' +
              '<span class="citation-score">score=' + score + '</span>' +
            '</div>' +
            '<div class="citation-body">' + escapeHtml(snippet) + '</div>' +
          '</a>' +
        '</li>'
      );
    });
    // M-4: collapse the overflow of citations when the answer carries
    // more than the configured expandTop count. The function is
    // intentionally named `collapseCitations` so the verify script
    // can grep for it.
    els.citations.innerHTML = collapseCitations(items);
    els.citations.hidden = false;
  }

  function render(payload) {
    if (!payload || typeof payload !== "object") {
      renderError({
        title: "The API returned an empty response.",
        detail: "The server replied, but the body was empty.",
        raw: "Empty response from API.",
        actionLabel: "Retry",
        actionId: "retry-query",
      });
      return;
    }
    if (payload.status === "answered") {
      renderAnswered(payload);
    } else if (payload.status === "refused") {
      renderRefused(payload);
    } else {
      renderError({
        title: "Unexpected response from the API.",
        detail: "Status: " + escapeText(payload.status),
        raw: "Unexpected response status: " + escapeText(payload.status),
        actionLabel: "Retry",
        actionId: "retry-query",
      });
    }
  }

  // ----- Boot ------------------------------------------------------------
  function refreshAskButton() {
    if (!els.ask || !els.question) return;
    var hasQuestion = els.question.value.trim().length > 0;
    var hasCollection = !!els.collection.value;
    els.ask.disabled = state.pending || !hasQuestion || !hasCollection;
  }

  function loadIdentity() {
    return fetchJson("/api/v1/identity").then(applyIdentity);
  }

  function loadCollections() {
    return fetchJson(
      "/api/v1/collections?workspace=" + encodeURIComponent(WORKSPACE)
    ).then(renderCollections).catch(function (err) {
      if (els.collection) {
        els.collection.innerHTML = '<option value="">— unavailable —</option>';
      }
      renderError({
        title: "Failed to load collections.",
        detail: "The /v1/collections endpoint did not respond.",
        raw: "Failed to load collections: " + err.message,
        actionLabel: "Retry",
        actionId: "retry-collections",
      });
    });
  }

  function refreshAuthPill() {
    if (!els.authPill || !state.identity) return;
    if (!state.identity.auth_enabled) {
      els.authPill.textContent = "Auth disabled";
      els.authPill.classList.remove("pill-warn");
      els.authPill.classList.add("pill-muted");
      return;
    }
    var token = readToken();
    els.authPill.textContent = token ? "Authenticated" : "Auth required";
    els.authPill.classList.toggle("pill-warn", !token);
    els.authPill.classList.toggle("pill-ok", !!token);
  }

  function submitQuery() {
    if (state.pending) return;
    var question = els.question.value.trim();
    var cid = parseInt(els.collection.value, 10);
    if (!question || !cid) {
      setStatus("Pick a collection and type a question.", "warn");
      return;
    }
    state.pending = true;
    state.lastQuestion = { question: question, collection_id: cid };
    refreshAskButton();
    setStatus("Asking…", "info");
    fetchJson("/api/v1/query", {
      method: "POST",
      body: JSON.stringify({
        question: question,
        collection_id: cid,
        workspace: WORKSPACE,
        top_k: 5,
      }),
    })
      .then(function (resp) {
        render(resp);
        if (resp.status === "answered") {
          setStatus(
            "Answered with " + pluralize((resp.citations || []).length, "citation") + ".",
            "ok"
          );
        } else if (resp.status === "refused") {
          setStatus("Refused — corpus has no supporting evidence.", "warn");
        }
      })
      .catch(function (err) {
        // M-2: turn raw HTTP errors into a friendly banner with a
        // primary action. 401 → "Open token settings"; everything
        // else (5xx, network) → "Retry".
        var opts = {
          title: err.status === 401
            ? "Unauthorized — the API rejected your request."
            : "Request failed.",
          detail: err.status === 401
            ? "The configured bearer token did not match."
            : "The API did not return a usable response.",
          raw: err.message || "Request failed.",
        };
        if (err.status === 401) {
          opts.actionLabel = "Open token settings";
          opts.actionId = "open-token-settings";
          opts.status = "401";
          setStatus("Unauthorized — check your bearer token.", "warn");
        } else {
          opts.actionLabel = "Retry";
          opts.actionId = "retry-query";
          opts.status = err.status ? String(err.status) : "network";
          setStatus("Request failed.", "warn");
        }
        renderError(opts);
      })
      .then(function () {
        state.pending = false;
        refreshAskButton();
      });
  }

  function bindEvents() {
    if (els.question) {
      els.question.addEventListener("input", refreshAskButton);
    }
    if (els.collection) {
      els.collection.addEventListener("change", refreshAskButton);
    }
    if (els.ask) {
      els.ask.addEventListener("click", submitQuery);
    }
    if (els.clear) {
      els.clear.addEventListener("click", function () {
        els.question.value = "";
        renderIdle();
        setStatus("Cleared.", "info");
        refreshAskButton();
        els.question.focus();
      });
    }
    if (els.authToggle) {
      els.authToggle.addEventListener("click", function () {
        els.authPanel.hidden = !els.authPanel.hidden;
        if (!els.authPanel.hidden) els.authToken.focus();
      });
    }
    if (els.authSave) {
      els.authSave.addEventListener("click", function () {
        var v = els.authToken.value.trim();
        writeToken(v);
        refreshAuthPill();
        setAuthMsg(
          v ? "Token saved to this browser only." : "Token cleared.",
          v ? "ok" : "info"
        );
        // Re-fetch collections with the new credential so the user sees
        // the auth change take effect immediately.
        if (state.identity && state.identity.auth_enabled) loadCollections();
      });
    }
    if (els.authClear) {
      els.authClear.addEventListener("click", function () {
        els.authToken.value = "";
        writeToken("");
        refreshAuthPill();
        setAuthMsg("Token cleared.", "info");
      });
    }
    // Submit on Ctrl+Enter / Cmd+Enter for ergonomics.
    if (els.question) {
      els.question.addEventListener("keydown", function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          submitQuery();
        }
      });
    }
    // Workspace switcher.
    if (els.workspaceApply) {
      els.workspaceApply.addEventListener("click", function () {
        var v = (els.workspaceInput.value || "").trim();
        if (!v || !WORKSPACE_PATTERN.test(v)) {
          setStatus("Workspace id must match [a-zA-Z0-9._-]{1,64}.", "warn");
          return;
        }
        writeWorkspace(v);
        WORKSPACE = v;
        if (els.workspaceCurrent) els.workspaceCurrent.textContent = v;
        document.documentElement.setAttribute("data-workspace", v);
        loadCollections();
        setStatus("Workspace switched to " + v + ".", "ok");
      });
    }
  }

  function boot() {
    bindEvents();
    renderIdle();
    setStatus("Loading identity…", "info");

    loadIdentity()
      .then(function () {
        refreshAuthPill();
        return loadCollections();
      })
      .then(function () {
        // M-3: if the workspace has no collections, renderCollections
        // already set the actionable empty-state status. Do not
        // overwrite it with the generic "Ready." copy.
        if (state.collections.length === 0) {
          refreshAskButton();
          return;
        }
        setStatus(
          state.identity && state.identity.auth_enabled
            ? "Auth required — set the bearer token before querying."
            : "Ready. Pick a collection and ask a question.",
          "ok"
        );
        refreshAskButton();
      })
      .catch(function (err) {
        setStatus("Failed to load identity: " + (err.message || "unknown"), "warn");
        // Keep the page usable: the user can still see the static shell.
      })
      .then(function () {
        // Smoke marker: JS is alive AND identity round-trip completed (or
        // failed gracefully). Useful for tests.
        document.documentElement.setAttribute("data-ui", "ready");
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();