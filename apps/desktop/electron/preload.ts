import { contextBridge, ipcRenderer, webUtils } from 'electron'

contextBridge.exposeInMainWorld('freeideDesktop', {
  getConnection: profile => ipcRenderer.invoke('freeide:connection', profile),
  revalidateConnection: () => ipcRenderer.invoke('freeide:connection:revalidate'),
  touchBackend: profile => ipcRenderer.invoke('freeide:backend:touch', profile),
  getGatewayWsUrl: profile => ipcRenderer.invoke('freeide:gateway:ws-url', profile),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('freeide:window:openSession', sessionId, opts),
  openWindow: () => ipcRenderer.invoke('freeide:window:openInstance'),
  claimAmbientCue: key => ipcRenderer.invoke('freeide:ambient:claim', key),
  petOverlay: {
    // Main renderer → main process: window lifecycle + drag. `request` is
    // `{ bounds, screen }`; resolves with the screen bounds it actually used.
    open: request => ipcRenderer.invoke('freeide:pet-overlay:open', request),
    close: () => ipcRenderer.invoke('freeide:pet-overlay:close'),
    setBounds: bounds => ipcRenderer.send('freeide:pet-overlay:set-bounds', bounds),
    setIgnoreMouse: ignore => ipcRenderer.send('freeide:pet-overlay:ignore-mouse', ignore),
    // Flip the overlay focusable (and focus it) while the composer needs keys.
    setFocusable: focusable => ipcRenderer.send('freeide:pet-overlay:set-focusable', focusable),
    // Main renderer → overlay (forwarded by main): push the latest pet state.
    pushState: payload => ipcRenderer.send('freeide:pet-overlay:state', payload),
    // Overlay → main renderer (forwarded by main): pop back in / composer submit.
    control: payload => ipcRenderer.send('freeide:pet-overlay:control', payload),
    // Overlay subscribes to state pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('freeide:pet-overlay:state', listener)

      return () => ipcRenderer.removeListener('freeide:pet-overlay:state', listener)
    },
    // Main renderer subscribes to overlay control messages.
    onControl: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('freeide:pet-overlay:control', listener)

      return () => ipcRenderer.removeListener('freeide:pet-overlay:control', listener)
    }
  },
  // Quick Entry: the global-hotkey mini composer window. Main owns the OS
  // shortcut + the persisted preference; the quick window only captures text
  // and hands it back, and the primary renderer submits it through the normal
  // prompt path.
  quickEntry: {
    getSettings: () => ipcRenderer.invoke('freeide:quick-entry:settings:get'),
    setSettings: patch => ipcRenderer.invoke('freeide:quick-entry:settings:set', patch),
    submit: payload => ipcRenderer.send('freeide:quick-entry:submit', payload),
    dismiss: () => ipcRenderer.send('freeide:quick-entry:dismiss'),
    // Primary renderer → main → quick window: gateway connection state + the
    // recent-session options the target picker offers. Main caches the latest
    // payload so a freshly spawned quick window starts from truth.
    pushState: payload => ipcRenderer.send('freeide:quick-entry:state', payload),
    // Quick window subscribes to those pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('freeide:quick-entry:state', listener)

      return () => ipcRenderer.removeListener('freeide:quick-entry:state', listener)
    },
    // Main → primary renderer: a submit captured by the quick window.
    onSubmit: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('freeide:quick-entry:submit', listener)

      return () => ipcRenderer.removeListener('freeide:quick-entry:submit', listener)
    },
    // Main → quick window: you were just summoned (reset draft + refocus).
    onShown: callback => {
      const listener = () => callback()
      ipcRenderer.on('freeide:quick-entry:shown', listener)

      return () => ipcRenderer.removeListener('freeide:quick-entry:shown', listener)
    }
  },
  getBootProgress: () => ipcRenderer.invoke('freeide:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('freeide:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('freeide:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('freeide:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('freeide:connection-config:test', payload),
  sshConfigHosts: () => ipcRenderer.invoke('freeide:ssh-config:hosts'),
  sshResolveHost: host => ipcRenderer.invoke('freeide:ssh-config:resolve', host),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('freeide:connection-config:probe', remoteUrl),
  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('freeide:connection-config:oauth-login', remoteUrl),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('freeide:connection-config:oauth-logout', remoteUrl),
  // FreeIDE Cloud: one portal login powers discovery + silent per-agent sign-in
  // (cloud-auto-discovery Phase 3).
  cloud: {
    status: () => ipcRenderer.invoke('freeide:cloud:status'),
    login: () => ipcRenderer.invoke('freeide:cloud:login'),
    logout: () => ipcRenderer.invoke('freeide:cloud:logout'),
    discover: org => ipcRenderer.invoke('freeide:cloud:discover', org),
    agentSignIn: dashboardUrl => ipcRenderer.invoke('freeide:cloud:agent-sign-in', dashboardUrl)
  },
  profile: {
    get: () => ipcRenderer.invoke('freeide:profile:get'),
    set: name => ipcRenderer.invoke('freeide:profile:set', name)
  },
  api: request => ipcRenderer.invoke('freeide:api', request),
  notify: payload => ipcRenderer.invoke('freeide:notify', payload),
  requestMicrophoneAccess: () => ipcRenderer.invoke('freeide:requestMicrophoneAccess'),
  readFileDataUrl: filePath => ipcRenderer.invoke('freeide:readFileDataUrl', filePath),
  readFileText: filePath => ipcRenderer.invoke('freeide:readFileText', filePath),
  selectPaths: options => ipcRenderer.invoke('freeide:selectPaths', options),
  writeClipboard: text => ipcRenderer.invoke('freeide:writeClipboard', text),
  saveImageFromUrl: url => ipcRenderer.invoke('freeide:saveImageFromUrl', url),
  saveImageBuffer: (data, ext) => ipcRenderer.invoke('freeide:saveImageBuffer', { data, ext }),
  saveClipboardImage: () => ipcRenderer.invoke('freeide:saveClipboardImage'),
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('freeide:normalizePreviewTarget', target, baseDir),
  watchPreviewFile: url => ipcRenderer.invoke('freeide:watchPreviewFile', url),
  stopPreviewFileWatch: id => ipcRenderer.invoke('freeide:stopPreviewFileWatch', id),
  setActiveWork: payload => ipcRenderer.send('freeide:active-work', payload),
  setTitleBarTheme: payload => ipcRenderer.send('freeide:titlebar-theme', payload),
  setNativeTheme: mode => ipcRenderer.send('freeide:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('freeide:translucency', payload),
  setKeepAwake: on => ipcRenderer.send('freeide:keep-awake', on),
  setPreviewShortcutActive: active => ipcRenderer.send('freeide:previewShortcutActive', Boolean(active)),
  openExternal: url => ipcRenderer.invoke('freeide:openExternal', url),
  openPreviewInBrowser: url => ipcRenderer.invoke('freeide:openPreviewInBrowser', url),
  fetchLinkTitle: url => ipcRenderer.invoke('freeide:fetchLinkTitle', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('freeide:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('freeide:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('freeide:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('freeide:setting:defaultProjectDir:pick')
  },
  zoom: {
    // Current zoom of this window, as { level, percent }.
    get: () => ipcRenderer.invoke('freeide:zoom:get'),
    setPercent: percent => ipcRenderer.send('freeide:zoom:set-percent', percent),
    // Fires on every zoom change, including the Ctrl/Cmd +/-/0 shortcuts,
    // so the settings UI can stay in sync with the keyboard.
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('freeide:zoom:changed', listener)

      return () => ipcRenderer.removeListener('freeide:zoom:changed', listener)
    }
  },
  revealLogs: () => ipcRenderer.invoke('freeide:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('freeide:logs:recent'),
  readDir: dirPath => ipcRenderer.invoke('freeide:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('freeide:fs:gitRoot', startPath),
  revealPath: targetPath => ipcRenderer.invoke('freeide:fs:reveal', targetPath),
  openDir: dirPath => ipcRenderer.invoke('freeide:fs:openDir', dirPath),
  renamePath: (targetPath, newName) => ipcRenderer.invoke('freeide:fs:rename', targetPath, newName),
  writeTextFile: (filePath, content) => ipcRenderer.invoke('freeide:fs:writeText', filePath, content),
  trashPath: targetPath => ipcRenderer.invoke('freeide:fs:trash', targetPath),
  git: {
    worktreeList: repoPath => ipcRenderer.invoke('freeide:git:worktreeList', repoPath),
    worktreeAdd: (repoPath, options) => ipcRenderer.invoke('freeide:git:worktreeAdd', repoPath, options),
    worktreeRemove: (repoPath, worktreePath, options) =>
      ipcRenderer.invoke('freeide:git:worktreeRemove', repoPath, worktreePath, options),
    branchSwitch: (repoPath, branch) => ipcRenderer.invoke('freeide:git:branchSwitch', repoPath, branch),
    branchList: repoPath => ipcRenderer.invoke('freeide:git:branchList', repoPath),
    baseBranchList: repoPath => ipcRenderer.invoke('freeide:git:baseBranchList', repoPath),
    repoStatus: repoPath => ipcRenderer.invoke('freeide:git:repoStatus', repoPath),
    fileDiff: (repoPath, filePath) => ipcRenderer.invoke('freeide:git:fileDiff', repoPath, filePath),
    scanRepos: (roots, options) => ipcRenderer.invoke('freeide:git:scanRepos', roots, options),
    review: {
      list: (repoPath, scope, baseRef) => ipcRenderer.invoke('freeide:git:review:list', repoPath, scope, baseRef),
      diff: (repoPath, filePath, scope, baseRef, staged) =>
        ipcRenderer.invoke('freeide:git:review:diff', repoPath, filePath, scope, baseRef, staged),
      stage: (repoPath, filePath) => ipcRenderer.invoke('freeide:git:review:stage', repoPath, filePath),
      unstage: (repoPath, filePath) => ipcRenderer.invoke('freeide:git:review:unstage', repoPath, filePath),
      revert: (repoPath, filePath) => ipcRenderer.invoke('freeide:git:review:revert', repoPath, filePath),
      revParse: (repoPath, ref) => ipcRenderer.invoke('freeide:git:review:revParse', repoPath, ref),
      commit: (repoPath, message, push) => ipcRenderer.invoke('freeide:git:review:commit', repoPath, message, push),
      commitContext: repoPath => ipcRenderer.invoke('freeide:git:review:commitContext', repoPath),
      push: repoPath => ipcRenderer.invoke('freeide:git:review:push', repoPath),
      shipInfo: repoPath => ipcRenderer.invoke('freeide:git:review:shipInfo', repoPath),
      createPr: repoPath => ipcRenderer.invoke('freeide:git:review:createPr', repoPath)
    }
  },
  terminal: {
    cwd: id => ipcRenderer.invoke('freeide:terminal:cwd', id),
    dispose: id => ipcRenderer.invoke('freeide:terminal:dispose', id),
    resize: (id, size) => ipcRenderer.invoke('freeide:terminal:resize', id, size),
    start: options => ipcRenderer.invoke('freeide:terminal:start', options),
    write: (id, data) => ipcRenderer.invoke('freeide:terminal:write', id, data),
    onData: (id, callback) => {
      const channel = `freeide:terminal:${id}:data`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    },
    onExit: (id, callback) => {
      const channel = `freeide:terminal:${id}:exit`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    }
  },
  onClosePreviewRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('freeide:close-preview-requested', listener)

    return () => ipcRenderer.removeListener('freeide:close-preview-requested', listener)
  },
  onOpenUpdatesRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('freeide:open-updates', listener)

    return () => ipcRenderer.removeListener('freeide:open-updates', listener)
  },
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('freeide:deep-link', listener)

    return () => ipcRenderer.removeListener('freeide:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('freeide:deep-link-ready'),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('freeide:window-state-changed', listener)

    return () => ipcRenderer.removeListener('freeide:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('freeide:focus-session', listener)

    return () => ipcRenderer.removeListener('freeide:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('freeide:notification-action', listener)

    return () => ipcRenderer.removeListener('freeide:notification-action', listener)
  },
  onPreviewFileChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('freeide:preview-file-changed', listener)

    return () => ipcRenderer.removeListener('freeide:preview-file-changed', listener)
  },
  onBackendExit: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('freeide:backend-exit', listener)

    return () => ipcRenderer.removeListener('freeide:backend-exit', listener)
  },
  // Soft gateway-mode apply finished tearing down the primary backend. Renderer
  // should wipe session lists + re-dial without a window reload.
  onConnectionApplied: callback => {
    const listener = () => callback()
    ipcRenderer.on('freeide:connection:applied', listener)

    return () => ipcRenderer.removeListener('freeide:connection:applied', listener)
  },
  onPowerResume: callback => {
    const listener = () => callback()
    ipcRenderer.on('freeide:power-resume', listener)

    return () => ipcRenderer.removeListener('freeide:power-resume', listener)
  },
  onBootProgress: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('freeide:boot-progress', listener)

    return () => ipcRenderer.removeListener('freeide:boot-progress', listener)
  },
  // First-launch bootstrap progress -- emitted by the install.ps1 stage
  // runner in main.ts (apps/desktop/electron/bootstrap-runner.ts).
  // Renderer's install overlay subscribes to live events and queries the
  // current snapshot via getBootstrapState() to recover after a devtools
  // reload mid-bootstrap.
  getBootstrapState: () => ipcRenderer.invoke('freeide:bootstrap:get'),
  continueBootstrapLocal: () => ipcRenderer.invoke('freeide:bootstrap:continue-local'),
  resetBootstrap: () => ipcRenderer.invoke('freeide:bootstrap:reset'),
  repairBootstrap: () => ipcRenderer.invoke('freeide:bootstrap:repair'),
  cancelBootstrap: () => ipcRenderer.invoke('freeide:bootstrap:cancel'),
  onBootstrapEvent: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('freeide:bootstrap:event', listener)

    return () => ipcRenderer.removeListener('freeide:bootstrap:event', listener)
  },
  getVersion: () => ipcRenderer.invoke('freeide:version'),
  getRemoteDisplayReason: () => ipcRenderer.invoke('freeide:get-remote-display-reason'),
  uninstall: {
    summary: () => ipcRenderer.invoke('freeide:uninstall:summary'),
    run: mode => ipcRenderer.invoke('freeide:uninstall:run', { mode })
  },
  updates: {
    check: () => ipcRenderer.invoke('freeide:updates:check'),
    apply: opts => ipcRenderer.invoke('freeide:updates:apply', opts),
    getBranch: () => ipcRenderer.invoke('freeide:updates:branch:get'),
    setBranch: name => ipcRenderer.invoke('freeide:updates:branch:set', name),
    onProgress: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('freeide:updates:progress', listener)

      return () => ipcRenderer.removeListener('freeide:updates:progress', listener)
    }
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('freeide:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('freeide:vscode-theme:search', query)
  },
  // Find-in-page (Ctrl/Cmd+F): delegates to Electron's
  // webContents.findInPage on the IPC sender's window so a Cmd+F pressed
  // in a secondary session window searches THAT window, not the primary.
  // `onFoundInPage` returns the unsubscribe fn; the renderer wires it via
  // `initFindInPageListener` in store/find-in-page.ts and tears it down
  // when the FindBar unmounts.
  findInPage: (query, options) => ipcRenderer.invoke('freeide:find-in-page', query, options),
  stopFindInPage: () => ipcRenderer.invoke('freeide:stop-find-in-page'),
  onFoundInPage: callback => {
    const listener = (_event, result) => callback(result)
    ipcRenderer.on('freeide:found-in-page', listener)

    return () => ipcRenderer.removeListener('freeide:found-in-page', listener)
  }
})
