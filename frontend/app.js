// OpenRice 餐飲優惠 — 每日生命週期狀態引擎 + 商場 Focus 橫向優惠軌
(function (global) {
  "use strict";

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function todayDateStr(ref) {
    const d = ref ? new Date(ref) : new Date();
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  }

  function parseLocalDate(value) {
    if (!value) return null;
    const text = String(value).slice(0, 10);
    const parts = text.split("-");
    if (parts.length !== 3) return null;
    const y = Number(parts[0]);
    const m = Number(parts[1]) - 1;
    const day = Number(parts[2]);
    const dt = new Date(y, m, day);
    return Number.isNaN(dt.getTime()) ? null : dt;
  }

  function daysBetween(fromStr, toStr) {
    const from = parseLocalDate(fromStr);
    const to = parseLocalDate(toStr);
    if (!from || !to) return null;
    return Math.round((to - from) / 86400000);
  }

  function formatMMDD(value) {
    const dt = parseLocalDate(value);
    if (!dt) return "";
    return `${dt.getMonth() + 1}/${dt.getDate()}`;
  }

  const DEFAULT_DINING_TITLE = "店內指定特惠套餐 / 堂食折扣";
  const DINING_IMAGE_FALLBACK =
    "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=500";
  const STORE_IMAGE_FALLBACK = "images/defaults/store_default.png";
  const MALL_FEED_SOURCES = [
    "./data/cache/malls.json",
    "./malls.json",
    "./data/malls.json",
  ];
  const JSON_CONFLICT_MARKERS = ["<<<<<<<", "=======", ">>>>>>>"];

  function isValidMallFeed(payload) {
    return (
      payload &&
      typeof payload === "object" &&
      Array.isArray(payload.districts)
    );
  }

  async function fetchJsonResource(url, label) {
    let response;
    try {
      response = await fetch(url, { cache: "no-store" });
    } catch (networkErr) {
      console.error(`[HK-Deal] Network error loading ${label}`, {
        url,
        error: networkErr,
      });
      throw networkErr;
    }
    if (!response.ok) {
      const err = new Error(`${label} HTTP ${response.status} ${response.statusText}`);
      console.error(`[HK-Deal] Failed to load ${label}`, {
        url,
        status: response.status,
        statusText: response.statusText,
      });
      throw err;
    }
    const text = await response.text();
    if (JSON_CONFLICT_MARKERS.some((marker) => text.includes(marker))) {
      const err = new Error(`${label} contains unresolved Git merge conflict markers`);
      console.error(`[HK-Deal] Conflict markers in ${label}`, { url });
      throw err;
    }
    try {
      return JSON.parse(text);
    } catch (parseErr) {
      console.error(`[HK-Deal] Invalid JSON in ${label}`, { url, error: parseErr });
      throw parseErr;
    }
  }

  /**
   * Load SPA mall feed with fallback chain:
   * data/cache/malls.json → malls.json → data/malls.json (parking catalog skipped if no districts).
   */
  async function fetchMallFeed() {
    const errors = [];
    for (const url of MALL_FEED_SOURCES) {
      const label = url.replace(/^\.\//, "");
      try {
        const payload = await fetchJsonResource(url, label);
        if (!isValidMallFeed(payload)) {
          console.warn(`[HK-Deal] ${label} is not a mall feed (missing districts); trying next source.`);
          continue;
        }
        if (url !== MALL_FEED_SOURCES[0]) {
          console.warn(`[HK-Deal] Mall feed loaded from fallback: ${url}`);
        }
        return payload;
      } catch (err) {
        errors.push({ url, error: err });
      }
    }
    const summary = errors.map((e) => `${e.url}: ${e.error && e.error.message}`).join("; ");
    throw new Error(`All mall feed sources failed (${summary})`);
  }

  function imgOnErrorAttr(fallbackUrl) {
    const fb = String(fallbackUrl || DINING_IMAGE_FALLBACK).replace(/'/g, "\\'");
    return `onerror="this.onerror=null;this.src='${fb}';"`;
  }

  const LEGACY_DEFAULTS = [
    "店內當期指定餐飲優惠（請參閱門市告示）",
    "OpenRice 門市／外賣常態禮遇：堂食或外賣自取惠顧可享店內當期推廣；實際條款以 OpenRice App／店內告示為準。",
  ];

  const SUBSTANTIVE_OFFER_RE =
    /\$\s*\d+|HK\$\s*\d+|港幣\s*\d+|\d+(?:\.\d+)?\s*折|\d+\s*%|現金券|現金劵|餐飲券|優惠券|禮券|半價|買一送一|BOGO|第二件|減\s*\$|滿\s*\$|即減|回贈|套餐|放題|特惠|折扣|訂座|外賣|自取|即買即用|限時/i;

  function isGenericOpenRiceTitle(text) {
    const t = String(text || "").trim();
    if (!t) return true;
    if (t === DEFAULT_DINING_TITLE || LEGACY_DEFAULTS.includes(t)) return true;
    if (t.includes("店內指定特惠套餐") || t.includes("店內當期指定餐飲優惠")) return true;
    if (t.includes("OpenRice 門市 / 外賣常態禮遇") || t.includes("OpenRice 門市／外賣常態禮遇")) return true;
    if (t.includes("OpenRice 門市/外賣常態禮遇")) return true;
    if (t === "門市／外賣優惠" || t === "OpenRice 門市／外賣優惠") return true;
    if (/^OpenRice\s/i.test(t) && t.length < 48 && t.includes("優惠")) return true;
    return false;
  }

  function normalizeDiningTitle(text) {
    let t = String(text || "").trim();
    if (t.includes("｜")) t = t.split("｜").pop().trim();
    const stripped = t.replace(/^OpenRice\s+/i, "").trim();
    if (stripped && !isGenericOpenRiceTitle(stripped)) return stripped;
    return t;
  }

  function isSubstantiveOfferTitle(text) {
    const t = normalizeDiningTitle(text);
    if (!t || isGenericOpenRiceTitle(t)) return false;
    if (SUBSTANTIVE_OFFER_RE.test(t)) return true;
    return t.length >= 4 && !t.includes("門市") && !t.includes("常態") && !t.includes("告示");
  }

  function extractDiningOfferTitle(offer) {
    if (!offer || typeof offer !== "object") return "";

    const voucherTitles = [];
    const seen = new Set();
    const pushVoucher = (value) => {
      const text = normalizeDiningTitle(value);
      const key = text.toLowerCase();
      if (!text || isGenericOpenRiceTitle(text) || seen.has(key)) return;
      seen.add(key);
      voucherTitles.push(text);
    };
    if (Array.isArray(offer.vouchers)) {
      offer.vouchers.forEach((v) => {
        if (v && typeof v === "object") {
          pushVoucher(v.title || v.voucher_title || v.shortTitle || v.name);
        }
      });
    }
    if (offer.relatedVoucher && typeof offer.relatedVoucher === "object") {
      const rv = offer.relatedVoucher;
      pushVoucher(rv.title || rv.voucher_title || rv.shortTitle || rv.name);
    }
    if (voucherTitles.length) return voucherTitles.join(" / ");

    for (const key of [
      "offer_name",
      "discount_text",
      "voucher_title",
      "promotion_title",
      "promo_title",
      "title",
      "offer_title",
      "description",
      "details",
    ]) {
      const val = offer[key];
      if (typeof val !== "string") continue;
      const text = normalizeDiningTitle(val);
      if (text && !isGenericOpenRiceTitle(text) && isSubstantiveOfferTitle(text)) return text;
    }

    const booking = String(
      offer.booking_discount_text || offer.takeaway_discount_text || ""
    ).trim();
    if (booking && !isGenericOpenRiceTitle(booking)) {
      return `線上預約享 ${booking}`;
    }
    return "";
  }

  function getDisplayOfferDetail(offer) {
    if (!offer || typeof offer !== "object") return "";
    const extracted = extractDiningOfferTitle(offer);
    if (extracted && isSubstantiveOfferTitle(extracted)) return extracted;
    const title =
      offer.title || offer.offer_title || offer.discount_text || offer.offer_name || "";
    if (title && isSubstantiveOfferTitle(title)) return normalizeDiningTitle(title);
    return "";
  }

  function hasSubstantiveDiningOffer(offer) {
    return Boolean(getDisplayOfferDetail(offer));
  }

  /**
   * @returns {{ status: 'active'|'upcoming'|'expired'|'scheduled', daysUntilStart?: number, label?: string }}
   */
  function getOfferStatus(start_date, end_date, todayOverride) {
    const today = todayOverride || todayDateStr();
    const start = String(start_date || "").slice(0, 10);
    const end = String(end_date || "").slice(0, 10);
    if (!start || !end) return { status: "expired" };
    if (end < today) return { status: "expired" };

    if (start <= today && end >= today) {
      return {
        status: "active",
        label: `🟢 今日進行中 (至 ${formatMMDD(end)})`,
      };
    }

    const delta = daysBetween(today, start);
    if (delta != null && delta > 0 && delta <= 3) {
      return {
        status: "upcoming",
        daysUntilStart: delta,
        label: `🟡 ${delta}天後開始`,
      };
    }

    if (start > today) return { status: "scheduled" };
    return { status: "expired" };
  }

  function processStoreDeals(deals, todayOverride) {
    const activeDeals = [];
    const upcomingDeals = [];
    if (!Array.isArray(deals)) return { activeDeals, upcomingDeals };

    deals.forEach((deal) => {
      const startDate = deal.start_date || "2026-01-01";
      const endDate = deal.end_date || deal.valid_until || "2099-12-31";
      const lifecycle = getOfferStatus(startDate, endDate, todayOverride);
      if (lifecycle.status === "active") {
        activeDeals.push({ ...deal, badgeType: "active", badgeText: lifecycle.label || "🟢 今日進行中" });
      } else if (lifecycle.status === "upcoming") {
        upcomingDeals.push({
          ...deal,
          badgeType: "upcoming",
          badgeText: lifecycle.label || `🟡 ${lifecycle.daysUntilStart || ""}天後開始`,
        });
      }
    });

    return { activeDeals, upcomingDeals };
  }

  function liveDiningOffers(mall, todayOverride) {
    const offers = Array.isArray(mall && mall.dining_offers) ? mall.dining_offers : [];
    return offers.filter((offer) => {
      if (!hasSubstantiveDiningOffer(offer)) return false;
      const lifecycle = getOfferStatus(offer.start_date, offer.end_date, todayOverride);
      return lifecycle.status === "active" || lifecycle.status === "upcoming";
    });
  }

  function mallHasDiningOffers(mall, todayOverride) {
    return liveDiningOffers(mall, todayOverride).length > 0;
  }

  function clearPanelInlineStyles(panel) {
    if (!panel) return;
    panel.removeAttribute("hidden");
    [
      "display",
      "flex-direction",
      "flex-wrap",
      "overflow-x",
      "overflow-y",
      "width",
      "gap",
      "margin-top",
      "padding-bottom",
      "visibility",
      "height",
      "max-height",
      "opacity",
    ].forEach((prop) => panel.style.removeProperty(prop));
    panel.querySelectorAll(".offer-card").forEach((el) => {
      ["min-width", "max-width", "width", "flex-shrink", "display", "flex-direction"].forEach(
        (prop) => el.style.removeProperty(prop)
      );
    });
  }

  function collapseMallCard(card) {
    if (!card) return;
    card.classList.remove("is-focused", "mall-card--focused", "mall-card--offers-open");
    card.style.removeProperty("display");
    const panel = card.querySelector(".mall-offers-panel");
    if (panel) {
      clearPanelInlineStyles(panel);
      panel.style.setProperty("display", "none", "important");
    }
    const btn = card.querySelector("button.mall-toggle");
    if (btn) {
      btn.textContent = "+";
      btn.setAttribute("aria-expanded", "false");
      btn.setAttribute("aria-label", `展開 ${card.getAttribute("data-place-name") || ""} 優惠`);
    }
  }

  function applyFocusedPanelStyles(panel) {
    if (!panel) return;
    panel.removeAttribute("hidden");
    // Match requested focus styles (override any display:none)
    panel.style.setProperty("display", "flex", "important");
    panel.style.setProperty("flex-direction", "row", "important");
    panel.style.setProperty("flex-wrap", "nowrap", "important");
    panel.style.setProperty("overflow-x", "auto", "important");
    panel.style.setProperty("width", "100%", "important");
    panel.style.setProperty("gap", "12px", "important");
    panel.style.setProperty("margin-top", "16px", "important");
    panel.style.setProperty("padding-bottom", "12px", "important");
    panel.style.setProperty("visibility", "visible", "important");
    panel.style.setProperty("opacity", "1", "important");
    panel.querySelectorAll(".offer-card").forEach((card) => {
      card.style.setProperty("min-width", "340px", "important");
      card.style.setProperty("max-width", "360px", "important");
      card.style.setProperty("flex-shrink", "0", "important");
      card.style.setProperty("display", "flex", "important");
    });
  }

  /**
   * Focus one mall via + / − .
   * Order: add .is-focused BEFORE list focus-mode, so CSS never hides the active card.
   */
  function toggleMallFocusMode(mallCardEl, listRoot, forceOpen) {
    if (!mallCardEl || !mallCardEl.querySelector) {
      console.warn("[HK-Deal] toggleMallFocusMode: missing mall card");
      return false;
    }
    const panel = mallCardEl.querySelector(".mall-offers-panel");
    if (!panel) {
      console.warn("[HK-Deal] toggleMallFocusMode: missing .mall-offers-panel");
      return false;
    }

    const list =
      listRoot ||
      mallCardEl.closest("#mall-list") ||
      (typeof document !== "undefined" ? document.querySelector("#mall-list") : null);

    const isFocused = mallCardEl.classList.contains("is-focused");
    const nextOpen = typeof forceOpen === "boolean" ? forceOpen : !isFocused;
    const mallName = mallCardEl.getAttribute("data-place-name") || "";
    let offers = panel.querySelectorAll(".offer-card");

    console.log("[HK-Deal] +/− click", {
      mall: mallName,
      nextOpen,
      offersInDom: offers.length,
      panelHtmlLength: panel.innerHTML.length,
    });
    console.log("Focusing mall:", mallName, "Offers count:", offers.length);

    if (list) {
      list.querySelectorAll(".mall-card.is-focused, .mall-card.mall-card--focused").forEach((card) => {
        if (card !== mallCardEl) collapseMallCard(card);
      });
    }

    if (nextOpen) {
      mallCardEl.classList.add("is-focused");
      mallCardEl.classList.remove("mall-card--focused", "mall-card--offers-open");
      mallCardEl.style.removeProperty("display");
      mallCardEl.style.setProperty("display", "block", "important");

      if (list) {
        list.classList.add("mall-list--focus-mode");
        list.querySelectorAll(".mall-card").forEach((card) => {
          if (card !== mallCardEl) {
            card.style.setProperty("display", "none", "important");
          }
        });
        list.querySelectorAll("[data-place-kind='hotel']").forEach((el) => {
          el.style.setProperty("display", "none", "important");
        });
      }

      if (offers.length === 0) {
        panel.innerHTML =
          '<article class="offer-card rounded-2xl border border-dashed border-slate-300 bg-white p-5 text-sm text-slate-500">暫無實質優惠</article>';
        offers = panel.querySelectorAll(".offer-card");
        console.log("[HK-Deal] injected empty-state offer-card");
      }

      applyFocusedPanelStyles(panel);

      const plusBtn = mallCardEl.querySelector("button.mall-toggle");
      if (plusBtn) {
        plusBtn.textContent = "-";
        plusBtn.setAttribute("aria-expanded", "true");
        plusBtn.setAttribute("aria-label", `收合 ${mallName} 優惠`);
      }

      console.log("[HK-Deal] focus applied", {
        hasIsFocused: mallCardEl.classList.contains("is-focused"),
        panelDisplay: panel.style.display,
        offerCards: panel.querySelectorAll(".offer-card").length,
      });

      if (typeof mallCardEl.scrollIntoView === "function") {
        mallCardEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    } else {
      collapseMallCard(mallCardEl);
      if (list) {
        list.classList.remove("mall-list--focus-mode");
        list.querySelectorAll(".mall-card, [data-place-kind='hotel']").forEach((el) => {
          el.style.removeProperty("display");
        });
      }
      console.log("[HK-Deal] focus collapsed, list restored");
    }

    return nextOpen;
  }

  function toggleMallOffersPanel(mallCardEl, forceOpen, listRoot) {
    return toggleMallFocusMode(mallCardEl, listRoot, forceOpen);
  }

  function toggleDiningOffersSection(mallCardEl, forceOpen) {
    return toggleMallFocusMode(mallCardEl, null, forceOpen);
  }

  /** Single capture-phase handler — avoids double-toggle from bubble + per-button binds. */
  function onMallFocusCapture(event) {
    const trigger = event.target && event.target.closest
      ? event.target.closest("[data-mall-focus-toggle], button.mall-toggle")
      : null;
    if (!trigger) return;
    // Ignore hotel expand buttons
    if (trigger.hasAttribute("data-hotel-key") || trigger.classList.contains("hotel-toggle")) return;

    const card = trigger.closest(".mall-card");
    if (!card || !card.querySelector(".mall-offers-panel")) return;

    event.preventDefault();
    event.stopPropagation();
    if (typeof event.stopImmediatePropagation === "function") event.stopImmediatePropagation();

    const list = card.closest("#mall-list") || document.querySelector("#mall-list");
    console.log("[HK-Deal] capture click on +/−", trigger.textContent, card.getAttribute("data-place-name"));
    toggleMallFocusMode(card, list);
  }

  function bindMallOffersToggle(root) {
    const doc = root && root.addEventListener ? root : document;
    if (doc.__mallFocusCaptureBound) return;
    doc.__mallFocusCaptureBound = true;
    doc.addEventListener("click", onMallFocusCapture, true);
    console.log("[HK-Deal] mall focus capture listener bound");
  }

  /** Kept for callers after render; capture listener already covers dynamic buttons. */
  function rebindMallFocusButtons(root) {
    bindMallOffersToggle(document);
    const scope = root || document;
    const list = scope.querySelector ? scope.querySelector("#mall-list") || scope : scope;
    if (!list || !list.querySelectorAll) return;
    const count = list.querySelectorAll("[data-mall-focus-toggle], button.mall-toggle").length;
    const withOffers = list.querySelectorAll(".mall-card .mall-offers-panel .offer-card").length;
    console.log("[HK-Deal] after render:", { toggleButtons: count, offerCardsInDom: withOffers });
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => bindMallOffersToggle(document));
    } else {
      bindMallOffersToggle(document);
    }
  }

  function diningOfferImageUrl(offer) {
    if (!offer || typeof offer !== "object") return DINING_IMAGE_FALLBACK;
    const src = String(
      offer.image || offer.photo_url || offer.logo_url || offer.banner || ""
    ).trim();
    if (/^https?:\/\//i.test(src)) return src;
    return DINING_IMAGE_FALLBACK;
  }

  /**
   * Build dining .offer-card HTML with facade image on top (used by SPA renderers).
   */
  function renderDiningOfferCardHtml(offer, extras) {
    const opts = extras && typeof extras === "object" ? extras : {};
    const detail = opts.detail || getDisplayOfferDetail(offer) || String((offer && offer.title) || "");
    const name = String((offer && offer.restaurant_name) || "").trim();
    const title = String((offer && offer.title) || name || "餐廳優惠");
    const img = diningOfferImageUrl(offer);
    const esc = (v) =>
      String(v == null ? "" : v)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    return (
      `<div class="offer-card-img-wrapper"><img class="offer-card-img" src="${esc(img)}" alt="${esc(title)}" loading="lazy" ${imgOnErrorAttr(DINING_IMAGE_FALLBACK)}></div>` +
      (opts.bodyHtml || `<div class="dining-offer-card__body"><h5>${esc(name || title)}</h5><p>${esc(detail)}</p></div>`)
    );
  }

  global.todayDateStr = todayDateStr;
  global.DINING_IMAGE_FALLBACK = DINING_IMAGE_FALLBACK;
  global.STORE_IMAGE_FALLBACK = STORE_IMAGE_FALLBACK;
  global.fetchJsonResource = fetchJsonResource;
  global.fetchMallFeed = fetchMallFeed;
  global.isValidMallFeed = isValidMallFeed;
  global.imgOnErrorAttr = imgOnErrorAttr;
  global.diningOfferImageUrl = diningOfferImageUrl;
  global.renderDiningOfferCardHtml = renderDiningOfferCardHtml;
  global.extractDiningOfferTitle = extractDiningOfferTitle;
  global.getDisplayOfferDetail = getDisplayOfferDetail;
  global.hasSubstantiveDiningOffer = hasSubstantiveDiningOffer;
  global.isSubstantiveOfferTitle = isSubstantiveOfferTitle;
  global.getOfferStatus = getOfferStatus;
  global.processStoreDeals = processStoreDeals;
  global.liveDiningOffers = liveDiningOffers;
  global.mallHasDiningOffers = mallHasDiningOffers;
  global.toggleMallFocusMode = toggleMallFocusMode;
  global.toggleMallOffersPanel = toggleMallOffersPanel;
  global.toggleDiningOffersSection = toggleDiningOffersSection;
  global.bindMallOffersToggle = bindMallOffersToggle;
  global.rebindMallFocusButtons = rebindMallFocusButtons;

  if (typeof module !== "undefined") {
    module.exports = {
      todayDateStr,
      extractDiningOfferTitle,
      getDisplayOfferDetail,
      hasSubstantiveDiningOffer,
      isSubstantiveOfferTitle,
      getOfferStatus,
      processStoreDeals,
      liveDiningOffers,
      mallHasDiningOffers,
      toggleMallFocusMode,
      toggleMallOffersPanel,
      toggleDiningOffersSection,
      bindMallOffersToggle,
      rebindMallFocusButtons,
      fetchMallFeed,
      fetchJsonResource,
      isValidMallFeed,
      imgOnErrorAttr,
      diningOfferImageUrl,
      renderDiningOfferCardHtml,
    };
  }
})(typeof window !== "undefined" ? window : globalThis);
