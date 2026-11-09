(() => {
  const STORAGE_KEY = 'aive-ui-skin';
  const items = [
    { value: 'system', color: '#718096', title: '跟随系统', detail: '原生布局 · 自动明暗', mode: 'adaptive' },
    { value: 'light', color: '#3f65d8', title: '冰川银', detail: '专业工作台 · 宽松卡片', mode: 'professional' },
    { value: 'dark', color: '#b9c4dc', title: '深空黑', detail: '影院沉浸 · 图标侧栏', mode: 'cinema' },
    { value: 'cyber-blue', color: '#42d9ff', title: '星舰蓝', detail: '指挥舱 · 高密度网格', mode: 'cockpit' },
    { value: 'cyber-teal', color: '#3ef0c2', title: '量子青', detail: '剪辑台 · 紧凑工具栏', mode: 'editor' },
    { value: 'cyber-violet', color: '#b77bff', title: '极光紫', detail: '创作空间 · 宽幅画布', mode: 'studio' },
  ];
  const values = new Set(items.map(item => item.value));
  const DEFAULT_SKIN = 'cyber-blue';
  const media = matchMedia('(prefers-color-scheme: dark)');
  let current = DEFAULT_SKIN;

  function normalize(value) {
    return values.has(value) ? value : DEFAULT_SKIN;
  }

  function apply(value, persist = false) {
    current = normalize(value);
    const root = document.documentElement;
    root.dataset.theme = current === 'system' ? (media.matches ? 'dark' : 'light') : current;
    root.dataset.uiSkin = current;
    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, current);
      } catch {}
    }
    document.querySelectorAll('.ui-skin-option').forEach(button => {
      const active = button.dataset.skin === current;
      button.classList.toggle('active', active);
      button.setAttribute('aria-checked', String(active));
    });
    const label = document.querySelector('.ui-skin-trigger-label');
    const nextLabel = items.find(item => item.value === current)?.title || '界面模式';
    if (label && label.textContent !== nextLabel) label.textContent = nextLabel;
    window.dispatchEvent(new CustomEvent('aive-ui-skin-changed', { detail: { skin: current } }));
  }

  function addNavigationTitles() {
    document.querySelectorAll('.app-sidebar nav a').forEach(link => {
      const text = link.querySelector('span')?.textContent?.trim();
      if (text && !link.title) link.title = text;
    });
  }

  function buildSwitcher() {
    const host = document.createElement('div');
    host.className = 'ui-skin-host';
    host.innerHTML = `
      <button class="ui-skin-trigger" type="button" aria-label="切换整个应用的界面模式" aria-expanded="false">
        <span class="ui-skin-trigger-mark" aria-hidden="true"></span>
        <span class="ui-skin-trigger-label">界面模式</span>
        <span class="ui-skin-trigger-arrow" aria-hidden="true">⌄</span>
      </button>
      <div class="ui-skin-menu" role="menu" aria-label="界面模式" hidden>
        <header>
          <strong>整套界面</strong>
          <span>布局、密度、侧栏、卡片和工具区会一起切换</span>
        </header>
        <div class="ui-skin-grid">
          ${items.map(item => `
            <button class="ui-skin-option" type="button" role="menuitemradio" data-skin="${item.value}" aria-checked="false">
              <span class="ui-skin-preview preview-${item.mode}" style="--preview-color:${item.color}" aria-hidden="true">
                <i></i><i></i><i></i><i></i>
              </span>
              <span class="ui-skin-copy"><strong>${item.title}</strong><small>${item.detail}</small></span>
              <span class="ui-skin-check" aria-hidden="true">✓</span>
            </button>`).join('')}
        </div>
      </div>`;
    const trigger = host.querySelector('.ui-skin-trigger');
    const menu = host.querySelector('.ui-skin-menu');
    const setOpen = open => {
      menu.hidden = !open;
      trigger.setAttribute('aria-expanded', String(open));
      host.classList.toggle('open', open);
    };
    trigger.addEventListener('click', event => {
      event.stopPropagation();
      setOpen(menu.hidden);
    });
    menu.addEventListener('click', event => event.stopPropagation());
    host.querySelectorAll('.ui-skin-option').forEach(option => {
      option.addEventListener('click', () => {
        apply(option.dataset.skin, true);
        setOpen(false);
      });
    });
    document.addEventListener('pointerdown', event => {
      if (!host.contains(event.target)) setOpen(false);
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        setOpen(false);
        trigger.focus();
      }
    });
    return host;
  }

  function mountSwitcher() {
    const headerRight = document.querySelector('.app-header .header-right');
    if (!headerRight) return;
    let host = headerRight.querySelector('.ui-skin-host');
    if (!host) {
      host = buildSwitcher();
      headerRight.insertBefore(host, headerRight.firstChild);
    }
    addNavigationTitles();
    apply(current);
  }

  try {
    current = normalize(localStorage.getItem(STORAGE_KEY) || DEFAULT_SKIN);
  } catch {}
  apply(current);
  media.addEventListener?.('change', () => current === 'system' && apply('system'));
  window.addEventListener('aive-ui-skin-changed', event => {
    const next = normalize(event.detail?.skin);
    if (next !== current) {
      current = next;
      apply(next);
    }
  });
  const observer = new MutationObserver(mountSwitcher);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mountSwitcher, { once: true });
  else mountSwitcher();
})();
