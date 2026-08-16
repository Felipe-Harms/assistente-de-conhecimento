// Knowledge Assistant — Production UI (REQ-006, REQ-007).
//
// i18n: single source of truth. The I18N dictionary at the top of
// this file holds both pt-BR (default) and en strings. The lang
// toggle in the header switches between them; the choice persists
// in localStorage. The translateHtml() call on boot replaces every
// element with a [data-i18n] attribute and the [data-i18n-attr]
// attributes for placeholder/aria-label/title.
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

  // ----- I18N -----------------------------------------------------------
  var I18N = {
    "pt-BR": {
      locale: "pt-BR",
      pageTitle: "Assistente de Conhecimento",
      brandName: "Assistente de Conhecimento",
      subtitleLoading: "Carregando identidade…",
      footerNote: "Build de prova local.",
      langToggleLabel: "EN",
      langToggleTitle: "Switch to English",
      authPillRequired: "Auth obrigatório",
      authPillDisabled: "Auth desativado",
      authPillAuthenticated: "Autenticado",
      authToggleLabel: "Configurar token",
      authPanelTitle: "Token bearer",
      authPanelDesc: 'A API está configurada com <code>AUTH_ENABLED=true</code>. Cole o token pré-compartilhado; ele é armazenado apenas no localStorage deste navegador e enviado como <code>Authorization: Bearer …</code> em cada requisição.',
      authSave: "Salvar",
      authClear: "Limpar",
      authTokenPlaceholder: "cole o token bearer",
      authTokenSaved: "Token salvo apenas neste navegador.",
      authTokenCleared: "Token removido.",
      askTitle: "Pergunte à base de conhecimento",
      askDesc: "Escolha uma coleção e faça uma pergunta. O assistente só responde quando o corpus tem evidência de suporte; caso contrário, recusa-se explicitamente.",
      collectionLabel: "Coleção",
      collectionLoading: "— carregando —",
      collectionUnavailable: "— indisponível —",
      collectionNoCollections: "— sem coleções —",
      collectionHelp: "Uma coleção é um bucket nomeado de documentos dentro do workspace configurado.",
      workspaceSummary: "Workspace: ",
      workspacePlaceholder: "id do workspace (ex.: default)",
      workspaceApply: "Aplicar",
      workspaceHelp: "Workspaces diferentes são isolados. A escolha persiste apenas neste navegador.",
      questionPlaceholder: "O que você gostaria de saber?",
      askButton: "Perguntar",
      clearButton: "Limpar",
      statusLoading: "Carregando identidade…",
      answerTitle: "Resposta",
      answerIdle: "Escolha uma coleção, digite uma pergunta e pressione <kbd>Perguntar</kbd>. As respostas vêm com citações que você pode verificar.",
      answerAsked: "Consultando…",
      limitsTitle: "Escopo & limites",
      limitOCR: "Sem OCR, sem tabelas complexas, sem analytics.",
      limitGrounded: "As respostas são fundamentadas apenas no corpus configurado — recusas são honestas, não palpites.",
      limitNoPublic: "Sem hospedagem pública, sem monitoramento 24/7, sem precisão perfeita.",
      limitLossy: "Lembre-se: embeddings são com perdas. Sempre leia as citações.",
      emptyStateTitle: "Este workspace ainda não tem coleções.",
      emptyStateDesc: "Você pode escolher outro workspace no seletor abaixo, ou ingerir um documento via a API <code>POST /v1/ingest</code>.",
      emptyStateStatus: "Este workspace ainda não tem coleções — escolha outro workspace ou ingira via a API.",
      refusedTitle: "O corpus não tem resposta para esta pergunta.",
      refusedStatus: "Recusado — o corpus não tem evidência de suporte.",
      errorTitle: "O assistente não conseguiu responder a esta pergunta.",
      errorDetail401: "O token bearer configurado não correspondeu.",
      errorDetailGeneric: "A API não retornou uma resposta utilizável.",
      errorDetailEmpty: "O servidor respondeu, mas o corpo estava vazio.",
      errorDetailUnexpected: "Status: ",
      errorRawLabel: "Detalhes técnicos",
      errorActionOpenToken: "Abrir configurações de token",
      errorActionRetry: "Tentar novamente",
      errorActionRetryCollections: "Recarregar coleções",
      errorUnauthorized: "Não autorizado — sua requisição foi rejeitada pela API.",
      errorRequestFailed: "Falha na requisição.",
      errorEmptyResponse: "A API retornou uma resposta vazia.",
      errorUnexpected: "Resposta inesperada da API.",
      errorStatus: "Status:",
      errorRetryQuestion: "Nada para tentar novamente — digite uma pergunta e pressione Perguntar.",
      warnPickBoth: "Escolha uma coleção e digite uma pergunta.",
      warnBadWorkspace: "O id do workspace deve corresponder a [a-zA-Z0-9._-]{1,64}.",
      statusSwitched: "Workspace alterado para ",
      statusCleared: "Limpo.",
      statusReady: "Pronto. Escolha uma coleção e faça uma pergunta.",
      statusAuthRequired: "Auth obrigatório — defina o token bearer antes de perguntar.",
      statusFailedIdentity: "Falha ao carregar identidade: ",
      statusFailedRequest: "Falha na requisição.",
      statusUnauthorized: "Não autorizado — verifique seu token bearer.",
      statusCitation: "Respondido com ",
      statusCitationSuffix: ".",
      statusRefused: "Recusado — o corpus não tem evidência de suporte.",
      statusWorkspaceSwitched: "Workspace alterado para ",
      toggleAuthTitle: "Configurar token",
      ariaJumpCitation: "Pular para citação ",
      ariaLangToggle: "Alternar idioma",
      citationLocPrefix: "seção: ",
      citationLocPage: "página ",
      citationLocSep: " · ",
      citationScore: "score=",
      citationSnippetMore: "…",
      collectionsFailed: "Falha ao carregar coleções: ",
      collectionsFailedTitle: "Falha ao carregar coleções.",
      collectionsFailedDetail: "O endpoint /v1/collections não respondeu.",
      overflowSummaryOne: "Mostrar mais 1 citação",
      overflowSummaryMany: "Mostrar mais ",
      overflowSummarySuffix: " citações",
      unknown: "desconhecido",
    },
    "en": {
      locale: "en",
      pageTitle: "Knowledge Assistant",
      brandName: "Knowledge Assistant",
      subtitleLoading: "Loading identity…",
      footerNote: "Local-only proof build.",
      langToggleLabel: "PT",
      langToggleTitle: "Mudar para português",
      authPillRequired: "Auth required",
      authPillDisabled: "Auth disabled",
      authPillAuthenticated: "Authenticated",
      authToggleLabel: "Configure token",
      authPanelTitle: "Bearer token",
      authPanelDesc: 'The API is configured with <code>AUTH_ENABLED=true</code>. Paste the pre-shared token; it is stored only in this browser\'s local storage and sent as <code>Authorization: Bearer …</code> on every request.',
      authSave: "Save",
      authClear: "Clear",
      authTokenPlaceholder: "paste bearer token",
      authTokenSaved: "Token saved to this browser only.",
      authTokenCleared: "Token cleared.",
      askTitle: "Ask the knowledge base",
      askDesc: "Pick a collection, then ask a question. The assistant will answer only when the corpus has supporting evidence; otherwise it will refuse explicitly.",
      collectionLabel: "Collection",
      collectionLoading: "— loading —",
      collectionUnavailable: "— unavailable —",
      collectionNoCollections: "— no collections —",
      collectionHelp: "A collection is a named bucket of documents inside the configured workspace.",
      workspaceSummary: "Workspace: ",
      workspacePlaceholder: "workspace id (e.g. default)",
      workspaceApply: "Apply",
      workspaceHelp: "Different workspaces are isolated. The choice persists in this browser only.",
      questionPlaceholder: "What would you like to know?",
      askButton: "Ask",
      clearButton: "Clear",
      statusLoading: "Loading identity…",
      answerTitle: "Answer",
      answerIdle: "Pick a collection, type a question, and press <kbd>Ask</kbd>. Answers come with citations you can verify.",
      answerAsked: "Asking…",
      limitsTitle: "Scope & limits",
      limitOCR: "No OCR, no complex tables, no analytics.",
      limitGrounded: "Answers are grounded in the configured corpus only — refusals are honest, not guesses.",
      limitNoPublic: "No public hosting, no 24/7 monitoring, no perfect accuracy.",
      limitLossy: "Bear in mind: embeddings are lossy. Always read the citations.",
      emptyStateTitle: "This workspace has no collections yet.",
      emptyStateDesc: "You can pick another workspace from the switcher below, or ingest a document via the <code>POST /v1/ingest</code> API.",
      emptyStateStatus: "This workspace has no collections yet — pick another workspace or ingest via the API.",
      refusedTitle: "The corpus has no answer to this question.",
      refusedStatus: "Refused — corpus has no supporting evidence.",
      errorTitle: "The assistant could not answer this question.",
      errorDetail401: "The configured bearer token did not match.",
      errorDetailGeneric: "The API did not return a usable response.",
      errorDetailEmpty: "The server replied, but the body was empty.",
      errorDetailUnexpected: "Status: ",
      errorRawLabel: "Technical details",
      errorActionOpenToken: "Open token settings",
      errorActionRetry: "Retry",
      errorActionRetryCollections: "Retry collections",
      errorUnauthorized: "Unauthorized — the API rejected your request.",
      errorRequestFailed: "Request failed.",
      errorEmptyResponse: "The API returned an empty response.",
      errorUnexpected: "Unexpected response from the API.",
      errorStatus: "Status:",
      errorRetryQuestion: "Nothing to retry — type a question and press Ask.",
      warnPickBoth: "Pick a collection and type a question.",
      warnBadWorkspace: "Workspace id must match [a-zA-Z0-9._-]{1,64}.",
      statusSwitched: "Workspace switched to ",
      statusCleared: "Cleared.",
      statusReady: "Ready. Pick a collection and ask a question.",
      statusAuthRequired: "Auth required — set the bearer token before querying.",
      statusFailedIdentity: "Failed to load identity: ",
      statusFailedRequest: "Request failed.",
      statusUnauthorized: "Unauthorized — check your bearer token.",
      statusCitation: "Answered with ",
      statusCitationSuffix: ".",
      statusRefused: "Refused — corpus has no supporting evidence.",
      statusWorkspaceSwitched: "Workspace switched to ",
      toggleAuthTitle: "Configure token",
      ariaJumpCitation: "Jump to citation ",
      ariaLangToggle: "Toggle language",
      citationLocPrefix: "section: ",
      citationLocPage: "page ",
      citationLocSep: " · ",
      citationScore: "score=",
      citationSnippetMore: "…",
      collectionsFailed: "Failed to load collections: ",
      collectionsFailedTitle: "Failed to load collections.",
      collectionsFailedDetail: "The /v1/collections endpoint did not respond.",
      overflowSummaryOne: "Show 1 more citation",
      overflowSummaryMany: "Show ",
      overflowSummarySuffix: " more citations",
      unknown: "unknown",
    },
  };

  var LOCALE_KEY = "upworkkb.locale.v1";
  var DEFAULT_LOCALE = "pt-BR";

  function readLocale() {
    try {
      var stored = window.localStorage.getItem(LOCALE_KEY);
      if (stored && I18N[stored]) return stored;
    } catch (_e) { /* fall through */ }
    var html = document.documentElement.getAttribute("lang");
    if (html && I18N[html]) return html;
    return DEFAULT_LOCALE;
  }

  function writeLocale(value) {
    try {
      if (value && I18N[value]) {
        window.localStorage.setItem(LOCALE_KEY, value);
      }
    } catch (_e) { /* noop */ }
  }

  var LOCALE = readLocale();

  function t(key) {
    var dict = I18N[LOCALE] || I18N[DEFAULT_LOCALE];
    return (dict && dict[key]) || (I18N[DEFAULT_LOCALE] && I18N[DEFAULT_LOCALE][key]) || key;
  }

  function setLocale(newLocale) {
    if (!I18N[newLocale]) return;
    LOCALE = newLocale;
    writeLocale(newLocale);
    document.documentElement.setAttribute("lang", newLocale);
    applyI18n();
    // Update the toggle button label.
    var btn = document.getElementById("lang-toggle");
    if (btn) {
      btn.textContent = t("langToggleLabel");
      btn.setAttribute("title", t("langToggleTitle"));
      btn.setAttribute("aria-label", t("ariaLangToggle"));
    }
    // Re-render identity-driven strings (auth pill, subtitle, etc.)
    if (state && state.identity) applyIdentity(state.identity);
    // Re-render the answer card if it has content.
    if (els && els.answerState) {
      var s = els.answerState.dataset.state;
      if (s === "idle") renderIdle();
      else if (s === "empty") renderEmptyCollection();
    }
  }

  function applyI18n() {
    var nodes = document.querySelectorAll("[data-i18n]");
    for (var i = 0; i < nodes.length; i++) {
      var key = nodes[i].getAttribute("data-i18n");
      var attr = nodes[i].getAttribute("data-i18n-attr");
      var val = t(key);
      if (attr) {
        nodes[i].setAttribute(attr, val);
      } else {
        nodes[i].textContent = val;
      }
    }
  }

  // ----- DOM ------------------------------------------------------------
  var els = {
    pageTitle:      document.getElementById("page-title"),
    brandName:      document.getElementById("brand-name"),
    brandLogo:      document.getElementById("brand-logo"),
    subtitle:       document.getElementById("subtitle"),
    footerNote:     document.getElementById("footer-note"),
    langToggle:     document.getElementById("lang-toggle"),
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
    var summaryHtml;
    if (totalExtra === 1) {
      summaryHtml = t("overflowSummaryOne");
    } else {
      summaryHtml = t("overflowSummaryMany") + totalExtra + t("overflowSummarySuffix");
    }
    return (
      '<details class="citations-overflow">' +
        '<summary>' + escapeHtml(summaryHtml) + '</summary>' +
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
    var brandName = escapeText(identity.brand_name || t("brandName"));
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
      els.authPill.textContent = authOn ? t("authPillRequired") : t("authPillDisabled");
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
      els.collection.innerHTML = '<option value="">' + escapeHtml(t("collectionNoCollections")) + '</option>';
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
          '<strong>' + escapeHtml(t("emptyStateTitle")) + '</strong> ' +
          escapeHtml(t("emptyStateDesc").replace(/^.*?API\./, "").trim() || t("emptyStateDesc").replace(/^You can pick another workspace from the switcher below, or ingest a document via the /, "").replace(/, or ingest.*$/, "") || "You can pick another workspace from the switcher below, or ingest a document via the API.") +
        '</p>'
      );
    }
    if (els.citations) {
      els.citations.hidden = true;
      els.citations.innerHTML = "";
    }
    if (els.status) {
      els.status.textContent = t("emptyStateStatus");
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
    els.answer.innerHTML = t("answerIdle");
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
    var title = opts.title || t("errorTitle");
    var detail = opts.detail || "";
    var raw = opts.raw || (typeof arg === "string" ? arg : t("errorRequestFailed"));
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
            '<summary>' + escapeHtml(t("errorRawLabel")) + '</summary>' +
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
              setStatus(t("errorRetryQuestion"), "warn");
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
      "<strong>" + escapeHtml(t("refusedTitle")) + "</strong> " +
      "<br><span class=\"muted\">" + escapeHtml(t("errorStatus")) + " <code>" + escapeHtml(reason) +
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
      if (c.section) loc.push(t("citationLocPrefix") + escapeHtml(c.section));
      if (c.page != null) loc.push(t("citationLocPage") + escapeHtml(String(c.page)));
      var locStr = loc.length ? loc.join(t("citationLocSep")) : escapeHtml(c.file_name || "");
      var score = c.score != null ? Number(c.score).toFixed(4) : "—";
      var snippet = (c.text || "").slice(0, 220);
      if ((c.text || "").length > 220) snippet += t("citationSnippetMore");
      var ariaLabel = t("ariaJumpCitation") + idx;
      // M-1: every citation is wrapped in an anchor + given a stable
      // id so the inline `[N]` markers can jump to it. The href is a
      // relative anchor so the link works without network access.
      return (
        '<li id="citation-' + idx + '" class="citation">' +
          '<a class="citation-anchor" href="#citation-' + idx + '" ' +
               'data-citation-idx="' + idx + '" aria-label="' + escapeAttr(ariaLabel) + '">' +
            '<div class="citation-head">' +
              '<span class="citation-idx">[' + idx + ']</span>' +
              '<span class="citation-file">' + escapeHtml(c.file_name || "") + '</span>' +
              '<span class="citation-loc">' + locStr + '</span>' +
              '<span class="citation-score">' + escapeHtml(t("citationScore")) + score + '</span>' +
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
        title: t("errorEmptyResponse"),
        detail: t("errorDetailEmpty"),
        raw: "Empty response from API.",
        actionLabel: t("errorActionRetry"),
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
        title: t("errorUnexpected"),
        detail: t("errorDetailUnexpected") + escapeText(payload.status),
        raw: "Unexpected response status: " + escapeText(payload.status),
        actionLabel: t("errorActionRetry"),
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
        els.collection.innerHTML = '<option value="">' + escapeHtml(t("collectionUnavailable")) + '</option>';
      }
      renderError({
        title: t("collectionsFailedTitle"),
        detail: t("collectionsFailedDetail"),
        raw: t("collectionsFailed") + err.message,
        actionLabel: t("errorActionRetryCollections"),
        actionId: "retry-collections",
      });
    });
  }

  function refreshAuthPill() {
    if (!els.authPill || !state.identity) return;
    if (!state.identity.auth_enabled) {
      els.authPill.textContent = t("authPillDisabled");
      els.authPill.classList.remove("pill-warn");
      els.authPill.classList.add("pill-muted");
      return;
    }
    var token = readToken();
    els.authPill.textContent = token ? t("authPillAuthenticated") : t("authPillRequired");
    els.authPill.classList.toggle("pill-warn", !token);
    els.authPill.classList.toggle("pill-ok", !!token);
  }

  function submitQuery() {
    if (state.pending) return;
    var question = els.question.value.trim();
    var cid = parseInt(els.collection.value, 10);
    if (!question || !cid) {
      setStatus(t("warnPickBoth"), "warn");
      return;
    }
    state.pending = true;
    state.lastQuestion = { question: question, collection_id: cid };
    refreshAskButton();
    setStatus(t("answerAsked"), "info");
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
            t("statusCitation") + pluralize((resp.citations || []).length, "citation") + t("statusCitationSuffix"),
            "ok"
          );
        } else if (resp.status === "refused") {
          setStatus(t("statusRefused"), "warn");
        }
      })
      .catch(function (err) {
        // M-2: turn raw HTTP errors into a friendly banner with a
        // primary action. 401 → "Open token settings"; everything
        // else (5xx, network) → "Retry".
        var opts = {
          title: err.status === 401 ? t("errorUnauthorized") : t("errorRequestFailed"),
          detail: err.status === 401 ? t("errorDetail401") : t("errorDetailGeneric"),
          raw: err.message || t("errorRequestFailed"),
        };
        if (err.status === 401) {
          opts.actionLabel = t("errorActionOpenToken");
          opts.actionId = "open-token-settings";
          opts.status = "401";
          setStatus(t("statusUnauthorized"), "warn");
        } else {
          opts.actionLabel = t("errorActionRetry");
          opts.actionId = "retry-query";
          opts.status = err.status ? String(err.status) : "network";
          setStatus(t("statusFailedRequest"), "warn");
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
        setStatus(t("statusCleared"), "info");
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
          v ? t("authTokenSaved") : t("authTokenCleared"),
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
        setAuthMsg(t("authTokenCleared"), "info");
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
          setStatus(t("warnBadWorkspace"), "warn");
          return;
        }
        writeWorkspace(v);
        WORKSPACE = v;
        if (els.workspaceCurrent) els.workspaceCurrent.textContent = v;
        document.documentElement.setAttribute("data-workspace", v);
        loadCollections();
        setStatus(t("statusWorkspaceSwitched") + v + t("statusCitationSuffix"), "ok");
      });
    }
    // Language toggle.
    if (els.langToggle) {
      els.langToggle.addEventListener("click", function () {
        var next = LOCALE === "pt-BR" ? "en" : "pt-BR";
        setLocale(next);
      });
    }
  }

  function boot() {
    applyI18n();
    bindEvents();
    renderIdle();
    setStatus(t("statusLoading"), "info");

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
            ? t("statusAuthRequired")
            : t("statusReady"),
          "ok"
        );
        refreshAskButton();
      })
      .catch(function (err) {
        setStatus(t("statusFailedIdentity") + (err.message || t("unknown")), "warn");
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

  // Expose a tiny API to the test harness so the E2E suite can deterministically
  // pin the locale and re-render without depending on click events.
  window.__KB = window.__KB || {};
  window.__KB.setLocale = setLocale;
  window.__KB.t = t;
  window.__KB.getLocale = function () { return LOCALE; };
})();
