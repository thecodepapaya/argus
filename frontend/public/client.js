export const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);
export const plainText = (value) => String(value ?? '').replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
export const safeHttpUrl = (value) => /^https?:\/\//i.test(String(value)) ? String(value) : '#';

export function tooltipTerm(label, key, methodology, focusable = true) {
  const definition = methodology?.glossary?.[key]?.definition;
  if (!definition) return escapeHtml(label);
  const accessibility = focusable ? ' tabindex="0"' : '';
  return `<span class="term"${accessibility} aria-label="${escapeHtml(`${label}: ${definition}`)}"><span>${escapeHtml(label)}</span><i aria-hidden="true">?</i><span class="tooltip" role="tooltip">${escapeHtml(definition)}</span></span>`;
}

const sleep = (milliseconds) => new Promise(resolve => setTimeout(resolve, milliseconds));

export async function requestJson(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const attempts = method === 'GET' ? 3 : 1;
  const { timeoutMs = 8000, ...fetchOptions } = options;
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(path, { ...fetchOptions, signal: controller.signal });
      const payload = await response.json().catch(() => ({}));
      if (response.ok) return payload;
      const error = new Error(payload.error || `ARGUS API returned ${response.status}`);
      error.code = payload.code;
      error.requestId = payload.request_id || response.headers.get('X-Request-ID');
      error.retryable = response.status >= 500;
      if (!error.retryable || attempt === attempts) throw error;
      lastError = error;
    } catch (error) {
      lastError = error.name === 'AbortError' ? new Error('ARGUS took too long to respond') : error;
      if (error.retryable === false) throw error;
      if (attempt === attempts) break;
    } finally {
      clearTimeout(timeout);
    }
    await sleep(200 * attempt);
  }
  throw lastError || new Error('ARGUS is unavailable');
}
