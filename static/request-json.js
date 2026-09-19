"use strict";
(function(root) {
  // Bound headers AND body, even when a browser operation ignores abort.
  // This helper never retries a request, especially a shutter/print POST.
  async function requestJson(url, options = {}, timeoutMs = 5000) {
    const controller = new AbortController();
    let timer;
    try {
      return await Promise.race([
        (async () => {
          const response = await fetch(url, {...options, signal: controller.signal});
          const data = await response.json();
          if (!response.ok) throw new Error(data?.error || `Request failed (${response.status})`);
          return data;
        })(),
        new Promise((_, reject) => {
          timer = setTimeout(() => {
            controller.abort();
            reject(new Error('Request timed out. Check status before repeating an action.'));
          }, timeoutMs);
        })
      ]);
    } finally { clearTimeout(timer); controller.abort(); }
  }
  if (typeof module !== 'undefined') module.exports = requestJson;
  else root.StripshotRequestJson = requestJson;
})(typeof window !== 'undefined' ? window : globalThis);
