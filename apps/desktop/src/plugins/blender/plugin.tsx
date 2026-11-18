import { type JettsTUIPlugin, ROUTES_AREA, SIDEBAR_NAV_AREA } from '@jetts-tui/plugin-sdk'

import { BlenderStudioView } from './view'

const blenderPlugin: JettsTUIPlugin = {
  id: 'blender',
  name: 'Blender 3D Studio',
  defaultEnabled: true,
  register(ctx) {
    ctx.register({
      id: 'route',
      area: ROUTES_AREA,
      title: 'Blender 3D',
      data: { path: '/blender' },
      render: () => <BlenderStudioView ctx={ctx} />
    })

    ctx.register({
      id: 'nav',
      area: SIDEBAR_NAV_AREA,
      data: {
        codicon: 'package',
        label: 'Blender 3D',
        path: '/blender'
      }
    })
  }
}

export default blenderPlugin
