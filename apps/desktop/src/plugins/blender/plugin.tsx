import React from 'react'

import { ROUTES_AREA, SIDEBAR_NAV_AREA } from '@/app/routes'
import type { JettsTUIPlugin } from '@/contrib/plugin'

import { BlenderStudioView } from './view'

const blenderPlugin: JettsTUIPlugin = {
  id: 'blender',
  name: 'Blender 3D Studio',
  defaultEnabled: true,
  register(ctx) {
    // 1. Mount full-page 3D Studio route at /blender
    ctx.register({
      id: 'route',
      area: ROUTES_AREA,
      title: 'Blender 3D',
      data: { path: '/blender' },
      render: () => <BlenderStudioView />
    })

    // 2. Add entry to the sidebar top nav
    ctx.register({
      id: 'nav',
      area: SIDEBAR_NAV_AREA,
      data: {
        label: 'Blender 3D',
        path: '/blender',
        codicon: 'package'
      }
    })
  }
}

export default blenderPlugin
