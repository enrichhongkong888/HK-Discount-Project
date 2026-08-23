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

  function isGenericOpenRiceTitle(text) {
    const t = String(text || "").trim();
    if (!t) return true;
    if (t.startsWith("OpenRice 門市／外賣常態禮遇")) return true;
    if (t === "門市／外賣優惠" || t === "OpenRice 門市／外賣優惠") return true;
    if (/^OpenRice\s/i.test(t) && t.length < 48 && t.includes("優惠")) return true;
    return false;
  }

  const DEFAULT_DINING_TITLE =
    "OpenRice 門市／外賣常態禮遇：堂食或外賣自取惠顧可享店內當期推廣；實際條款以 OpenRice App／店內告示為準。";

  function extractDiningOfferTitle(offer) {
    if (!offer || typeof offer !== "object") return DEFAULT_DINING_TITLE;
    const candidates = [];
    ["offer_name", "discount_text", "voucher_title", "title"].forEach((key) => {
      const val = String(offer[key] || "").trim();
      if (val) candidates.push(val);
    });
    const vouchers = offer.vouchers;
    if (Array.isArray(vouchers) && vouchers[0] && vouchers[0].title) {
      candidates.push(String(vouchers[0].title).trim());
    }
    const details = String(offer.details || "").trim();
    if (details) candidates.push(details);

    const seen = new Set();
    for (const candidate of candidates) {
      const parts = candidate.includes("｜") ? [candidate.split("｜").pop().trim()] : [candidate];
      for (const part of parts) {
        const text = String(part || "").trim();
        const key = text.toLowerCase();
        if (!text || seen.has(key)) continue;
        seen.add(key);
        if (!isGenericOpenRiceTitle(text)) {
          const normalized = text.replace(/^OpenRice\s+/i, "").trim();
          return isGenericOpenRiceTitle(normalized) ? text : normalized || text;
        }
      }
    }
    return DEFAULT_DINING_TITLE;
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
  global.getOfferStatus = getOfferStatus;
  global.processStoreDeals = processStoreDeals;
  global.liveDiningOffers = liveDiningOffers;
  global.mallHasDiningOffers = mallHasDiningOffers;

  if (typeof module !== "undefined") {
      module.exports = {
      todayDateStr,
      extractDiningOfferTitle,
      getOfferStatus,
      processStoreDeals,
      liveDiningOffers,
      mallHasDiningOffers,
    };
  }
})(typeof window !== "undefined" ? window : globalThis);
