import { contextBridge, ipcRenderer, webUtils } from 'electron'

contextBridge.exposeInMainWorld('jettstuiDesktop', {
  getConnection: profile => ipcRenderer.invoke('jettstui:connection', profile),
  revalidateConnection: () => ipcRenderer.invoke('jettstui:connection:revalidate'),
  touchBackend: profile => ipcRenderer.invoke('jettstui:backend:touch', profile),
  getGatewayWsUrl: profile => ipcRenderer.invoke('jettstui:gateway:ws-url', profile),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('jettstui:window:openSession', sessionId, opts),
  openWindow: () => ipcRenderer.invoke('jettstui:window:openInstance'),
  claimAmbientCue: key => ipcRenderer.invoke('jettstui:ambient:claim', key),
  petOverlay: {
    // Main renderer → main process: window lifecycle + drag. `request` is
    // `{ bounds, screen }`; resolves with the screen bounds it actually used.
    open: request => ipcRenderer.invoke('jettstui:pet-overlay:open', request),
    close: () => ipcRenderer.invoke('jettstui:pet-overlay:close'),
    setBounds: bounds => ipcRenderer.send('jettstui:pet-overlay:set-bounds', bounds),
    setIgnoreMouse: ignore => ipcRenderer.send('jettstui:pet-overlay:ignore-mouse', ignore),
    // Flip the overlay focusable (and focus it) while the composer needs keys.
    setFocusable: focusable => ipcRenderer.send('jettstui:pet-overlay:set-focusable', focusable),
    // Main renderer → overlay (forwarded by main): push the latest pet state.
    pushState: payload => ipcRenderer.send('jettstui:pet-overlay:state', payload),
    // Overlay → main renderer (forwarded by main): pop back in / composer submit.
    control: payload => ipcRenderer.send('jettstui:pet-overlay:control', payload),
    // Overlay subscribes to state pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('jettstui:pet-overlay:state', listener)

      return () => ipcRenderer.removeListener('jettstui:pet-overlay:state', listener)
    },
    // Main renderer subscribes to overlay control messages.
    onControl: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('jettstui:pet-overlay:control', listener)

      return () => ipcRenderer.removeListener('jettstui:pet-overlay:control', listener)
    }
  },
  // Quick Entry: the global-hotkey mini composer window. Main owns the OS
  // shortcut + the persisted preference; the quick window only captures text
  // and hands it back, and the primary renderer submits it through the normal
  // prompt path.
  quickEntry: {
    getSettings: () => ipcRenderer.invoke('jettstui:quick-entry:settings:get'),
    setSettings: patch => ipcRenderer.invoke('jettstui:quick-entry:settings:set', patch),
    submit: payload => ipcRenderer.send('jettstui:quick-entry:submit', payload),
    dismiss: () => ipcRenderer.send('jettstui:quick-entry:dismiss'),
    // Primary renderer → main → quick window: gateway connection state + the
    // recent-session options the target picker offers. Main caches the latest
    // payload so a freshly spawned quick window starts from truth.
    pushState: payload => ipcRenderer.send('jettstui:quick-entry:state', payload),
    // Quick window subscribes to those pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('jettstui:quick-entry:state', listener)

      return () => ipcRenderer.removeListener('jettstui:quick-entry:state', listener)
    },
    // Main → primary renderer: a submit captured by the quick window.
    onSubmit: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('jettstui:quick-entry:submit', listener)

      return () => ipcRenderer.removeListener('jettstui:quick-entry:submit', listener)
    },
    // Main → quick window: you were just summoned (reset draft + refocus).
    onShown: callback => {
      const listener = () => callback()
      ipcRenderer.on('jettstui:quick-entry:shown', listener)

      return () => ipcRenderer.removeListener('jettstui:quick-entry:shown', listener)
    }
  },
  getBootProgress: () => ipcRenderer.invoke('jettstui:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('jettstui:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('jettstui:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('jettstui:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('jettstui:connection-config:test', payload),
  sshConfigHosts: () => ipcRenderer.invoke('jettstui:ssh-config:hosts'),
  sshResolveHost: host => ipcRenderer.invoke('jettstui:ssh-config:resolve', host),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('jettstui:connection-config:probe', remoteUrl),
  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('jettstui:connection-config:oauth-login', remoteUrl),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('jettstui:connection-config:oauth-logout', remoteUrl),
  profile: {
    get: () => ipcRenderer.invoke('jettstui:profile:get'),
    set: name => ipcRenderer.invoke('jettstui:profile:set', name)
  },
  api: request => ipcRenderer.invoke('jettstui:api', request),
  notify: payload => ipcRenderer.invoke('jettstui:notify', payload),
  requestMicrophoneAccess: () => ipcRenderer.invoke('jettstui:requestMicrophoneAccess'),
  readFileDataUrl: filePath => ipcRenderer.invoke('jettstui:readFileDataUrl', filePath),
  readFileText: filePath => ipcRenderer.invoke('jettstui:readFileText', filePath),
  selectPaths: options => ipcRenderer.invoke('jettstui:selectPaths', options),
  writeClipboard: text => ipcRenderer.invoke('jettstui:writeClipboard', text),
  saveImageFromUrl: url => ipcRenderer.invoke('jettstui:saveImageFromUrl', url),
  saveImageBuffer: (data, ext) => ipcRenderer.invoke('jettstui:saveImageBuffer', { data, ext }),
  saveClipboardImage: () => ipcRenderer.invoke('jettstui:saveClipboardImage'),
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('jettstui:normalizePreviewTarget', target, baseDir),
  watchPreviewFile: url => ipcRenderer.invoke('jettstui:watchPreviewFile', url),
  stopPreviewFileWatch: id => ipcRenderer.invoke('jettstui:stopPreviewFileWatch', id),
  setActiveWork: payload => ipcRenderer.send('jettstui:active-work', payload),
  setTitleBarTheme: payload => ipcRenderer.send('jettstui:titlebar-theme', payload),
  setNativeTheme: mode => ipcRenderer.send('jettstui:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('jettstui:translucency', payload),
  setKeepAwake: on => ipcRenderer.send('jettstui:keep-awake', on),
  setPreviewShortcutActive: active => ipcRenderer.send('jettstui:previewShortcutActive', Boolean(active)),
  openExternal: url => ipcRenderer.invoke('jettstui:openExternal', url),
  openPreviewInBrowser: url => ipcRenderer.invoke('jettstui:openPreviewInBrowser', url),
  fetchLinkTitle: url => ipcRenderer.invoke('jettstui:fetchLinkTitle', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('jettstui:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('jettstui:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('jettstui:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('jettstui:setting:defaultProjectDir:pick')
  },
  zoom: {
    // Current zoom of this window, as { level, percent }.
    get: () => ipcRenderer.invoke('jettstui:zoom:get'),
    setPercent: percent => ipcRenderer.send('jettstui:zoom:set-percent', percent),
    // Fires on every zoom change, including the Ctrl/Cmd +/-/0 shortcuts,
    // so the settings UI can stay in sync with the keyboard.
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('jettstui:zoom:changed', listener)

      return () => ipcRenderer.removeListener('jettstui:zoom:changed', listener)
    }
  },
  revealLogs: () => ipcRenderer.invoke('jettstui:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('jettstui:logs:recent'),
  readDir: dirPath => ipcRenderer.invoke('jettstui:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('jettstui:fs:gitRoot', startPath),
  revealPath: targetPath => ipcRenderer.invoke('jettstui:fs:reveal', targetPath),
  openDir: dirPath => ipcRenderer.invoke('jettstui:fs:openDir', dirPath),
  renamePath: (targetPath, newName) => ipcRenderer.invoke('jettstui:fs:rename', targetPath, newName),
  writeTextFile: (filePath, content) => ipcRenderer.invoke('jettstui:fs:writeText', filePath, content),
  trashPath: targetPath => ipcRenderer.invoke('jettstui:fs:trash', targetPath),
  git: {
    worktreeList: repoPath => ipcRenderer.invoke('jettstui:git:worktreeList', repoPath),
    worktreeAdd: (repoPath, options) => ipcRenderer.invoke('jettstui:git:worktreeAdd', repoPath, options),
    worktreeRemove: (repoPath, worktreePath, options) =>
      ipcRenderer.invoke('jettstui:git:worktreeRemove', repoPath, worktreePath, options),
    branchSwitch: (repoPath, branch) => ipcRenderer.invoke('jettstui:git:branchSwitch', repoPath, branch),
    branchList: repoPath => ipcRenderer.invoke('jettstui:git:branchList', repoPath),
    baseBranchList: repoPath => ipcRenderer.invoke('jettstui:git:baseBranchList', repoPath),
    repoStatus: repoPath => ipcRenderer.invoke('jettstui:git:repoStatus', repoPath),
    fileDiff: (repoPath, filePath) => ipcRenderer.invoke('jettstui:git:fileDiff', repoPath, filePath),
    scanRepos: (roots, options) => ipcRenderer.invoke('jettstui:git:scanRepos', roots, options),
    review: {
      list: (repoPath, scope, baseRef) => ipcRenderer.invoke('jettstui:git:review:list', repoPath, scope, baseRef),
      diff: (repoPath, filePath, scope, baseRef, staged) =>
        ipcRenderer.invoke('jettstui:git:review:diff', repoPath, filePath, scope, baseRef, staged),
      stage: (repoPath, filePath) => ipcRenderer.invoke('jettstui:git:review:stage', repoPath, filePath),
      unstage: (repoPath, filePath) => ipcRenderer.invoke('jettstui:git:review:unstage', repoPath, filePath),
      revert: (repoPath, filePath) => ipcRenderer.invoke('jettstui:git:review:revert', repoPath, filePath),
      revParse: (repoPath, ref) => ipcRenderer.invoke('jettstui:git:review:revParse', repoPath, ref),
      commit: (repoPath, message, push) => ipcRenderer.invoke('jettstui:git:review:commit', repoPath, message, push),
      commitContext: repoPath => ipcRenderer.invoke('jettstui:git:review:commitContext', repoPath),
      push: repoPath => ipcRenderer.invoke('jettstui:git:review:push', repoPath),
      shipInfo: repoPath => ipcRenderer.invoke('jettstui:git:review:shipInfo', repoPath),
      createPr: repoPath => ipcRenderer.invoke('jettstui:git:review:createPr', repoPath)
    }
  },
  terminal: {
    cwd: id => ipcRenderer.invoke('jettstui:terminal:cwd', id),
    dispose: id => ipcRenderer.invoke('jettstui:terminal:dispose', id),
    resize: (id, size) => ipcRenderer.invoke('jettstui:terminal:resize', id, size),
    start: options => ipcRenderer.invoke('jettstui:terminal:start', options),
    write: (id, data) => ipcRenderer.invoke('jettstui:terminal:write', id, data),
    onData: (id, callback) => {
      const channel = `jettstui:terminal:${id}:data`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    },
    onExit: (id, callback) => {
      const channel = `jettstui:terminal:${id}:exit`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    }
  },
  onClosePreviewRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('jettstui:close-preview-requested', listener)

    return () => ipcRenderer.removeListener('jettstui:close-preview-requested', listener)
  },
  onOpenUpdatesRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('jettstui:open-updates', listener)

    return () => ipcRenderer.removeListener('jettstui:open-updates', listener)
  },
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('jettstui:deep-link', listener)

    return () => ipcRenderer.removeListener('jettstui:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('jettstui:deep-link-ready'),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('jettstui:window-state-changed', listener)

    return () => ipcRenderer.removeListener('jettstui:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('jettstui:focus-session', listener)

    return () => ipcRenderer.removeListener('jettstui:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('jettstui:notification-action', listener)

    return () => ipcRenderer.removeListener('jettstui:notification-action', listener)
  },
  onPreviewFileChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('jettstui:preview-file-changed', listener)

    return () => ipcRenderer.removeListener('jettstui:preview-file-changed', listener)
  },
  onBackendExit: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('jettstui:backend-exit', listener)

    return () => ipcRenderer.removeListener('jettstui:backend-exit', listener)
  },
  // Soft gateway-mode apply finished tearing down the primary backend. Renderer
  // should wipe session lists + re-dial without a window reload.
  onConnectionApplied: callback => {
    const listener = () => callback()
    ipcRenderer.on('jettstui:connection:applied', listener)

    return () => ipcRenderer.removeListener('jettstui:connection:applied', listener)
  },
  onPowerResume: callback => {
    const listener = () => callback()
    ipcRenderer.on('jettstui:power-resume', listener)

    return () => ipcRenderer.removeListener('jettstui:power-resume', listener)
  },
  onBootProgress: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('jettstui:boot-progress', listener)

    return () => ipcRenderer.removeListener('jettstui:boot-progress', listener)
  },
  // First-launch bootstrap progress -- emitted by the install.ps1 stage
  // runner in main.ts (apps/desktop/electron/bootstrap-runner.ts).
  // Renderer's install overlay subscribes to live events and queries the
  // current snapshot via getBootstrapState() to recover after a devtools
  // reload mid-bootstrap.
  getBootstrapState: () => ipcRenderer.invoke('jettstui:bootstrap:get'),
  continueBootstrapLocal: () => ipcRenderer.invoke('jettstui:bootstrap:continue-local'),
  resetBootstrap: () => ipcRenderer.invoke('jettstui:bootstrap:reset'),
  repairBootstrap: () => ipcRenderer.invoke('jettstui:bootstrap:repair'),
  cancelBootstrap: () => ipcRenderer.invoke('jettstui:bootstrap:cancel'),
  onBootstrapEvent: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('jettstui:bootstrap:event', listener)

    return () => ipcRenderer.removeListener('jettstui:bootstrap:event', listener)
  },
  getVersion: () => ipcRenderer.invoke('jettstui:version'),
  getRemoteDisplayReason: () => ipcRenderer.invoke('jettstui:get-remote-display-reason'),
  uninstall: {
    summary: () => ipcRenderer.invoke('jettstui:uninstall:summary'),
    run: mode => ipcRenderer.invoke('jettstui:uninstall:run', { mode })
  },
  updates: {
    check: () => ipcRenderer.invoke('jettstui:updates:check'),
    apply: opts => ipcRenderer.invoke('jettstui:updates:apply', opts),
    getBranch: () => ipcRenderer.invoke('jettstui:updates:branch:get'),
    setBranch: name => ipcRenderer.invoke('jettstui:updates:branch:set', name),
    onProgress: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('jettstui:updates:progress', listener)

      return () => ipcRenderer.removeListener('jettstui:updates:progress', listener)
    }
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('jettstui:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('jettstui:vscode-theme:search', query)
  },
  // Find-in-page (Ctrl/Cmd+F): delegates to Electron's
  // webContents.findInPage on the IPC sender's window so a Cmd+F pressed
  // in a secondary session window searches THAT window, not the primary.
  // `onFoundInPage` returns the unsubscribe fn; the renderer wires it via
  // `initFindInPageListener` in store/find-in-page.ts and tears it down
  // when the FindBar unmounts.
  findInPage: (query, options) => ipcRenderer.invoke('jettstui:find-in-page', query, options),
  stopFindInPage: () => ipcRenderer.invoke('jettstui:stop-find-in-page'),
  onFoundInPage: callback => {
    const listener = (_event, result) => callback(result)
    ipcRenderer.on('jettstui:found-in-page', listener)

    return () => ipcRenderer.removeListener('jettstui:found-in-page', listener)
  }
})
