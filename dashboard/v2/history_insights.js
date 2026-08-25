(() => {
  'use strict';

  const view = document.getElementById('view');
  if (!view) return;

  let loading = false;

  const esc = value => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

  const num = (value, digits = 0) => {
    const n = Number(value);
    return Number.isFinite(n)
      ? n.toLocaleString(undefined, {maximumFractionDigits: digits, minimumFractionDigits: digits})
      : '—';
  };

  const odds = value => value == null ? '—' : num(value, 2);

  const date = value => {
    if (!value) return '—';
    const d = new Date(value);
    return Number.isNaN(d.getTime())
      ? esc(value)
      : d.toLocaleDateString(undefined, {day:'2-digit', month:'short', year:'numeric'});
  };

  async function api(path) {
    const response = await fetch(`/api/v2${path}`, {
      headers: {'Accept': 'application/json'},
      cache: 'no-store',
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function resultBadge(value) {
    const labels = {
      improved_result: ['won', 'Improved'],
      worsened_result: ['lost', 'Worsened'],
      both_won: ['won', 'Both won'],
      both_lost: ['lost', 'Both lost'],
      other_or_unsettled: ['pending', 'Other / unsettled'],
    };
    const [cls, label] = labels[value] || ['pending', value || 'Unknown'];
    return `<span class="badge ${cls}">${esc(label)}</span>`;
  }

  function table(headers, rows) {
    if (!rows.length) {
      return '<div class="empty-state"><div><strong>Nothing recorded yet</strong><p>This view will build as our history grows.</p></div></div>';
    }
    return `<div class="table-wrap"><table><thead><tr>${headers.map(h => `<th class="${h.num ? 'num' : ''}">${esc(h.label)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${headers.map(h => `<td class="${h.num ? 'num' : ''}">${h.render(row)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }

  function metric(label, value, foot = '', cls = '') {
    return `<div class="metric"><div class="metric-label">${esc(label)}</div><div class="metric-value ${esc(cls)}">${value}</div><div class="metric-foot">${esc(foot)}</div></div>`;
  }

  function sectionHead(name, description = '') {
    return `<div class="section-head"><div><h2>${esc(name)}</h2>${description ? `<p>${esc(description)}</p>` : ''}</div></div>`;
  }

  async function enhanceHistory() {
    if (location.pathname !== '/history') return;
    if (loading || document.getElementById('advanced-history-insights')) return;
    if (view.querySelector('.loading-state')) return;

    loading = true;
    try {
      const [versions, priceHistory, disagreements] = await Promise.all([
        api('/tickets/version-outcomes?limit=100'),
        api('/bookmakers/price-history?limit=50'),
        api('/bookmakers/price-disagreements?limit=30'),
      ]);

      if (location.pathname !== '/history' || document.getElementById('advanced-history-insights')) return;

      const summary = versions.summary || {};
      const pairs = versions.pairs || [];
      const historyRows = priceHistory.rows || [];
      const gapRows = disagreements.rows || [];

      const wrapper = document.createElement('div');
      wrapper.id = 'advanced-history-insights';
      wrapper.innerHTML = `
        <section class="section">
          ${sectionHead('Ticket edits & conversions', 'What happened when we changed a ticket instead of only counting the final version')}
          <div class="hero-grid">
            ${metric('Compared versions', num(summary.total_pairs || 0), 'Parent → child ticket pairs', 'accent')}
            ${metric('Improved result', num(summary.improved_result || 0), 'Parent lost · changed version won', 'positive')}
            ${metric('Worsened result', num(summary.worsened_result || 0), 'Parent won · changed version lost', 'negative')}
            ${metric('Same outcome', num((summary.both_won || 0) + (summary.both_lost || 0)), `${summary.both_won || 0} both won · ${summary.both_lost || 0} both lost`)}
          </div>
        </section>

        <section class="section">
          <div class="panel flush"><div class="panel-head"><h3>Recent ticket-version comparisons</h3><span>${pairs.length} shown</span></div><div class="panel-body">
            ${table([
              {label:'Change', render:r => `<span class="primary-cell">${esc(r.parent_source_type || 'original')} → ${esc(r.child_source_type || 'edited')}</span><span class="sub-cell">${date(r.child_created_at)}</span>`},
              {label:'Result', render:r => resultBadge(r.comparison)},
              {label:'Before', num:true, render:r => odds(r.parent_combined_odds)},
              {label:'After', num:true, render:r => odds(r.child_combined_odds)},
              {label:'Odds change', num:true, render:r => r.combined_odds_change == null ? '—' : num(r.combined_odds_change, 2)},
            ], pairs.slice(0, 40))}
          </div></div>
        </section>

        <section class="section grid-equal">
          <div class="panel flush"><div class="panel-head"><h3>Bookmaker price disagreement</h3><span>Recorded observations</span></div><div class="panel-body">
            ${table([
              {label:'Game / market', render:r => `<span class="primary-cell">${esc(r.event)}</span><span class="sub-cell">${esc(r.market)}</span>`},
              {label:'Books', num:true, render:r => num(r.bookmakers)},
              {label:'Low', num:true, render:r => odds(r.lowest_latest_odds)},
              {label:'High', num:true, render:r => odds(r.highest_latest_odds)},
              {label:'Gap', num:true, render:r => num(r.latest_gap, 2)},
            ], gapRows.slice(0, 20))}
          </div></div>

          <div class="panel flush"><div class="panel-head"><h3>Observed price movement</h3><span>Historical, not live prices</span></div><div class="panel-body">
            ${table([
              {label:'Book / market', render:r => `<span class="primary-cell">${esc(r.bookmaker)}</span><span class="sub-cell">${esc(r.event)} · ${esc(r.market)}</span>`},
              {label:'First', num:true, render:r => odds(r.first_odds)},
              {label:'Latest', num:true, render:r => odds(r.latest_odds)},
              {label:'Change', num:true, render:r => r.change == null ? '—' : num(r.change, 2)},
              {label:'Seen', num:true, render:r => num(r.observations)},
            ], historyRows.slice(0, 20))}
          </div></div>
        </section>`;

      view.appendChild(wrapper);
    } catch (error) {
      console.error('Sabi Boy advanced history could not be loaded', error);
      if (location.pathname === '/history' && !document.getElementById('advanced-history-insights')) {
        const wrapper = document.createElement('section');
        wrapper.id = 'advanced-history-insights';
        wrapper.className = 'section';
        wrapper.innerHTML = `<div class="empty-state"><div><strong>Advanced history is unavailable</strong><p>${esc(error.message || 'The read model could not be loaded.')}</p></div></div>`;
        view.appendChild(wrapper);
      }
    } finally {
      loading = false;
    }
  }

  let scheduled = false;
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(() => {
      scheduled = false;
      enhanceHistory();
    });
  };

  new MutationObserver(schedule).observe(view, {childList: true, subtree: true});
  window.addEventListener('popstate', schedule);
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href="/history"]');
    if (link) window.setTimeout(schedule, 0);
  });
  schedule();
})();
