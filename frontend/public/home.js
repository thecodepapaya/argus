import { escapeHtml as h, requestJson, tooltipTerm } from '/client.js?v=a4fd3680';

const $ = (selector) => document.querySelector(selector);
const date = (value) => value ? new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—';
const delta = (value) => `${value > 0 ? '+' : ''}${Math.round(value)}`;
const movement = (change, label) => {
  const direction = change.phase_direction;
  const icon = direction === 'advanced' ? '↑' : direction === 'moved back' ? '↓' : '→';
  const tone = direction === 'advanced' ? 'positive' : direction === 'moved back' ? 'negative' : 'steady';
  return `<span class="movement-badge ${tone}"><small>${label}</small><b>${icon} ${h(direction)}</b></span>`;
};

function portfolioSummary(items, methodology) {
  const latestWeek = items.map(item => item.current.week).sort().at(-1) || '—';
  const largestMover = items.reduce((largest, item) => {
    const adoptionChange = item.change.month.adoption;
    return !largest || Math.abs(adoptionChange) > Math.abs(largest.change.month.adoption) ? item : largest;
  }, null);
  const averageCoverage = items.length
    ? Math.round(items.reduce((total, item) => total + item.current.features.coverage, 0) / items.length)
    : 0;
  const weekLabel = latestWeek === '—'
    ? latestWeek
    : new Date(`${latestWeek}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  const moverName = largestMover?.technology.display_name || 'No estimate yet';
  const moverChange = largestMover ? `${delta(largestMover.change.month.adoption)} pts` : '—';

  return `<div><b>Week of ${h(weekLabel)}</b><span>latest estimate window</span></div><div><b>${h(moverName)} <i>${h(moverChange)}</i></b><span>largest monthly ${tooltipTerm('adoption', 'adoption', methodology)}</span></div><div><b>${averageCoverage}%</b><span>average ${tooltipTerm('evidence coverage', 'coverage', methodology)}</span></div>`;
}

function card({ technology, current, change, source_errors: sourceErrors }, methodology) {
  const path = `/technologies/${h(technology.id)}`;
  const detailsLabel = `View ${technology.display_name} analysis`;
  return `<a class="tech-card portfolio-card panel" href="${path}" aria-label="${h(detailsLabel)}"><div class="card-top"><span class="eyebrow">${h(technology.kind.replace('_', ' '))}</span><span class="signal ${h(current.confidence_band)}">${h(current.confidence_band)} ${tooltipTerm('confidence', 'confidence', methodology, false)}</span></div><h3>${h(technology.display_name)}<span aria-hidden="true">↗</span></h3><p class="tech-description">${h(technology.definition)}</p><div class="phase-line"><small>Current phase</small><b>${tooltipTerm(current.phase_label, 'phase', methodology, false)}</b></div><div class="tech-metrics"><span>${tooltipTerm('Adoption', 'adoption', methodology, false)} <b>${Math.round(current.features.adoption)}</b></span><span>${tooltipTerm('Maturity', 'maturity', methodology, false)} <b>${Math.round(current.features.maturity)}</b></span><span>${tooltipTerm('Hype gap', 'hype_gap', methodology, false)} <b>${current.hype_gap > 0 ? '+' : ''}${current.hype_gap}</b></span></div><div class="direction-list" aria-label="Recent movement">${movement(change.week, '7 days')} ${movement(change.month, '30 days')}</div>${sourceErrors.length ? `<small class="warning">${sourceErrors.length} source warning${sourceErrors.length > 1 ? 's' : ''}</small>` : ''}</a>`;
}

function renderTechnologyCards(items, methodology, query = '') {
  const normalizedQuery = query.trim().toLowerCase();
  const visibleItems = normalizedQuery
    ? items.filter(({ technology }) => [technology.display_name, technology.kind, technology.definition].join(' ').toLowerCase().includes(normalizedQuery))
    : items;
  $('#technology-cards').innerHTML = visibleItems.map(item => card(item, methodology)).join('');
  $('#technology-search-result').textContent = normalizedQuery
    ? `${visibleItems.length} of ${items.length} ${visibleItems.length === 1 ? 'technology' : 'technologies'} shown`
    : `${items.length} technologies tracked`;
  if (!visibleItems.length) {
    $('#technology-cards').innerHTML = '<p class="search-empty">No tracked technology matches that search.</p>';
  }
}

function renderFailure(error) {
  $('#health').innerHTML = `<div class="load-error"><b>ARGUS is temporarily unavailable</b><span>${h(error.message)}</span><button id="retry-home" type="button">Retry</button></div>`;
  $('#retry-home').addEventListener('click', boot, { once: true });
}

function setupSuggestionForm() {
  const toggle = $('#suggest-technology-toggle');
  const form = $('#technology-suggestion-form');
  const result = $('#technology-suggestion-result');
  const close = $('#suggest-technology-close');
  toggle.addEventListener('click', () => {
    const opening = form.classList.contains('hidden');
    form.classList.toggle('hidden', !opening);
    toggle.setAttribute('aria-expanded', String(opening));
    if (opening) form.elements.name.focus();
  });
  close.addEventListener('click', () => {
    form.classList.add('hidden');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.focus();
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submit = form.querySelector('button[type="submit"]');
    const data = new FormData(form);
    submit.disabled = true;
    result.className = 'pending';
    result.textContent = 'Sending…';
    try {
      const response = await requestJson('/api/v1/suggestions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: data.get('name'), rationale: data.get('rationale'), website: data.get('website') }),
      });
      result.className = 'success';
      result.textContent = response.already_suggested
        ? 'That technology is already in the review queue. Thanks for reinforcing it.'
        : 'Thanks—your suggestion is now in the ARGUS review queue.';
      form.reset();
    } catch (error) {
      result.className = 'error';
      result.textContent = error.message || 'ARGUS could not save the suggestion.';
    } finally {
      submit.disabled = false;
    }
  });
}

async function boot() {
  $('#health').innerHTML = '<span>Loading portfolio summary…</span>';
  try {
    const [overview, methodology] = await Promise.all([requestJson('/api/v1/overview'), requestJson('/api/v1/methodology')]);
    $('#health').innerHTML = portfolioSummary(overview.items, methodology);
    $('#last-updated').textContent = `Updated ${date(overview.last_updated)}`;
    renderTechnologyCards(overview.items, methodology);
    $('#technology-search').addEventListener('input', (event) => renderTechnologyCards(overview.items, methodology, event.target.value));
  } catch (error) {
    renderFailure(error);
    return;
  }

  try {
    const activity = await requestJson('/api/v1/activity');
    $('#activity-list').innerHTML = activity.items.map(run => `<div><span class="run-state ${h(run.status)}">${h(run.status)}</span><b>${h(run.technology_id || 'system')}</b><span>week of ${h(run.week)}</span><span>${h(run.stage)}</span></div>`).join('') || '<p>No runs yet.</p>';
  } catch (error) {
    $('#activity-list').innerHTML = `<p class="subtle">Recent activity is temporarily unavailable. The technology estimates above are still current.</p>`;
  }
}

setupSuggestionForm();
boot();
