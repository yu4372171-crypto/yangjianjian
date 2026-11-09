(() => {
  const packedVersion = document.documentElement.dataset.runtimeVersion || '2026.10.27.1';
  let release = null;
  const releaseReady = fetch('./app-release.json', { cache: 'no-store' })
    .then(response => {
      if (!response.ok) throw new Error(`release metadata ${response.status}`);
      return response.json();
    })
    .then(data => {
      if (!data || data.product !== 'yangjianjian' || !data.version) {
        throw new Error('invalid release metadata');
      }
      release = data;
      document.documentElement.dataset.releaseVersion = release.version;
      return release;
    })
    .catch(() => null);

  function currentVersion() {
    return release?.version || document.documentElement.dataset.releaseVersion || packedVersion;
  }

  function sync() {
    const version = currentVersion();
    if (!version) return;
    document.querySelectorAll('.version-label').forEach(node => {
      if (node.textContent.trim() !== version) node.textContent = version;
    });
    document.querySelectorAll('.about-info').forEach(container => {
      container.querySelectorAll('p').forEach(node => {
        if (!node.textContent.includes('版本 ')) return;
        const next = node.textContent.replace(/版本\s+[0-9]+(?:\.[0-9]+){2,3}/, `版本 ${version}`);
        if (node.textContent !== next) node.textContent = next;
      });
    });
  }

  function patchAppVersion() {
    const version = currentVersion();
    const app = document.querySelector('#app')?.__vue_app__;
    const pinia = app?._context?.config?.globalProperties?.$pinia;
    const store = pinia?._s?.get('app');
    if (!version || !store || !('version' in store)) return;
    try {
      const current = store.version;
      if (current && typeof current === 'object' && 'value' in current) {
        if (current.value !== version) current.value = version;
      } else if (current !== version) {
        if (typeof store.$patch === 'function') store.$patch({ version });
        else store.version = version;
      }
    } catch {}
  }

  function apply() {
    if (!currentVersion()) return;
    patchAppVersion();
    sync();
  }

  // Only synchronize version surfaces here. The updater owns announcements and
  // online release notes. Rewriting its nodes from a document-wide observer
  // queues another mutation forever, starving timers and pointer events.
  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      apply();
    });
  }
  const observer = new MutationObserver(schedule);
  observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  schedule();
  releaseReady.then(schedule);
  window.addEventListener('hashchange', schedule);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', schedule, { once: true });
  }
})();
