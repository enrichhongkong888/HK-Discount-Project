// OpenRice 餐飲優惠 — 每日生命週期狀態引擎
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
  const LEGACY_DEFAULTS = [
    "店內當期指定餐飲優惠（請參閱門市告示）",
    "OpenRice 門市／外賣常態禮遇：堂食或外賣自取惠顧可享店內當期推廣；實際條款以 OpenRice App／店內告示為準。",
  ];

  function isGenericOpenRiceTitle(text) {
    const t = String(text || "").trim();
    if (!t) return true;
    if (t === DEFAULT_DINING_TITLE || LEGACY_DEFAULTS.includes(t)) return true;
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

  function extractDiningOfferTitle(offer) {
    if (!offer || typeof offer !== "object") return DEFAULT_DINING_TITLE;

    // 1. Prefer voucher / cash-coupon titles (join multiple).
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

    // 2. Specific discount / promo description fields.
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
      if (text && !isGenericOpenRiceTitle(text)) return text;
    }

    // 3. Booking / takeaway discount tags.
    const booking = String(
      offer.booking_discount_text || offer.takeaway_discount_text || ""
    ).trim();
    if (booking && !isGenericOpenRiceTitle(booking)) {
      return `線上預約享 ${booking}`;
    }

    // 4. Short placeholder — never long boilerplate.
    return DEFAULT_DINING_TITLE;
  }

  /** Display-layer helper: swap legacy generic copy for a short tip. */
  function getDisplayOfferDetail(offer) {
    if (!offer || typeof offer !== "object") return DEFAULT_DINING_TITLE;
    const title =
      offer.title || offer.offer_title || offer.discount_text || offer.offer_name || "";
    if (!title || isGenericOpenRiceTitle(title)) {
      return DEFAULT_DINING_TITLE;
    }
    // Prefer richer extraction when available (vouchers, booking tags, etc.).
    const extracted = extractDiningOfferTitle(offer);
    return extracted || DEFAULT_DINING_TITLE;
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
      const lifecycle = getOfferStatus(offer.start_date, offer.end_date, todayOverride);
      return lifecycle.status === "active" || lifecycle.status === "upcoming";
    });
  }

  function mallHasDiningOffers(mall, todayOverride) {
    return liveDiningOffers(mall, todayOverride).length > 0;
  }

  global.todayDateStr = todayDateStr;
  global.extractDiningOfferTitle = extractDiningOfferTitle;
  global.getDisplayOfferDetail = getDisplayOfferDetail;
  global.getOfferStatus = getOfferStatus;
  global.processStoreDeals = processStoreDeals;
  global.liveDiningOffers = liveDiningOffers;
  global.mallHasDiningOffers = mallHasDiningOffers;

  if (typeof module !== "undefined") {
      module.exports = {
      todayDateStr,
      extractDiningOfferTitle,
      getDisplayOfferDetail,
      getOfferStatus,
      processStoreDeals,
      liveDiningOffers,
      mallHasDiningOffers,
    };
  }
})(typeof window !== "undefined" ? window : globalThis);
