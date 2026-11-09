(() => {
  const PRODUCT_NAME = '羊剪剪';
  const LEGACY_NAMES = new Set([
    'AI自动剪辑-洋芋科技',
    'AI自动剪辑',
    'AI全自动剪辑_云湃科技',
  ]);
  let observer = null;
  let debounce = null;
  let originalTitle = '';
  let currentRelease = null;

  const releaseReady = fetch('./app-release.json', { cache: 'no-store' })
    .then(response => {
      if (!response.ok) throw new Error(`release metadata ${response.status}`);
      return response.json();
    })
    .then(release => {
      if (!release || release.product !== 'yangjianjian' || !release.version || !release.title) {
        throw new Error('release metadata is invalid');
      }
      currentRelease = release;
      scrubStaleAnnouncement();
      return release;
    })
    .catch(() => null);

  function setBrandText(node) {
    const text = node.textContent?.trim();
    if (LEGACY_NAMES.has(text) && text !== PRODUCT_NAME) node.textContent = PRODUCT_NAME;
  }

  function applyDocumentBrand() {
    if (document.title !== PRODUCT_NAME) document.title = PRODUCT_NAME;
    const description = document.querySelector('meta[name="description"]');
    if (description) description.content = `${PRODUCT_NAME} - 洋芋科技智能视频剪辑工作台`;
  }

  function buildDecorLayer() {
    const hero = document.createElement('div');
    hero.className = 'yang-login-hero';
    hero.setAttribute('aria-hidden', 'true');
    hero.innerHTML = `
      <div class="yang-login-glow"></div>
      <div class="yang-login-orbit"><i></i></div>
      <div class="yang-login-grid"></div>
      <div class="yang-login-horizon"></div>
      <div class="yang-login-particles"></div>
      <div class="yang-login-scanline"></div>
      <div class="yang-login-hud"><i></i></div>
      <div class="yang-login-coordinate">YJ-SYS / AUTHORIZED ACCESS / SHIP-BLUE</div>`;
    return hero;
  }

  function buildIdentity() {
    const identity = document.createElement('aside');
    identity.className = 'yang-login-identity';
    identity.setAttribute('aria-label', `${PRODUCT_NAME}品牌信息`);
    identity.innerHTML = `
      <div class="yang-login-emblem">
        <img src="./assets/app-icon.png" alt="">
      </div>
      <div class="yang-login-brand">
        <h1>${PRODUCT_NAME}</h1>
        <p>洋芋科技出品</p>
      </div>
      <p class="yang-login-subtitle">全息智能剪辑舰桥<br>安全连接你的创作空间</p>
      <div class="yang-login-metrics" aria-hidden="true">
        <span>AI EDIT CORE</span>
        <span>MULTI-TRACK</span>
        <span>LOCAL READY</span>
      </div>`;
    return identity;
  }

  function enhancePanel(panel, main) {
    if (panel.dataset.yangExperience === '1') return;
    panel.dataset.yangExperience = '1';
    panel.classList.add('yang-login-card');
    panel.classList.toggle('is-signed-in', Boolean(panel.querySelector('h2')?.textContent?.includes('账号状态')));
    if (!main.querySelector('.yang-login-hero')) main.prepend(buildDecorLayer());
    const access = document.createElement('section');
    access.className = 'yang-login-access';
    access.setAttribute('aria-label', `${PRODUCT_NAME}账号密码登录`);
    const heading = panel.querySelector('h2');
    // Keep decorative CSS text out of the login heading's accessible name.
    if (heading) heading.setAttribute('aria-label', heading.textContent.trim());
    while (panel.firstChild) access.appendChild(panel.firstChild);
    panel.append(access);
    panel.prepend(buildIdentity());
  }

  function scrubLegacyBrand() {
    document.querySelectorAll('.app-header .title-drag strong').forEach(setBrandText);
    document.querySelectorAll('[aria-label], [title], [alt]').forEach(node => {
      for (const attribute of ['aria-label', 'title', 'alt']) {
        const value = node.getAttribute?.(attribute);
        if (!value) continue;
        let next = value;
        for (const legacy of LEGACY_NAMES) next = next.replaceAll(legacy, PRODUCT_NAME);
        if (next !== value) node.setAttribute(attribute, next);
      }
    });
  }

  function scrubStaleAnnouncement() {
    document.querySelectorAll('.announcement-track').forEach(track => {
      if (track.textContent?.includes('0.6.1')) {
        const ticker = track.closest('.announcement-ticker');
        if (ticker && currentRelease) {
          track.textContent = `${currentRelease.version} · ${currentRelease.title} · ${currentRelease.summary}`;
          ticker.hidden = false;
          ticker.dataset.releaseVersion = currentRelease.version;
          ticker.removeAttribute('role');
          ticker.removeAttribute('tabindex');
          ticker.removeAttribute('title');
          ticker.style.cursor = 'default';
        } else if (ticker) {
          ticker.hidden = true;
        }
      }
    });
  }

  function sync() {
    const shell = document.querySelector('.app-shell');
    const main = shell?.querySelector('main.page-container');
    if (!main) {
      document.documentElement.classList.remove('yang-locked');
      document.documentElement.removeAttribute('data-page-state');
      return;
    }
    const panel = main.querySelector('.license-panel');
    const locked = Boolean(panel && !shell.querySelector('.app-sidebar'));
    document.documentElement.classList.toggle('yang-locked', locked);
    document.documentElement.dataset.pageState = locked ? 'locked' : 'unlocked';
    applyDocumentBrand();
    scrubLegacyBrand();
    scrubStaleAnnouncement();
    if (!locked) {
      main.querySelectorAll('.yang-login-hero').forEach(hero => hero.remove());
      return;
    }
    enhancePanel(panel, main);
  }

  function scheduleSync() {
    if (debounce) clearTimeout(debounce);
    debounce = setTimeout(sync, 20);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', sync, { once: true });
  } else {
    sync();
  }
  observer = new MutationObserver(scheduleSync);
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ['class', 'aria-label', 'title'],
  });
  window.addEventListener('pageshow', sync);
})();
