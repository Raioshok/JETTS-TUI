import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Code mode drives the REAL layout store (applyTree, pane sizes, the file
// browser toggle) — no mocks — so these assert the round trip a user sees:
// enter swaps in the code layout, leave restores the exact previous one.

describe('code mode', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.resetModules()
  })

  afterEach(() => {
    vi.resetModules()
  })

  async function setup() {
    const tree = await import('@/components/pane-shell/tree/store')
    const model = await import('@/components/pane-shell/tree/model')
    const panes = await import('@/store/panes')
    const layout = await import('@/store/layout')
    const { registry } = await import('@/contrib/registry')

    for (const [id, data] of [
      ['sessions', { placement: 'left', width: '14rem' }],
      ['workspace', { placement: 'main', uncloseable: true }],
      ['files', { placement: 'right', width: '15rem' }],
      ['preview', { placement: 'right', width: '30rem' }]
    ] as const) {
      registry.register({ id, area: 'panes', title: id, data, render: () => null })
    }

    const userTree = model.split(
      'row',
      [
        model.group(['sessions'], { id: 'grp-sessions' }),
        model.group(['workspace'], { id: 'grp-main' }),
        model.group(['preview'], { id: 'grp-preview' }),
        model.group(['files'], { id: 'grp-files' }),
        model.group(['terminal'], { id: 'grp-terminal', minimized: true })
      ],
      [1, 3, 1, 1, 1],
      'spl-user'
    )

    tree.declareDefaultTree(userTree)
    registry.register({ id: 'default', area: 'layouts', title: 'Default', data: userTree })
    tree.applyTree(structuredClone(userTree), 'user-mine', { userPlaced: new Set(['files']) })
    // A sash size the user dragged, which must survive the round trip.
    panes.setPaneWidthOverride('files', 300)
    layout.setFileBrowserOpen(false)

    // A toggle-gated pane that a layout PICK would open; a mode switch must not.
    registry.register({
      id: 'terminal',
      area: 'panes',
      title: 'terminal',
      data: { placement: 'bottom', revealOnPreset: true },
      render: () => null
    })
    const openTerminal = vi.fn()
    tree.registerPaneOpener('terminal', openTerminal)

    const codeMode = await import('./code-mode')

    return { codeMode, layout, model, openTerminal, panes, tree, userTree }
  }

  it('enters: applies the code layout, shows the file tree, widens the editor', async () => {
    const { codeMode, layout, model, panes, tree } = await setup()

    codeMode.enterCodeMode(1440)

    expect(codeMode.$codeMode.get()).toBe(true)
    expect(tree.$activePresetId.get()).toBe(codeMode.CODE_PRESET_ID)
    // The file tree sits left of the editor, which sits left of the chat.
    const order = model.allPaneIds(tree.$layoutTree.get()!)
    expect(order.indexOf('files')).toBeLessThan(order.indexOf('preview'))
    expect(order.indexOf('preview')).toBeLessThan(order.indexOf('workspace'))
    expect(layout.$fileBrowserOpen.get()).toBe(true)
    expect(panes.$paneStates.get().preview?.widthOverride).toBe(codeMode.codeEditorWidth(1440))
  })

  it('leaves: restores the previous tree, preset and sash sizes', async () => {
    const { codeMode, model, panes, tree, userTree } = await setup()

    codeMode.enterCodeMode(1440)
    codeMode.exitCodeMode()

    expect(codeMode.$codeMode.get()).toBe(false)
    expect(tree.$activePresetId.get()).toBe('user-mine')
    // The user's panes come back in their order (applyTree may adopt extra
    // panes the code layout introduced, which is its documented behavior).
    const userIds = model.allPaneIds(userTree)
    const restored = model.allPaneIds(tree.$layoutTree.get()!).filter(id => userIds.includes(id))
    expect(restored).toEqual(userIds)
    expect(panes.$paneStates.get().files?.widthOverride).toBe(300)
    expect(panes.$paneStates.get().preview?.widthOverride).toBeUndefined()
    expect(tree.$userPlacedPanes.get().has('files')).toBe(true)
  })

  it('never opens toggle-gated panes (terminal/logs) in either direction', async () => {
    const { codeMode, model, openTerminal, tree } = await setup()

    codeMode.enterCodeMode(1440)
    // The collapsed terminal zone stays collapsed in the code layout.
    expect(model.findGroupOfPane(tree.$layoutTree.get()!, 'terminal')?.minimized).toBe(true)
    codeMode.exitCodeMode()

    expect(openTerminal).not.toHaveBeenCalled()
  })

  it('re-entering keeps the original return point', async () => {
    const { codeMode, tree } = await setup()

    codeMode.enterCodeMode(1440)
    codeMode.enterCodeMode(1440)
    codeMode.exitCodeMode()

    expect(tree.$activePresetId.get()).toBe('user-mine')
  })

  it('leaving without a saved return point falls back to the default layout', async () => {
    const { codeMode, tree } = await setup()

    codeMode.enterCodeMode(1440)
    window.localStorage.removeItem('jettstui.desktop.codeMode.return.v1')
    codeMode.exitCodeMode()

    expect(tree.$activePresetId.get()).toBe('default')
  })

  it('exiting when not in code mode is a no-op', async () => {
    const { codeMode, tree } = await setup()

    codeMode.exitCodeMode()

    expect(tree.$activePresetId.get()).toBe('user-mine')
  })

  it('sizes the editor between sane bounds', async () => {
    const { codeMode } = await setup()

    expect(codeMode.codeEditorWidth(800)).toBe(480)
    expect(codeMode.codeEditorWidth(1440)).toBe(634)
    expect(codeMode.codeEditorWidth(4000)).toBe(1100)
  })
})
