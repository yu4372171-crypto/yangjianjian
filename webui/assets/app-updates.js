(() => {
  const rpcPromise = import('./index-CVDv6sjN.js');
  let rpc = null;
  let useApp = null;
  let status = null;
  let busy = false;
  let timer = null;
  let lastAutomatic = 0;
  let automaticInFlight = false;
  let mounted = false;
  let localRelease = null;
  let localReleasePromise = null;
  let mountedVersion = '';
  let sessionRevision = 0;
  let operationRevision = 0;
  let resetStartup = () => {};

  const AUTO_INTERVAL = 30 * 60 * 1000;
  const STARTUP_POLL_INTERVAL = 500;

  function fmtBytes(value) {
    if (!Number.isFinite(value) || value <= 0) return '';
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = value, index = 0;
    while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1; }
    return `${size >= 10 ? Math.round(size) : size.toFixed(1)} ${units[index]}`;
  }

  function text(key, fallback) {
    return fallback;
  }

  async function automaticCheck() {
    if (!status || !status.configured || status.autoCheck === false) return;
    if (status.onlineConfigured && !status.onlineSignedIn) return;
    if (automaticInFlight || busy) return;
    if (['checking', 'downloading', 'installing'].includes(status.phase)) return;
    const now = Date.now();
    if (now - lastAutomatic < AUTO_INTERVAL) return;
    automaticInFlight = true;
    const session = sessionRevision;
    const operation = ++operationRevision;
    lastAutomatic = now;
    status = {...status, phase: 'checking', error: ''};
    renderHostStatus();
    try {
      const nextStatus = await rpc.invoke('video.checkUpdate', {});
      if (session !== sessionRevision || operation !== operationRevision) return;
      status = nextStatus;
      if (status?.onlineConfigured && !status.onlineSignedIn) return;
      if (status.available) useApp().toast(`发现新版本 ${status.latest.version}`);
      renderHostStatus();
    } catch (error) {
      if (session !== sessionRevision || operation !== operationRevision) return;
      if (status) {
        status = { ...status, phase: 'error', error: error.message || String(error) };
      }
      renderHostStatus();
    } finally {
      if (session === sessionRevision) automaticInFlight = false;
    }
  }

  function renderHostStatus() {
    const host = document.querySelector('.app-update-host');
    host?.syncStatus?.(status);
  }

function buildDialog() {
    const host = document.createElement('div');
    host.className = 'app-update-host';
    host.innerHTML = `
      <button class="app-update-trigger" type="button" aria-label="检查更新" aria-haspopup="dialog">
        <span class="app-update-mark" aria-hidden="true"></span>
        <span class="app-update-label">检查更新</span>
        <span class="app-update-badge" aria-hidden="true" hidden></span>
      </button>
      <section class="app-release-announcement" data-release-announcement aria-live="polite" hidden></section>
      <div class="app-update-backdrop" role="presentation" hidden></div>
      <section class="app-update-dialog" role="dialog" aria-modal="true" aria-label="检查更新" hidden>
        <header class="app-update-head">
          <strong>检查更新</strong>
          <button class="app-update-close" type="button" aria-label="关闭">×</button>
        </header>
        <div class="app-update-versions">
          <div><span>当前版本</span><b data-update-current>—</b></div>
          <div><span>最新版本</span><b data-update-latest>—</b></div>
        </div>
        <div class="app-update-body" data-update-body>
          <p class="app-update-line" data-update-state>正在读取更新状态…</p>
          <div class="app-update-notes" data-update-notes hidden></div>
          <div class="app-update-progress" data-update-progress hidden>
            <progress max="100" value="0"></progress>
            <span>0%</span>
          </div>
        </div>
        <footer class="app-update-actions">
          <button type="button" data-update-action="check">检查更新</button>
          <button type="button" data-update-action="download" hidden>下载更新</button>
          <button type="button" data-update-action="cancel" hidden>取消下载</button>
          <button type="button" data-update-action="install" class="primary" hidden>安装并重启</button>
        </footer>
        <details class="app-update-settings">
          <summary>更新设置</summary>
<label class="app-update-field" data-update-url-field style="display:block">
            <span>发布地址（HTTPS）</span>
            <input type="url" data-update-url placeholder="https://example.com/app/latest.json" spellcheck="false">
          </label>
          <label class="app-update-checkbox">
            <input type="checkbox" data-update-auto> 打开软件后自动检查新版本
          </label>
          <button type="button" data-update-action="save">保存设置</button>
        </details>
      </section>`;
    const trigger = host.querySelector('.app-update-trigger');
    const dialog = host.querySelector('.app-update-dialog');
    const backdrop = host.querySelector('.app-update-backdrop');
    const badge = host.querySelector('.app-update-badge');
    const releaseAnnouncement = host.querySelector('[data-release-announcement]');
    const currentEl = dialog.querySelector('[data-update-current]');
    const latestEl = dialog.querySelector('[data-update-latest]');
    const body = dialog.querySelector('[data-update-body]');
    const stateEl = dialog.querySelector('[data-update-state]');
    const notesEl = dialog.querySelector('[data-update-notes]');
    const progressBox = dialog.querySelector('[data-update-progress]');
    const progressBar = progressBox.querySelector('progress');
    const progressText = progressBox.querySelector('span');
    const urlInput = dialog.querySelector('[data-update-url]');
    const autoInput = dialog.querySelector('[data-update-auto]');

    const action = name => dialog.querySelector(`[data-update-action="${name}"]`);
    let actionError = '';

    function renderReleaseAnnouncement() {
      if (!localRelease) {
        releaseAnnouncement.hidden = true;
        return;
      }
      releaseAnnouncement.hidden = false;
      releaseAnnouncement.dataset.version = localRelease.version;
      releaseAnnouncement.dataset.releaseTitle = localRelease.title;
      releaseAnnouncement.textContent = `${localRelease.version} · ${localRelease.title} · ${localRelease.publishedAt} · ${localRelease.summary}`;
      releaseAnnouncement.title = `${localRelease.title}\n${localRelease.summary}`;
      dialog.dataset.product = localRelease.product;
    }

    function renderReleaseNotes() {
      const onlineNotes = status?.available ? status.latest?.notes : '';
      let headingText = '本版本更新';
      let noteText = '';
      if (onlineNotes) {
        headingText = `发现新版本 ${status.latest.version}`;
        noteText = onlineNotes;
      } else if (localRelease) {
        headingText = `当前版本 ${localRelease.version} · ${localRelease.publishedAt}`;
        noteText = [
          localRelease.title,
          localRelease.summary,
          ...(Array.isArray(localRelease.notes) ? localRelease.notes.map(note => `• ${note}`) : []),
        ].filter(Boolean).join('\n');
      }
      if (!noteText) {
        notesEl.hidden = true;
        notesEl.textContent = '';
        return;
      }
      notesEl.hidden = false;
      const heading = document.createElement('strong');
      heading.textContent = headingText;
      const note = document.createElement('div');
      note.textContent = noteText;
      notesEl.replaceChildren(heading, note);
    }

    function setOpen(open) {
      dialog.hidden = !open;
      backdrop.hidden = !open;
      trigger.setAttribute('aria-expanded', String(open));
      if (open) {
        if (status?.phase === 'error' && status.error) renderError(status.error);
        else refresh();
        if (timer) clearInterval(timer);
        timer = setInterval(refresh, 1500);
      } else if (timer) {
        clearInterval(timer);
        timer = null;
      }
    }

    async function fetchStatus() {
      return rpc.invoke('video.updateStatus', {});
    }

    function renderError(message) {
      actionError = message;
      stateEl.className = 'app-update-line error';
      stateEl.textContent = message;
    }

    function render() {
      if (!status) return;
      const configured = Boolean(status.configured);
      const available = Boolean(status.available);
      const onlineConfigured = Boolean(status.onlineConfigured);
      const phase = status.phase || 'idle';
      const urlField = dialog.querySelector('[data-update-url-field]');
      if (urlField) urlField.hidden = onlineConfigured;
      dialog.dataset.onlineConfigured = String(onlineConfigured);
      currentEl.textContent = status.currentVersion || '—';
      latestEl.textContent = status.latest?.version || (phase === 'up_to_date' ? status.currentVersion : (configured ? '待检查' : '未配置'));
      badge.hidden = !available;
      notesEl.hidden = true;
      notesEl.textContent = '';
      progressBox.hidden = !(phase === 'downloading');
      progressBar.value = Math.max(0, Math.min(100, Number(status.progress) || 0));
      progressText.textContent = `${Math.round(progressBar.value)}%`;
      action('check').disabled = busy || ['checking', 'downloading', 'installing'].includes(phase);
      action('download').hidden = !(phase === 'available' && status.latest);
      action('download').disabled = busy;
      action('download').textContent = status.resumable ? '继续下载更新' : '下载更新';
      action('cancel').hidden = phase !== 'downloading';
      action('install').hidden = !(phase === 'ready' && available);
      action('install').disabled = busy;
    // A customer may edit the update channel while the dialog refreshes from
    // the backend. Preserve unsaved input until the settings panel is closed
    // or a different status revision has actually been applied.
    if (!urlInput.dataset.dirty && urlInput !== document.activeElement) {
      urlInput.value = status.manifestUrl || '';
    }
    if (!autoInput.dataset.dirty && autoInput !== document.activeElement) {
      autoInput.checked = status.autoCheck !== false;
    }
      if (onlineConfigured && !status.onlineSignedIn) {
        stateEl.className = 'app-update-line muted';
        stateEl.textContent = '在线更新会话已断开，请退出后重新登录账号再检查更新。';
      } else if (phase === 'unconfigured') {
        stateEl.className = 'app-update-line muted';
        stateEl.textContent = localRelease
          ? `当前版本为 ${localRelease.version}，本版本公告已同步；发行者尚未配置在线更新源，暂时无法检查后续版本。`
          : '发行者尚未配置在线更新服务，暂时无法检查后续版本。';
      } else if (phase === 'checking') {
        stateEl.className = 'app-update-line';
        stateEl.textContent = '正在检查新版本…';
      } else if (phase === 'downloading') {
        stateEl.className = 'app-update-line';
        stateEl.textContent = `正在下载更新，已完成 ${fmtBytes(Number(status.partialBytes) || 0)}；中断后会保留进度。`;
      } else if (phase === 'ready') {
        stateEl.className = 'app-update-line ready';
        stateEl.textContent = `新版本 ${status.latest.version} 已下载并通过完整性校验。`;
      } else if (phase === 'installing') {
        stateEl.className = 'app-update-line';
        stateEl.textContent = '正在安装，应用即将关闭并自动重启。';
      } else if (phase === 'up_to_date') {
        stateEl.className = 'app-update-line ok';
        stateEl.textContent = '当前已经是最新版本。';
      } else if (phase === 'error') {
        renderError(status.error || '更新检查失败');
      } else if (phase === 'idle' && configured) {
        stateEl.className = 'app-update-line muted';
        stateEl.textContent = '点击“检查更新”查看是否有新版本。';
      } else if (phase === 'available') {
        stateEl.className = 'app-update-line ready';
        stateEl.textContent = status.error || `发现新版本 ${status.latest.version}，可以下载更新。`;
      }
      if (phase === 'available' && status.resumable) {
        stateEl.className = 'app-update-line ready';
        stateEl.textContent = `已保留 ${fmtBytes(Number(status.partialBytes) || 0)} 下载进度，重新打开软件后可继续下载。`;
      }
      renderReleaseNotes();
      if (status.lastInstall?.status) {
        const line = document.createElement('p');
        line.className = 'app-update-line muted';
        const restart = status.lastInstall.restart;
        if (status.lastInstall.status !== 'installed') {
          line.textContent = `上次更新未完成：${status.lastInstall.message || status.lastInstall.status}`;
        } else if (restart?.status === 'failed') {
          line.className = 'app-update-line error';
          line.textContent = `更新 ${status.lastInstall.version} 已安装，但应用未能自动重启：${restart.message || '请手动打开应用'}`;
        } else {
          line.textContent = `上次更新已安装：${status.lastInstall.version}`;
        }
        const previous = body.querySelector('[data-last-install]');
        if (previous) previous.textContent = line.textContent;
        else { line.dataset.lastInstall = '1'; body.append(line); }
      } else {
        body.querySelector('[data-last-install]')?.remove();
      }
      if (actionError) {
        stateEl.className = 'app-update-line error';
        stateEl.textContent = actionError;
      }
    }

    async function refresh() {
      const session = sessionRevision;
      const operation = operationRevision;
      try {
        const nextStatus = await fetchStatus();
        if (session !== sessionRevision || operation !== operationRevision) return false;
        if (status?.phase === 'error' && nextStatus.phase === 'idle') {
          status = { ...nextStatus, phase: 'error', error: status.error };
        } else {
          if (status?.phase !== nextStatus.phase) actionError = '';
          status = nextStatus;
        }
      } catch (error) {
        if (session !== sessionRevision || operation !== operationRevision) return false;
        renderError(error.message || String(error));
        return false;
      }
      render();
      return true;
    }

    async function loadLocalRelease() {
      if (!localReleasePromise) {
        localReleasePromise = fetch('./app-release.json', { cache: 'no-store' })
          .then(response => {
            if (!response.ok) throw new Error(`本版本公告读取失败（${response.status}）`);
            return response.json();
          })
          .then(release => {
            if (!release || release.product !== 'yangjianjian' || !release.version || !release.title) {
              throw new Error('本版本公告格式无效');
            }
            const expectedVersion = status?.currentVersion || mountedVersion || localVersionFromPage();
            if (expectedVersion && release.version !== expectedVersion) {
              throw new Error('本版本公告与安装版本不一致');
            }
            localRelease = release;
            renderReleaseAnnouncement();
            render();
            return release;
          })
          .catch(() => {
            releaseAnnouncement.hidden = true;
            return null;
          });
      }
      return localReleasePromise;
    }

    async function check() {
      if (busy || automaticInFlight) return;
      const session = sessionRevision;
      ++operationRevision;
      actionError = '';
      busy = true;
      if (status) status = {...status, phase: 'checking', error: ''};
      render();
      try {
        const nextStatus = await rpc.invoke('video.checkUpdate', {});
        if (session !== sessionRevision) return;
        status = nextStatus;
        if (status?.phase === 'login_required') useApp()?.toast?.('请重新登录账号后检查在线更新');
        render();
      } catch (error) {
        if (session !== sessionRevision) return;
        if (status) status = {...status, phase: 'error', error: error.message || String(error)};
        renderError(error.message || String(error));
        useApp()?.toast?.(error.message || '更新检查失败');
      } finally {
        if (session === sessionRevision) { busy = false; render(); }
      }
    }

    async function download() {
      actionError = '';
      busy = true;
      render();
      try {
        await useApp().runJob('video.downloadUpdate', {}, false);
      } catch (error) {
        renderError(error.message || String(error));
      }
      busy = false;
      await refresh();
    }

    async function cancelDownload() {
      const tasks = useApp().tasks || [];
      const row = tasks.find(item => item.action === 'video.downloadUpdate' && ['queued', 'running', 'paused'].includes(item.status))
        || tasks.find(item => item.name === '下载应用更新' && ['queued', 'running', 'paused'].includes(item.status));
      if (!row) return;
      try {
        await rpc.invoke('task.cancel', { taskId: row.taskId });
      } catch (error) {
        renderError(error.message || String(error));
      }
      await refresh();
    }

    async function install() {
      actionError = '';
      if ((useApp().activeTasks || []).length) {
        renderError('请等待当前的剪辑或下载任务完成，再安装更新。');
        return;
      }
      busy = true;
      render();
      try {
        const allowed = await useApp().allowLeave();
        if (!allowed) {
          busy = false;
          render();
          return;
        }
        const result = await rpc.invoke('video.installUpdate', {});
        if (result && result.closeRequired) {
          await rpc.invoke('window.forceClose', {});
        }
      } catch (error) {
        renderError(error.message || String(error));
      }
      busy = false;
      render();
    }

    async function save() {
      actionError = '';
      const url = urlInput.value.trim();
      try {
        status = await rpc.invoke('video.configureUpdates', {
          manifestUrl: status?.onlineConfigured ? '' : url,
          autoCheck: autoInput.checked,
        });
        delete urlInput.dataset.dirty;
        delete autoInput.dataset.dirty;
        useApp().toast('更新设置已保存');
        render();
      } catch (error) {
        renderError(error.message || String(error));
      }
    }

    // The application shell applies CSS zoom. A fixed-position dialog nested
    // inside that transformed coordinate space can land outside the viewport,
    // taking its close button with it. Keep the trigger in the header and move
    // the backdrop/dialog to the document body.
    document.body.append(backdrop, dialog);

    trigger.addEventListener('click', event => {
      event.stopPropagation();
      setOpen(dialog.hidden);
    });
    dialog.querySelector('.app-update-close').addEventListener('click', () => setOpen(false));
    backdrop.addEventListener('click', () => setOpen(false));
    document.addEventListener('pointerdown', event => {
      if (!host.contains(event.target) && !dialog.contains(event.target)) setOpen(false);
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') setOpen(false);
    });
    action('check').addEventListener('click', check);
    action('download').addEventListener('click', download);
    action('cancel').addEventListener('click', cancelDownload);
    action('install').addEventListener('click', install);
    action('save').addEventListener('click', save);
    urlInput.addEventListener('input', () => { urlInput.dataset.dirty = '1'; });
    autoInput.addEventListener('change', () => { autoInput.dataset.dirty = '1'; });

    host.refresh = refresh;
    host.render = render;
    host.syncStatus = nextStatus => {
      if (!nextStatus) return;
      if (nextStatus.phase !== 'error') actionError = '';
      status = nextStatus;
      render();
    };
    host.close = () => setOpen(false);
    host.reset = () => { actionError = ''; setOpen(false); };
    host.loadLocalRelease = loadLocalRelease;
    host.dialog = dialog;
    host.backdrop = backdrop;
    loadLocalRelease();
    return host;
  }

  function localVersionFromPage() {
    const match = String(document.querySelector('.version-tag')?.textContent || '').match(/\d+(?:\.\d+){2,3}/);
    return match ? match[0] : '';
  }

  function mount() {
    const headerRight = document.querySelector('.app-header .header-right');
    if (!headerRight) return;
    mountedVersion = localVersionFromPage();
    if (headerRight.querySelector('.app-update-host')) return;
    const host = buildDialog();
    headerRight.insertBefore(host, headerRight.firstChild);
    window.addEventListener('hashchange', () => host.close?.());
    mounted = true;
  }

  function applyReleaseVersion(release) {
    if (!release || release.product !== 'yangjianjian' || !release.version) return false;
    const app = useApp?.();
    if (!app) return false;
    const current = app.version;
    try {
      if (current && typeof current === 'object' && 'value' in current) current.value = release.version;
      else app.version = release.version;
    } catch {
      return false;
    }
    return String(app.version || '') === release.version;
  }

  function loadReleaseVersion() {
    return fetch('./app-release.json', { cache: 'no-store' })
      .then(response => {
        if (!response.ok) throw new Error(`release metadata ${response.status}`);
        return response.json();
      })
      .then(release => applyReleaseVersion(release))
      .catch(() => false);
  }

  window.addEventListener('yangjianjian:logout', () => {
    sessionRevision += 1;
    operationRevision += 1;
    status = null;
    busy = automaticInFlight = false;
    lastAutomatic = 0;
    resetStartup();
    document.querySelector('.app-update-host')?.reset?.();
    const badge = document.querySelector('.app-update-badge');
    if (badge) badge.hidden = true;
    if (rpc) rpc.invoke('video.clearUpdateSession', {}).catch(() => {});
  });
  window.addEventListener('yangjianjian:update-session', () => {
    resetStartup();
    lastAutomatic = 0;
  });
let releaseVersionRetry = null;
  rpcPromise.then(module => {
    rpc = module.l;
    useApp = module.u;
    let releaseChecks = 0;
    const pinReleaseVersion = async () => {
      await loadReleaseVersion();
      releaseChecks += 1;
      if (releaseChecks >= 80) clearInterval(releaseVersionRetry);
    };
    pinReleaseVersion();
    releaseVersionRetry = setInterval(pinReleaseVersion, 250);
    const observer = new MutationObserver(mount);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
    else mount();
    let startupComplete = false;
    let startupRefreshing = false;
    let startupPoll = null;
    let signedIn = false;
    let nextStatusRetry = 0;
    resetStartup = () => { startupComplete = false; nextStatusRetry = 0; };
    const initializeAutomaticUpdates = async () => {
      const app = useApp();
      const active = app.ready && app.license?.active === true && app.license?.required === false;
      if (active !== signedIn) { signedIn = active; resetStartup(); lastAutomatic = 0; }
      if (!active || startupComplete || startupRefreshing || !mounted || Date.now() < nextStatusRetry) return;
      const session = sessionRevision;
      startupRefreshing = true;
      try {
        const host = document.querySelector('.app-update-host');
        if (!await host?.refresh?.()) { nextStatusRetry = Date.now() + 1500; return; }
        if (session !== sessionRevision) return;
        host?.loadLocalRelease?.();
        await automaticCheck();
        if (session === sessionRevision) startupComplete = true;
      } finally {
        startupRefreshing = false;
      }
    };
    startupPoll = setInterval(initializeAutomaticUpdates, STARTUP_POLL_INTERVAL);
    initializeAutomaticUpdates();
    const automaticPoll = setInterval(() => {
      if (!startupComplete) return;
      const app = useApp();
      if (app.ready && app.license?.active === true && app.license?.required === false) {
        document.querySelector('.app-update-host')?.refresh?.().then(ok => { if (ok) automaticCheck(); });
      }
    }, AUTO_INTERVAL);
  }).catch(() => {});
})();
