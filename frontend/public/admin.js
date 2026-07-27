(async () => {
  const { escapeHtml, plainText, requestJson, safeHttpUrl } = await import('/client.js?v=0.8');
  const $ = (selector) => document.querySelector(selector);
  const esc = (value) => escapeHtml(plainText(value));
  const state = { token: '', evidence: [], evidenceVisible: 12, technologyNames: new Map() };

  const friendlyDate = (value) => {
    if (!value) return '—';
    return new Date(`${value}T00:00:00Z`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  };
  const technologyName = (id) => state.technologyNames.get(id) || String(id || 'System').replaceAll('-', ' ');

  function message(text = '', type = 'info') {
    let element = $('#admin-message');
    if (!element) {
      element = document.createElement('div');
      element.id = 'admin-message';
      element.setAttribute('role', 'status');
      $('.admin').prepend(element);
    }
    element.className = `admin-message ${text ? type : 'hidden'}`;
    element.textContent = text;
  }

  async function api(path, options = {}) {
    return requestJson(`/api/v1/admin/${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', 'X-Argus-Token': state.token, ...options.headers },
    });
  }

  function renderOverview(data) {
    state.technologyNames = new Map(data.items.map(item => [item.technology.id, item.technology.display_name]));
    const weekly = data.items.filter(item => item.technology.analysis_cadence === 'weekly').length;
    const failedSources = data.sources.filter(source => source.last_error).length;
    const healthySources = data.sources.length - failedSources;
    $('#admin-health').innerHTML = `
      <article class="summary-card panel"><span class="summary-kicker">Analysis cadence</span><b>${weekly} weekly</b><p>${data.items.length - weekly} technologies currently use quarterly monitoring.</p></article>
      <article class="summary-card panel"><span class="summary-kicker">Review queue</span><b>${data.open_reviews} pending</b><p>Evidence records still need an operator decision.</p></article>
      <article class="summary-card panel ${failedSources ? 'warning-card' : ''}"><span class="summary-kicker">Source health</span><b>${healthySources}/${data.sources.length} healthy</b><p>${failedSources ? `${failedSources} source warning${failedSources > 1 ? 's need' : ' needs'} attention.` : 'All configured sources collected successfully.'}</p></article>`;

    $('#run-rows').innerHTML = data.runs.map(run => {
      const warningCount = run.errors?.length || 0;
      return `<tr><td><span class="status-pill ${warningCount ? 'warning' : ''}">${esc(run.status)}</span></td><td>${esc(technologyName(run.technology_id))}</td><td>${esc(friendlyDate(run.week))}</td><td>${esc(run.stage)}</td><td>${esc(run.details.documents ?? '—')}</td><td>${warningCount ? `<span class="warning">${warningCount} warning${warningCount > 1 ? 's' : ''}</span>` : '<span class="subtle">None</span>'}</td></tr>`;
    }).join('') || '<tr><td colspan="6" class="subtle">No analysis runs have been recorded.</td></tr>';

    $('#source-rows').innerHTML = data.sources.map(source => {
      const hasError = Boolean(source.last_error);
      return `<tr><td>${esc(technologyName(source.technology_id))}</td><td>${esc(source.name)}</td><td>${esc(source.source_class.replaceAll('_', ' '))}</td><td><span class="status-pill ${hasError ? 'warning' : ''}">${hasError ? 'warning' : 'healthy'}</span></td><td class="${hasError ? 'warning' : 'subtle'}">${esc(source.last_error || 'No current warning')}</td></tr>`;
    }).join('');
  }

  function evidenceCard(item) {
    return `<article class="review-card panel"><div class="review-meta"><span class="tag" title="${esc(technologyName(item.technology_id))}">${esc(technologyName(item.technology_id))} · ${esc(item.dimension)}</span><span>${esc(friendlyDate(item.date))}</span></div><h3>${esc(item.title)}</h3><p>${esc(item.excerpt)}</p><footer><a href="${escapeHtml(safeHttpUrl(item.url))}" target="_blank" rel="noreferrer">Open source ↗</a><label class="review-select">Decision<select data-evidence="${esc(item.id)}"><option value="unreviewed" ${item.review_status === 'unreviewed' ? 'selected' : ''}>Awaiting review</option><option value="approved" ${item.review_status === 'approved' ? 'selected' : ''}>Approve</option><option value="excluded" ${item.review_status === 'excluded' ? 'selected' : ''}>Exclude</option></select></label></footer></article>`;
  }

  function renderEvidence() {
    const visible = state.evidence.slice(0, state.evidenceVisible);
    $('#admin-evidence').innerHTML = visible.map(evidenceCard).join('') || '<div class="empty-state panel"><b>Queue clear</b><p>No evidence matches the selected technology and decision filters.</p></div>';
    $('#evidence-queue-count').textContent = state.evidence.length
      ? `Showing ${visible.length} of ${state.evidence.length} records`
      : 'No matching records';
    $('#evidence-more').classList.toggle('hidden', state.evidenceVisible >= state.evidence.length);

    document.querySelectorAll('[data-evidence]').forEach(select => select.addEventListener('change', async () => {
      select.disabled = true;
      try {
        await api(`evidence/${encodeURIComponent(select.dataset.evidence)}/review`, { method: 'POST', body: JSON.stringify({ status: select.value, note: 'Updated in admin console' }) });
        message('Evidence decision saved.', 'success');
        await loadEvidence();
      } catch (error) {
        message(`Decision was not saved: ${error.message}`, 'error');
        select.disabled = false;
      }
    }));
  }

  async function loadEvidence() {
    const reviewState = $('#evidence-filter').value;
    const technologyId = $('#evidence-tech-filter').value;
    const query = new URLSearchParams();
    if (reviewState) query.set('review_status', reviewState);
    if (technologyId) query.set('technology_id', technologyId);
    const data = await api(`evidence${query.size ? `?${query}` : ''}`);
    state.evidence = data.items;
    state.evidenceVisible = 12;
    renderEvidence();
  }

  function technologyActions(technology) {
    const actions = [`<button class="card-action" data-tech="${esc(technology.id)}" data-action="backfill">Collect now</button>`];
    if (technology.status === 'active') {
      const nextCadence = technology.analysis_cadence === 'weekly' ? 'quarterly' : 'weekly';
      actions.push(`<button class="card-action quiet" data-tech="${esc(technology.id)}" data-action="cadence" data-cadence="${nextCadence}">Switch to ${nextCadence}</button>`);
    }
    if (technology.status === 'draft') actions.push(`<button class="card-action" data-tech="${esc(technology.id)}" data-action="validate">Validate profile</button>`);
    if (technology.status === 'validated') actions.push(`<button class="card-action" data-tech="${esc(technology.id)}" data-action="activate">Publish technology</button>`);
    return actions.join('');
  }

  async function loadTechnologies() {
    const data = await api('technologies');
    const selectedTechnology = $('#evidence-tech-filter').value;
    $('#evidence-tech-filter').innerHTML = `<option value="">All technologies</option>${data.items.map(technology => `<option value="${esc(technology.id)}" ${selectedTechnology === technology.id ? 'selected' : ''}>${esc(technology.display_name)}</option>`).join('')}`;
    data.items.forEach(technology => state.technologyNames.set(technology.id, technology.display_name));

    $('#technology-admin-list').innerHTML = data.items.map(technology => `<article class="technology-admin-card panel"><div class="technology-card-meta"><span class="tech-badge ${esc(technology.status)}">${esc(technology.status)}</span><span class="tech-badge">${esc(technology.analysis_cadence)}</span></div><h3>${esc(technology.display_name)}</h3><p>${esc(technology.definition)}</p><div class="technology-card-facts"><span>Repositories<b>${(technology.github_repos || []).length}</b></span><span>Profile type<b>${esc(technology.kind)}</b></span></div><div class="card-actions">${technologyActions(technology)}</div></article>`).join('');

    document.querySelectorAll('[data-tech]').forEach(button => button.addEventListener('click', async () => {
      button.disabled = true;
      const actionLabels = { backfill: 'Collection', cadence: 'Cadence update', validate: 'Validation', activate: 'Publication' };
      try {
        const body = button.dataset.action === 'cadence' ? JSON.stringify({ cadence: button.dataset.cadence }) : undefined;
        await api(`technologies/${encodeURIComponent(button.dataset.tech)}/${button.dataset.action}`, { method: 'POST', body });
        message(`${actionLabels[button.dataset.action] || 'Operation'} completed.`, 'success');
        await reload();
      } catch (error) {
        message(`${actionLabels[button.dataset.action] || 'Operation'} failed: ${error.message}`, 'error');
      } finally {
        button.disabled = false;
      }
    }));
  }

  async function loadDiscovery() {
    const data = await api('discovery');
    const latest = data.runs[0];
    $('#discovery-status').textContent = data.configured
      ? (latest ? `Latest run: ${latest.status} · ${latest.candidate_count} candidates` : 'Gemini is configured; the first weekly run is pending.')
      : 'Weekly discovery is currently paused.';
    const suggestions = data.items.filter(item => item.status === 'new');
    $('#discovery-list').innerHTML = suggestions.map(item => {
      const links = item.evidence_urls.map((url, index) => `<a href="${escapeHtml(safeHttpUrl(url))}" target="_blank" rel="noreferrer">Source ${index + 1} ↗</a>`).join('');
      return `<article class="suggestion-card panel"><div class="review-meta"><span class="tag">${esc(item.kind)}</span><span>${esc(item.emergence_score)}/100</span></div><h3>${esc(item.display_name)}</h3><p>${esc(item.definition)}</p><p>${esc(item.rationale)}</p><div class="suggestion-links">${links}</div><div class="card-actions"><button class="card-action" data-suggestion="${esc(item.id)}" data-decision="accept">Create draft</button><button class="card-action quiet" data-suggestion="${esc(item.id)}" data-decision="dismiss">Dismiss</button></div></article>`;
    }).join('') || `<div class="empty-state panel"><b>${data.configured ? 'No candidates awaiting review' : 'Discovery needs a Gemini key'}</b><p>${data.configured ? 'The discovery queue is clear. The scheduler will check again on its next weekly run.' : 'Set GEMINI_API_KEY for the discovery service to search for emerging technologies. Suggestions always require operator review before they can become public.'}</p></div>`;

    document.querySelectorAll('[data-suggestion]').forEach(button => button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        await api(`suggestions/${encodeURIComponent(button.dataset.suggestion)}/${button.dataset.decision}`, { method: 'POST' });
        message(button.dataset.decision === 'accept' ? 'Suggestion converted to a draft technology.' : 'Suggestion dismissed.', 'success');
        await Promise.all([loadDiscovery(), loadTechnologies()]);
      } catch (error) {
        message(`Suggestion was not updated: ${error.message}`, 'error');
        button.disabled = false;
      }
    }));
  }

  async function reload() {
    const overview = await api('overview');
    renderOverview(overview);
    const results = await Promise.allSettled([loadEvidence(), loadTechnologies(), loadDiscovery()]);
    const failure = results.find(result => result.status === 'rejected');
    if (failure) message(`Some console data could not be loaded: ${failure.reason.message}`, 'error');
  }

  async function login() {
    state.token = $('#token').value;
    $('#login-button').disabled = true;
    try {
      await reload();
      $('#login').classList.add('hidden');
      $('#console').classList.remove('hidden');
      $('#login-error').textContent = '';
    } catch (error) {
      $('#login-error').textContent = error.message;
    } finally {
      $('#login-button').disabled = false;
    }
  }

  $('#login-button').addEventListener('click', login);
  $('#token').addEventListener('keydown', event => { if (event.key === 'Enter') login(); });
  $('#evidence-filter').addEventListener('change', () => loadEvidence().catch(error => message(error.message, 'error')));
  $('#evidence-tech-filter').addEventListener('change', () => loadEvidence().catch(error => message(error.message, 'error')));
  $('#evidence-more').addEventListener('click', () => { state.evidenceVisible += 12; renderEvidence(); });
  $('#refresh-all').addEventListener('click', async () => {
    const button = $('#refresh-all');
    button.disabled = true;
    button.textContent = 'Analysis running…';
    message('Running all technologies currently due for analysis.');
    try {
      await api('refresh', { method: 'POST', body: '{}' });
      await reload();
      message('Scheduled analysis completed.', 'success');
    } catch (error) {
      message(`Analysis failed: ${error.message}`, 'error');
    } finally {
      button.disabled = false;
      button.innerHTML = '<span aria-hidden="true">↻</span> Run scheduled analysis';
    }
  });
  $('#technology-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = new FormData(event.target);
    const profile = Object.fromEntries(form.entries());
    profile.github_repos = profile.github_repos.split(',').map(value => value.trim()).filter(Boolean);
    profile.relevance_terms = profile.relevance_terms.split(',').map(value => value.trim()).filter(Boolean);
    try {
      const technology = await api('technologies', { method: 'POST', body: JSON.stringify(profile) });
      $('#technology-result').textContent = `Draft “${technology.display_name}” created.`;
      event.target.reset();
      await loadTechnologies();
    } catch (error) {
      $('#technology-result').textContent = error.message;
    }
  });
})().catch(error => {
  const target = document.querySelector('#login-error');
  if (target) target.textContent = `Console failed to initialize: ${error.message}`;
});
