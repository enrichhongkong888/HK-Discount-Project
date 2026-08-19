// 優惠日期過濾與分類核心邏輯
function processStoreDeals(deals) {
  const now = new Date();
  const todayStr = now.toISOString().split('T')[0];
  
  const threeDaysLater = new Date(now);
  threeDaysLater.setDate(now.getDate() + 3);
  const threeDaysLaterStr = threeDaysLater.toISOString().split('T')[0];

  const activeDeals = [];   // 🔥 今日進行中
  const upcomingDeals = []; // ⏳ 3天內即將開始

  if (!Array.isArray(deals)) return { activeDeals, upcomingDeals };

  deals.forEach(deal => {
    const startDate = deal.start_date || "2026-01-01";
    const endDate = deal.end_date || deal.valid_until || "2099-12-31";

    // 1. 今日進行中: 開始日期 <= 今日 AND 結束日期 >= 今日
    if (startDate <= todayStr && endDate >= todayStr) {
      activeDeals.push({
        ...deal,
        badgeType: 'active',
        badgeText: '🔥 今日進行中'
      });
    } 
    // 2. 3天內即將開始: 開始日期介於 (今日+1天) 至 (今日+3天)
    else if (startDate > todayStr && startDate <= threeDaysLaterStr) {
      const startMs = new Date(startDate).getTime();
      const todayMs = new Date(todayStr).getTime();
      const diffDays = Math.ceil((startMs - todayMs) / (1000 * 60 * 60 * 24));

      upcomingDeals.push({
        ...deal,
        badgeType: 'upcoming',
        badgeText: `⏳ ${diffDays} 天後開始`
      });
    }
  });

  return { activeDeals, upcomingDeals };
}

// 導出模組或綁定至全域
if (typeof module !== 'undefined') {
  module.exports = { processStoreDeals };
}
