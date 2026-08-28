(() => {
  'use strict';

  const esc = value => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
  const num = value => {
    const n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString() : '—';
  };

  async function coverageData() {
    const response = await fetch('/api/v2/research/funnel', {
      headers: {'Accept': 'application/json'},
      cache: 'no-store',
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function metric(label, value, detail = '') {
    return `<div class="metric"><div class="metric-label">${esc(label)}</div><div class="metric-value">${esc(value)}</div><div class="metric-foot">${esc(detail)}</div></div>`;
  }

  function sportRows(data) {
    const sports = Array.isArray(data?.details?.sports) ? data.details.sports : [];
    if (!sports.length) return '<div class="empty-state"><div><strong>No radar coverage recorded yet</strong><p>The deterministic discovery timer will populate this after its first run.</p></div></div>';
    return `<div class="table-wrap"><table><thead><tr><th>Sport</th><th class="num">Games</th><th class="num">Priced</th><th class="num">Sources</th><th>Market families</th><th>Missing minimum</th></tr></thead><tbody>${sports.map(row => {
      const families = Array.isArray(row.market_families) ? row.market_families : [];
      const missing = Array.isArray(row.missing_minimum) ? row.missing_minimum : [];
      return `<tr><td><span class="primary-cell">${esc(row.sport)}</span></td><td class="num">${num(row.events)}</td><td class="num">${num(row.priced_events)}</td><td class="num">${num(row.source_count)}</td><td>${esc(families.length ? families.join(', ') : '—')}</td><td>${missing.length ? `<span class="badge pending">${esc(missing.join(', '))}</span>` : '<span class="badge won">covered</span>'}</td></tr>`;
    }).join('')}</tbody></table></div>`;
  }

  async function render() {
    if (location.pathname !== '/system') return;
    const view = document.getElementById('view');
    if (!view || view.querySelector('[data-coverage-engine]')) return;
    try {
      const data = await coverageData();
      if (location.pathname !== '/system' || !document.getElementById('view')) return;
      const section = document.createElement('section');
      section.className = 'section';
      section.dataset.coverageEngine = 'v2.4';
      const completed = data.completed_at ? new Date(data.completed_at).toLocaleString() : 'not run yet';
      section.innerHTML = `
        <div class="section-head"><div><h2>Discovery → decision funnel</h2><p>Cheap deterministic coverage is deliberately much larger than the AI research universe.</p></div><div class="meta">${esc(completed)}</div></div>
        <div class="metrics-grid">
          ${metric('Discovered', num(data.discovered), 'canonical events')}
          ${metric('Priced', num(data.priced), `${Number(data.priced_pct || 0).toFixed(1)}% of discovered`)}
          ${metric('Market catalogue', num(data.market_catalogue), 'distinct market definitions')}
          ${metric('Price observations', num(data.market_offers), 'retained market snapshots')}
          ${metric('Pre-filtered', num(data.prefiltered), 'eligible for deeper work')}
          ${metric('Researched', num(data.researched), 'bounded model universe')}
          ${metric('Selected', num(data.selected), 'final recommendations')}
        </div>
        <div class="panel flush"><div class="panel-head"><h3>Sport & market coverage</h3><span>${num((data.details?.sports || []).length)} sports</span></div><div class="panel-body">${sportRows(data)}</div></div>`;
      view.appendChild(section);
    } catch (error) {
      console.warn('Sabi Boy coverage telemetry unavailable', error);
    }
  }

  const observer = new MutationObserver(() => window.setTimeout(render, 0));
  const view = document.getElementById('view');
  if (view) observer.observe(view, {childList: true, subtree: true});
  window.addEventListener('popstate', () => window.setTimeout(render, 0));
  document.addEventListener('click', event => {
    if (event.target.closest('a[data-route="system"]')) window.setTimeout(render, 100);
  });
  window.setTimeout(render, 100);
})();
