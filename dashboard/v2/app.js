(() => {
  'use strict';

  const view = document.getElementById('view');
  const title = document.getElementById('page-title');
  const eyebrow = document.getElementById('eyebrow');
  const readinessChip = document.getElementById('readiness-chip');
  const refreshButton = document.getElementById('refresh-button');
  const menuButton = document.getElementById('menu-button');
  const navBackdrop = document.getElementById('nav-backdrop');
  const installButton = document.getElementById('install-button');
  const notificationButton = document.getElementById('notification-button');
  const networkStatus = document.getElementById('network-status');
  const toast = document.getElementById('toast');
  let installPrompt = null;
  let pushConfig = null;

  const cache = new Map();
  const routes = {
    '/': ['overview', 'Overview', 'OUR HISTORY'],
    '/picks': ['picks', 'Games / Picks', 'OUR GAMES'],
    '/tickets': ['tickets', 'Tickets', 'OUR TICKETS'],
    '/performance': ['performance', 'Performance', 'OUR PERFORMANCE'],
    '/finance': ['finance', 'Finance', 'OUR BANKROLL'],
    '/strategies': ['strategies', 'Strategies', 'OUR STRATEGIES'],
    '/history': ['history', 'History', 'OUR RECORD'],
    '/blog': ['blog', 'Sabi Blog', 'SABI'],
    '/system': ['system', 'System', 'SYSTEM HEALTH'],
  };

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

  const num = (value, digits = 0) => {
    const n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString(undefined, {maximumFractionDigits: digits, minimumFractionDigits: digits}) : '—';
  };

  const money = (value) => {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    const sign = n < 0 ? '−' : '';
    return `${sign}${Math.abs(n).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
  };

  const pct = (value) => value == null ? '—' : `${num(value, 1)}%`;
  const odds = (value) => value == null ? '—' : num(value, 2);
  const date = (value) => {
    if (!value) return '—';
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? esc(value) : d.toLocaleDateString(undefined, {day:'2-digit', month:'short', year:'numeric'});
  };

  function outcomeBadge(value) {
    const text = String(value || 'unknown');
    const cls = text.toLowerCase().replaceAll(' ', '-');
    return `<span class="badge ${esc(cls)}">${esc(text)}</span>`;
  }

  async function api(path, force = false) {
    if (!force && cache.has(path)) return cache.get(path);
    const response = await fetch(`/api/v2${path}`, {headers: {'Accept': 'application/json'}, cache: 'no-store'});
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const data = await response.json();
    cache.set(path, data);
    return data;
  }

  function clearCache() { cache.clear(); }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add('show');
    window.setTimeout(() => toast.classList.remove('show'), 1800);
  }

  function closeMenu({restoreFocus = false} = {}) {
    document.body.classList.remove('nav-open');
    menuButton.setAttribute('aria-expanded', 'false');
    if (restoreFocus) menuButton.focus();
  }

  function openMenu() {
    document.body.classList.add('nav-open');
    menuButton.setAttribute('aria-expanded', 'true');
    document.querySelector('.nav a')?.focus();
  }

  function urlBase64ToUint8Array(value) {
    const padding = '='.repeat((4 - (value.length % 4)) % 4);
    const base64 = (value + padding).replaceAll('-', '+').replaceAll('_', '/');
    const raw = window.atob(base64);
    return Uint8Array.from([...raw].map(char => char.charCodeAt(0)));
  }

  function setNotificationButton(enabled, available = true) {
    notificationButton.textContent = enabled ? '●' : '♢';
    notificationButton.title = available
      ? (enabled ? 'Disable result notifications' : 'Enable result notifications')
      : 'Push notifications are not configured';
    notificationButton.setAttribute('aria-label', notificationButton.title);
    notificationButton.disabled = !available;
  }

  async function pushRegistration() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) return null;
    return navigator.serviceWorker.ready;
  }

  async function refreshPushState() {
    try {
      const response = await fetch('/api/v2/push/config', {headers: {'Accept':'application/json'}, cache:'no-store'});
      if (!response.ok) throw new Error('Push configuration unavailable');
      pushConfig = await response.json();
      const registration = await pushRegistration();
      if (!pushConfig.available || !registration) {
        setNotificationButton(false, false);
        return;
      }
      const subscription = await registration.pushManager.getSubscription();
      setNotificationButton(Boolean(subscription));
    } catch (_) {
      setNotificationButton(false, false);
    }
  }

  async function toggleNotifications() {
    const registration = await pushRegistration();
    if (!registration || !pushConfig?.available) {
      showToast('Push notifications are unavailable on this device.');
      return;
    }
    const existing = await registration.pushManager.getSubscription();
    if (existing) {
      const response = await fetch('/api/v2/push/subscriptions', {
        method: 'DELETE',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({endpoint: existing.endpoint}),
      });
      if (!response.ok) throw new Error('The notification subscription could not be removed.');
      await existing.unsubscribe();
      setNotificationButton(false);
      showToast('Result notifications disabled');
      return;
    }
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      showToast('Notification permission was not granted.');
      return;
    }
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(pushConfig.public_key),
    });
    const payload = subscription.toJSON();
    const response = await fetch('/api/v2/push/subscriptions', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({endpoint: payload.endpoint, keys: payload.keys}),
    });
    if (!response.ok) {
      await subscription.unsubscribe();
      throw new Error('The subscription could not be saved.');
    }
    setNotificationButton(true);
    await registration.showNotification('Sabi notifications are on', {
      body: 'Automatic settlement updates can now reach this device.',
      icon: '/assets/icon-192.png',
      tag: 'sabi-boy-push-enabled',
    });
  }

  async function registerPwa() {
    if (!('serviceWorker' in navigator)) {
      installButton.hidden = true;
      setNotificationButton(false, false);
      return;
    }
    try {
      const registration = await navigator.serviceWorker.register('/sw.js', {scope:'/'});
      registration.addEventListener('updatefound', () => {
        if (navigator.serviceWorker.controller) showToast('A Sabi update is downloading.');
      });
      await refreshPushState();
    } catch (error) {
      console.error(error);
      setNotificationButton(false, false);
    }
  }

  function updateNetworkStatus() {
    networkStatus.textContent = navigator.onLine ? '' : 'Offline';
    if (navigator.onLine) clearCache();
  }

  function empty(titleText, detail = 'There is no recorded data for this view yet.') {
    return `<div class="empty-state"><div><strong>${esc(titleText)}</strong><p>${esc(detail)}</p></div></div>`;
  }

  function metric(label, value, foot = '', cls = '') {
    return `<div class="metric"><div class="metric-label">${esc(label)}</div><div class="metric-value ${esc(cls)}">${value}</div><div class="metric-foot">${esc(foot)}</div></div>`;
  }

  function sectionHead(name, description = '', meta = '') {
    return `<div class="section-head"><div><h2>${esc(name)}</h2>${description ? `<p>${esc(description)}</p>` : ''}</div>${meta ? `<div class="meta">${esc(meta)}</div>` : ''}</div>`;
  }

  function table(headers, rows) {
    if (!rows.length) return empty('Nothing recorded yet');
    return `<div class="table-wrap"><table><thead><tr>${headers.map(h => `<th class="${h.num ? 'num' : ''}">${esc(h.label)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${headers.map(h => `<td class="${h.num ? 'num' : ''}">${h.render ? h.render(row) : esc(row[h.key])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }

  function barList(rows, labelKey, valueKey = 'win_percentage', suffix = '%') {
    if (!rows.length) return empty('Not enough data');
    const values = rows.map(r => Number(r[valueKey]) || 0);
    const max = Math.max(...values, 1);
    return `<div class="bar-list">${rows.slice(0, 12).map(row => {
      const v = Number(row[valueKey]) || 0;
      return `<div class="bar-row"><div class="bar-name" title="${esc(row[labelKey])}">${esc(row[labelKey])}</div><div class="bar-track"><div class="bar-fill" style="width:${Math.max(1,(v/max)*100)}%"></div></div><div class="bar-value">${num(v, valueKey.includes('percentage') ? 1 : 0)}${suffix}</div></div>`;
    }).join('')}</div>`;
  }

  function lineChart(rows, xKey, yKey) {
    if (!rows || rows.length < 2) return empty('Not enough history for a trend line', 'The chart will appear as our record grows.');
    const data = rows.map(r => ({x: r[xKey], y: Number(r[yKey])})).filter(r => Number.isFinite(r.y));
    if (data.length < 2) return empty('Not enough history for a trend line');
    const ys = data.map(d => d.y);
    let min = Math.min(...ys), max = Math.max(...ys);
    if (min === max) { min -= 1; max += 1; }
    const w = 700, h = 220, px = 24, py = 20;
    const x = i => px + (i / (data.length - 1)) * (w - px * 2);
    const y = v => h - py - ((v - min) / (max - min)) * (h - py * 2);
    const points = data.map((d,i) => `${x(i).toFixed(1)},${y(d.y).toFixed(1)}`).join(' ');
    const area = `${px},${h-py} ${points} ${w-px},${h-py}`;
    const grid = [0,.25,.5,.75,1].map(frac => {
      const gy = py + frac * (h - py*2);
      const val = max - frac * (max-min);
      return `<line class="chart-grid" x1="${px}" y1="${gy}" x2="${w-px}" y2="${gy}"/><text class="chart-label" x="0" y="${gy+3}">${esc(num(val,2))}</text>`;
    }).join('');
    return `<div class="chart-wrap"><svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Trend chart"><defs><linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e6b252" stop-opacity=".22"/><stop offset="1" stop-color="#e6b252" stop-opacity="0"/></linearGradient></defs>${grid}<polygon class="chart-area" points="${area}"/><polyline class="chart-line" points="${points}"/>${data.map((d,i) => `<circle class="chart-dot" cx="${x(i)}" cy="${y(d.y)}" r="2.8"><title>${esc(d.x)}: ${esc(d.y)}</title></circle>`).join('')}</svg></div>`;
  }

  function outcomeTrend(rows) {
    if (!rows.length) return empty('No settled history yet');
    let won = 0, lost = 0;
    const cumulative = rows.map(row => {
      won += Number(row.won || 0); lost += Number(row.lost || 0);
      const decided = won + lost;
      return {day: row.day, rate: decided ? (won / decided) * 100 : 0};
    });
    return lineChart(cumulative, 'day', 'rate');
  }

  async function readiness(force = false) {
    try {
      const r = await api('/system/readiness', force);
      const cls = r.state.toLowerCase().replaceAll(' ', '-');
      readinessChip.className = `status-chip ${cls}`;
      readinessChip.innerHTML = `<span></span><b>${esc(r.state)}</b>`;
    } catch (_) {
      readinessChip.className = 'status-chip action-locked';
      readinessChip.innerHTML = '<span></span><b>Unavailable</b>';
    }
  }

  async function renderOverview() {
    const [o, outcomes, bankroll, sports] = await Promise.all([
      api('/overview'), api('/series/outcomes?days=60'), api('/series/bankroll?limit=365'), api('/performance/sports')
    ]);
    const p = o.summary.picks || {};
    const pl = o.profit_loss.betting || {};
    const current = o.streaks.current || {};
    const streakText = current.count ? `${current.count} ${current.type === 'won' ? 'W' : 'L'}` : '—';
    const pnlN = Number(pl.profit_loss || 0);
    const bankrollRows = bankroll.rows || [];

    view.innerHTML = `
      <section class="section"><div class="hero-grid">
        ${metric('Bankroll', money(o.summary.bankroll), 'Current recorded balance', 'accent')}
        ${metric('Betting P/L', money(pl.profit_loss), 'Stakes, payouts and refunds only', pnlN >= 0 ? 'positive' : 'negative')}
        ${metric('Win rate', pct(p.win_percentage), `${p.won || 0} won · ${p.lost || 0} lost`)}
        ${metric('Current streak', streakText, `Best: ${o.streaks.best_win_streak || 0}W · Worst: ${o.streaks.worst_losing_streak || 0}L`)}
      </div></section>

      <section class="section grid-2">
        <div class="panel"><div class="panel-head"><h3>Bankroll over time</h3><span>${bankrollRows.length} ledger points</span></div><div class="panel-body">${lineChart(bankrollRows, 'occurred_at', 'balance')}</div></div>
        <div class="panel"><div class="panel-head"><h3>By sport</h3><span>Our record only</span></div><div class="panel-body">${barList(sports.rows || [], 'sport')}</div></div>
      </section>

      <section class="section grid-equal">
        <div class="panel"><div class="panel-head"><h3>Win rate trend</h3><span>Settled picks</span></div><div class="panel-body">${outcomeTrend(outcomes.rows || [])}</div></div>
        <div class="panel"><div class="panel-head"><h3>Record</h3><span>All picks</span></div><div class="panel-body stat-stack">
          <div class="stat-line"><span>Won</span><strong>${num(p.won)}</strong></div>
          <div class="stat-line"><span>Lost</span><strong>${num(p.lost)}</strong></div>
          <div class="stat-line"><span>Draw</span><strong>${num(p.draw)}</strong></div>
          <div class="stat-line"><span>Void</span><strong>${num(p.void)}</strong></div>
          <div class="stat-line"><span>Pending</span><strong>${num(p.pending)}</strong></div>
        </div></div>
      </section>

      <section class="section">${sectionHead('Recent games', 'The latest picks in our record')}
        <div class="panel flush"><div class="panel-body">${picksTable(o.recent_picks || [])}</div></div>
      </section>

      <section class="section">${sectionHead('Recent tickets', 'The latest ticket versions in our record')}
        ${ticketCards(o.recent_tickets || [])}
      </section>`;
  }

  function picksTable(rows) {
    return table([
      {label:'Game', render:r => `<span class="primary-cell">${esc(r.event)}</span><span class="sub-cell">${esc(r.sport || '')}${r.competition ? ` · ${esc(r.competition)}` : ''}</span>`},
      {label:'Pick', render:r => `<span class="primary-cell">${esc(r.selection)}</span><span class="sub-cell">${esc(r.market || '')}</span>`},
      {label:'Odds', num:true, render:r => odds(r.decimal_odds)},
      {label:'Strategy', render:r => esc(r.strategy || '—')},
      {label:'Result', render:r => outcomeBadge(r.outcome)},
      {label:'Date', render:r => date(r.created_at)},
    ], rows);
  }

  function ticketCards(rows) {
    if (!rows.length) return empty('No tickets recorded yet');
    return `<div class="ticket-list">${rows.map(r => `<article class="ticket-card" data-ticket-id="${esc(r.id)}">
      <div class="ticket-top"><div><div class="ticket-code">${esc(r.bookmaker || r.source_type || 'Ticket')}</div><div class="ticket-odds">${odds(r.combined_odds)}</div></div>${outcomeBadge(r.status)}</div>
      <div class="ticket-meta"><span>${num(r.leg_count)} games</span><span>${date(r.created_at)}</span>${r.booking_code ? `<span>Code ${esc(r.booking_code)}</span>` : ''}</div>
      <div class="ticket-result-line"><span><b>${num(r.won_legs)}</b> won</span><span><b>${num(r.lost_legs)}</b> lost</span><span><b>${num(r.pending_legs)}</b> pending</span>${r.parent_ticket_id ? '<span>Edited version</span>' : '<span>Original</span>'}</div>
    </article>`).join('')}</div>`;
  }

  async function renderPicks() {
    const [data, filters] = await Promise.all([api('/picks?limit=300'), api('/filters')]);
    view.innerHTML = `<section class="section">${sectionHead('Games / Picks', 'Every recorded selection, with our outcome and context', `${(data.rows||[]).length} shown`)}
      <div class="filter-row">
        <select id="pick-result"><option value="">All results</option>${['won','lost','draw','void','pending'].map(x => `<option>${x}</option>`).join('')}</select>
        <select id="pick-sport"><option value="">All sports</option>${(filters.sports||[]).map(x => `<option>${esc(x)}</option>`).join('')}</select>
        <select id="pick-strategy"><option value="">All strategies</option>${(filters.strategies||[]).map(x => `<option>${esc(x)}</option>`).join('')}</select>
      </div>
      <div class="panel flush"><div class="panel-body" id="picks-table">${picksTable(data.rows || [])}</div></div></section>`;

    const update = async () => {
      const result = document.getElementById('pick-result').value;
      const sport = document.getElementById('pick-sport').value;
      const strategy = document.getElementById('pick-strategy').value;
      const qs = new URLSearchParams({limit:'500'});
      if (result) qs.set('outcome', result);
      if (sport) qs.set('sport', sport);
      if (strategy) qs.set('strategy', strategy);
      const rows = (await api(`/picks?${qs}`, true)).rows || [];
      document.getElementById('picks-table').innerHTML = picksTable(rows);
    };
    ['pick-result','pick-sport','pick-strategy'].forEach(id => document.getElementById(id).addEventListener('change', update));
  }

  async function renderTickets() {
    const [data, killers, sizes] = await Promise.all([api('/tickets?limit=250'), api('/tickets/killers?limit=12'), api('/performance/ticket-sizes')]);
    view.innerHTML = `
      <section class="section">${sectionHead('Tickets', 'Original tickets and every edited version we actually recorded', `${(data.rows||[]).length} shown`)}
        ${ticketCards(data.rows || [])}
      </section>
      <section class="section grid-equal">
        <div class="panel"><div class="panel-head"><h3>Performance by ticket size</h3><span>Our tickets</span></div><div class="panel-body">${barList(sizes.rows || [], 'leg_count')}</div></div>
        <div class="panel flush"><div class="panel-head"><h3>One game killed it</h3><span>Recent</span></div><div class="panel-body">${table([
          {label:'Ticket', render:r => `<span class="primary-cell">${esc(r.event)}</span><span class="sub-cell">${esc(r.selection)}</span>`},
          {label:'Odds', num:true, render:r => odds(r.decimal_odds)},
          {label:'Ticket odds', num:true, render:r => odds(r.combined_odds)},
        ], killers.rows || [])}</div></div>
      </section>`;
  }

  async function renderPerformance() {
    const [sports, markets, books, oddsBands, competitions] = await Promise.all([
      api('/performance/sports'), api('/performance/markets'), api('/performance/bookmakers'), api('/performance/odds-bands'), api('/performance/competitions')
    ]);
    const performanceTable = rows => table([
      {label:'Group', render:r => `<span class="primary-cell">${esc(r.sport || r.market || r.bookmaker || r.odds_band || r.competition || '—')}</span>`},
      {label:'Played', num:true, render:r => num(r.played)},
      {label:'Won', num:true, render:r => num(r.won)},
      {label:'Lost', num:true, render:r => num(r.lost)},
      {label:'Win rate', num:true, render:r => pct(r.win_percentage)},
    ], rows);
    view.innerHTML = `
      <section class="section grid-equal">
        <div class="panel"><div class="panel-head"><h3>Sports</h3><span>Win rate</span></div><div class="panel-body">${barList(sports.rows||[],'sport')}</div></div>
        <div class="panel"><div class="panel-head"><h3>Odds ranges</h3><span>Win rate</span></div><div class="panel-body">${barList(oddsBands.rows||[],'odds_band')}</div></div>
      </section>
      <section class="section">${sectionHead('By market', 'Which selections have worked for us')}
        <div class="panel flush"><div class="panel-body">${performanceTable(markets.rows||[])}</div></div>
      </section>
      <section class="section grid-equal">
        <div class="panel flush"><div class="panel-head"><h3>Bookmakers</h3><span>Our recorded picks</span></div><div class="panel-body">${performanceTable(books.rows||[])}</div></div>
        <div class="panel flush"><div class="panel-head"><h3>Competitions</h3><span>Our recorded picks</span></div><div class="panel-body">${performanceTable(competitions.rows||[])}</div></div>
      </section>`;
  }

  async function renderFinance() {
    const [pl, series] = await Promise.all([api('/history/profit_loss'), api('/series/bankroll?limit=1000')]);
    const b = pl.betting || {}, f = pl.funding || {};
    const pnlN = Number(b.profit_loss || 0);
    view.innerHTML = `
      <section class="section"><div class="hero-grid">
        ${metric('Bankroll', money(pl.bankroll), 'Recorded balance', 'accent')}
        ${metric('Betting P/L', money(b.profit_loss), 'Excludes deposits and withdrawals', pnlN >= 0 ? 'positive' : 'negative')}
        ${metric('Total stakes', money(b.stakes), 'Stake ledger entries')}
        ${metric('Payouts', money(b.payouts), `Refunds ${money(b.refunds)}`)}
      </div></section>
      <section class="section"><div class="panel"><div class="panel-head"><h3>Bankroll</h3><span>${(series.rows||[]).length} entries</span></div><div class="panel-body">${lineChart(series.rows||[], 'occurred_at', 'balance')}</div></div></section>
      <section class="section grid-equal">
        <div class="panel"><div class="panel-head"><h3>Betting cashflow</h3><span>Performance</span></div><div class="panel-body stat-stack">
          <div class="stat-line"><span>Stakes</span><strong>${money(b.stakes)}</strong></div>
          <div class="stat-line"><span>Payouts</span><strong>${money(b.payouts)}</strong></div>
          <div class="stat-line"><span>Refunds</span><strong>${money(b.refunds)}</strong></div>
          <div class="stat-line"><span>Net betting P/L</span><strong class="${pnlN >= 0 ? 'positive':'negative'}">${money(b.profit_loss)}</strong></div>
        </div></div>
        <div class="panel"><div class="panel-head"><h3>Funding</h3><span>Not counted as profit</span></div><div class="panel-body stat-stack">
          <div class="stat-line"><span>Deposits + opening</span><strong>${money(f.deposits_and_opening)}</strong></div>
          <div class="stat-line"><span>Withdrawals</span><strong>${money(f.withdrawals)}</strong></div>
          <div class="stat-line"><span>Adjustments</span><strong>${money(f.adjustments)}</strong></div>
        </div></div>
      </section>`;
  }

  async function renderStrategies() {
    const data = await api('/performance/strategies');
    const rows = data.rows || [];
    view.innerHTML = `<section class="section">${sectionHead('Strategies', 'How each of our recorded approaches has performed')}
      <div class="grid-equal">
        <div class="panel"><div class="panel-head"><h3>Win rate</h3><span>Decided picks</span></div><div class="panel-body">${barList(rows,'strategy')}</div></div>
        <div class="panel flush"><div class="panel-head"><h3>Breakdown</h3><span>Our record</span></div><div class="panel-body">${table([
          {label:'Strategy', render:r=>`<span class="primary-cell">${esc(r.strategy)}</span>`},
          {label:'Played', num:true, render:r=>num(r.played)},
          {label:'Won', num:true, render:r=>num(r.won)},
          {label:'Lost', num:true, render:r=>num(r.lost)},
          {label:'Win rate', num:true, render:r=>pct(r.win_percentage)},
        ], rows)}</div></div>
      </div></section>`;
  }

  async function renderHistory() {
    const [picks, sources, combined, outcomes] = await Promise.all([
      api('/picks?limit=500'), api('/tickets/sources'), api('/performance/combined-odds'), api('/series/outcomes?days=180')
    ]);
    view.innerHTML = `
      <section class="section grid-equal">
        <div class="panel"><div class="panel-head"><h3>Win rate over time</h3><span>Our settled picks</span></div><div class="panel-body">${outcomeTrend(outcomes.rows||[])}</div></div>
        <div class="panel"><div class="panel-head"><h3>Ticket odds ranges</h3><span>Win rate</span></div><div class="panel-body">${barList(combined.rows||[],'combined_odds_band')}</div></div>
      </section>
      <section class="section">${sectionHead('Original vs edited tickets', 'How ticket versions have performed')}
        <div class="panel flush"><div class="panel-body">${table([
          {label:'Version', render:r=>`<span class="primary-cell">${esc(r.version_type)}</span><span class="sub-cell">${esc(r.source_type)}</span>`},
          {label:'Tickets', num:true, render:r=>num(r.tickets)},
          {label:'Won', num:true, render:r=>num(r.won)},
          {label:'Lost', num:true, render:r=>num(r.lost)},
          {label:'Win rate', num:true, render:r=>pct(r.win_percentage)},
        ], sources.rows||[])}</div></div>
      </section>
      <section class="section">${sectionHead('Full recent record', 'Latest 500 recorded picks')}
        <div class="panel flush"><div class="panel-body">${picksTable(picks.rows||[])}</div></div>
      </section>`;
  }

  async function renderBlog() {
    const data = await api('/blog?limit=100');
    const posts = data.posts || [];
    view.innerHTML = `<section class="section">${sectionHead('Sabi Blog', 'Thoughts, lessons, postmortems and reflections from our own journey')}
      ${posts.length ? `<div class="blog-grid">${posts.map(p => `<article class="blog-card" data-blog-slug="${esc(p.slug)}"><div class="category">${esc(p.category || 'Sabi')}</div><h2>${esc(p.title)}</h2><p>${esc(p.excerpt || String(p.body||'').slice(0,190))}</p><footer>${date(p.published_at || p.created_at)}${p.tags?.length ? ` · ${p.tags.slice(0,3).map(esc).join(' · ')}` : ''}</footer></article>`).join('')}</div>` : empty('Sabi has not published a post yet', 'The blog will build continuity from our actual record and reflections.')}
    </section>`;
  }

  async function renderBlogPost(slug) {
    const p = await api(`/blog/${encodeURIComponent(slug)}`);
    view.innerHTML = `<article class="article"><a class="article-back" href="/blog" data-route="blog">← Back to Sabi Blog</a><div class="category">${esc(p.category || 'Sabi')}</div><h1>${esc(p.title)}</h1><div class="article-meta">${date(p.published_at || p.created_at)}</div><div class="article-body">${esc(p.body)}</div>${p.tags?.length ? `<div class="tags">${p.tags.map(tag=>`<span class="tag">${esc(tag)}</span>`).join('')}</div>` : ''}</article>`;
  }

  async function renderSystem() {
    const [ready, sources, economy] = await Promise.all([api('/system/readiness'), api('/system/sources'), api('/system/api-economy')]);
    const sourceRows = sources.sources || [];
    view.innerHTML = `
      <section class="section"><div class="system-grid">
        <div class="system-card"><label>State</label><strong>${outcomeBadge(ready.state)}</strong></div>
        <div class="system-card"><label>Database</label><strong>${ready.database_ok ? 'Healthy' : 'Needs attention'}</strong></div>
        <div class="system-card"><label>Bankroll ledger</label><strong>${ready.bankroll_ok ? 'Reconciles' : 'Mismatch'}</strong></div>
        <div class="system-card"><label>Settlement backlog</label><strong>${num(ready.stale_settlements)}</strong></div>
      </div></section>
      <section class="section grid-equal">
        <div class="panel"><div class="panel-head"><h3>API economy</h3><span>Free-first</span></div><div class="panel-body stat-stack">
          ${Object.entries(economy||{}).map(([k,v])=>`<div class="stat-line"><span>${esc(k.replaceAll('_',' '))}</span><strong>${typeof v === 'number' ? num(v) : esc(v)}</strong></div>`).join('') || '<div class="stat-line"><span>No source usage yet</span><strong>—</strong></div>'}
        </div></div>
        <div class="panel"><div class="panel-head"><h3>Readiness issues</h3><span>${(ready.issues||[]).length}</span></div><div class="panel-body issue-list">
          ${(ready.issues||[]).length ? ready.issues.map(i=>`<div class="issue"><div>${outcomeBadge(i.severity)}</div><p><b>${esc(i.area)}</b> — ${esc(i.message)}</p></div>`).join('') : '<div class="stat-line"><span>No current readiness issues</span><strong>✓</strong></div>'}
        </div></div>
      </section>
      <section class="section">${sectionHead('Sources', 'What Sabi has actually been using and how those sources are behaving')}
        <div class="panel flush"><div class="panel-body">${table([
          {label:'Source', render:r=>`<span class="primary-cell">${esc(r.name)}</span>`},
          {label:'State', render:r=>outcomeBadge(r.state)},
          {label:'Requests', num:true, render:r=>num(r.requests)},
          {label:'Success', num:true, render:r=>num(r.successes)},
          {label:'Failures', num:true, render:r=>num(r.failures)},
          {label:'Cache hits', num:true, render:r=>num(r.cache_hits)},
          {label:'Paid', num:true, render:r=>num(r.paid_calls)},
        ], sourceRows)}</div></div>
      </section>`;
  }

  async function renderTicketDetail(id) {
    const t = await api(`/tickets/${encodeURIComponent(id)}`);
    const legs = t.legs || [];
    view.innerHTML = `<section class="section"><a class="article-back" href="/tickets" data-route="tickets">← Back to tickets</a><div class="hero-grid">
      ${metric('Combined odds', odds(t.combined_odds), `${legs.length} games`, 'accent')}
      ${metric('Status', outcomeBadge(t.status), t.bookmaker || t.source_type || '')}
      ${metric('Stake', money(t.stake), 'Recorded stake')}
      ${metric('Payout', money(t.payout), 'Recorded payout')}
    </div></section>
    <section class="section">${sectionHead('Ticket legs', t.parent_ticket_id ? 'Edited version' : 'Original ticket')}
      <div class="panel flush"><div class="panel-body">${table([
        {label:'#', num:true, render:r=>num(r.leg_no)},
        {label:'Game', render:r=>`<span class="primary-cell">${esc(r.event)}</span><span class="sub-cell">${esc(r.sport)}${r.competition ? ` · ${esc(r.competition)}` : ''}</span>`},
        {label:'Pick', render:r=>`<span class="primary-cell">${esc(r.selection)}</span><span class="sub-cell">${esc(r.market)}</span>`},
        {label:'Odds', num:true, render:r=>odds(r.decimal_odds)},
        {label:'Result', render:r=>outcomeBadge(r.outcome)},
      ], legs)}</div></div>
    </section>`;
  }

  const renderers = { overview:renderOverview, picks:renderPicks, tickets:renderTickets, performance:renderPerformance, finance:renderFinance, strategies:renderStrategies, history:renderHistory, blog:renderBlog, system:renderSystem };

  function pathRoute(pathname) {
    if (pathname.startsWith('/blog/') && pathname.length > 6) return ['blog-post','Blog','SABI'];
    if (pathname.startsWith('/tickets/') && pathname.length > 9) return ['ticket-detail','Ticket','OUR TICKETS'];
    return routes[pathname] || routes['/'];
  }

  async function render(force = false) {
    if (force) clearCache();
    const [name, pageTitle, eye] = pathRoute(location.pathname);
    title.textContent = pageTitle; eyebrow.textContent = eye;
    document.querySelectorAll('.nav a').forEach(a => a.classList.toggle('active', a.dataset.route === (name === 'blog-post' ? 'blog' : name === 'ticket-detail' ? 'tickets' : name)));
    view.innerHTML = '<div class="loading-state"><div class="spinner"></div><p>Loading our record…</p></div>';
    try {
      if (name === 'blog-post') await renderBlogPost(decodeURIComponent(location.pathname.slice('/blog/'.length)));
      else if (name === 'ticket-detail') await renderTicketDetail(decodeURIComponent(location.pathname.slice('/tickets/'.length)));
      else await renderers[name]();
    } catch (err) {
      console.error(err);
      view.innerHTML = empty('This view could not be loaded', err.message || 'The V2 data service is unavailable.');
    }
    readiness(force);
  }

  function navigate(path) {
    history.pushState({}, '', path);
    closeMenu();
    render();
    window.scrollTo({top:0, behavior:'instant'});
  }

  document.addEventListener('click', e => {
    const link = e.target.closest('a[data-route]');
    if (link && link.origin === location.origin) { e.preventDefault(); navigate(link.pathname); return; }
    const ticket = e.target.closest('[data-ticket-id]');
    if (ticket) { navigate(`/tickets/${encodeURIComponent(ticket.dataset.ticketId)}`); return; }
    const post = e.target.closest('[data-blog-slug]');
    if (post) { navigate(`/blog/${encodeURIComponent(post.dataset.blogSlug)}`); }
  });

  menuButton.setAttribute('aria-expanded', 'false');
  menuButton.addEventListener('click', () => document.body.classList.contains('nav-open') ? closeMenu() : openMenu());
  navBackdrop.addEventListener('click', () => closeMenu({restoreFocus:true}));
  notificationButton.addEventListener('click', () => toggleNotifications().catch(error => showToast(error.message || 'Notifications could not be changed.')));
  installButton.addEventListener('click', async () => {
    if (installPrompt) {
      await installPrompt.prompt();
      await installPrompt.userChoice;
      installPrompt = null;
      installButton.hidden = true;
    } else {
      showToast('Use your browser menu and choose Add to Home Screen.');
    }
  });
  refreshButton.addEventListener('click', async () => { refreshButton.textContent = '…'; await render(true); refreshButton.textContent = '↻'; showToast('Refreshed'); });
  window.addEventListener('popstate', () => render());
  window.addEventListener('keydown', e => { if (e.key === 'Escape') closeMenu({restoreFocus:true}); });
  window.addEventListener('online', updateNetworkStatus);
  window.addEventListener('offline', updateNetworkStatus);
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    installPrompt = event;
    installButton.hidden = false;
  });
  window.addEventListener('appinstalled', () => { installButton.hidden = true; showToast('Sabi installed'); });

  if (window.matchMedia('(display-mode: standalone)').matches) installButton.hidden = true;
  updateNetworkStatus();
  registerPwa();
  render();
})();
