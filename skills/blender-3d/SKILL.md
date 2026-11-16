---
name: blender-3d
description: >
  Generate, script, and render 3D models and scenes using Blender from natural language descriptions.
  Covers procedural bpy scripting, PBR materials, lighting, cameras, and GLB/PNG export.
triggers:
  - "blender"
  - "3d model"
  - "render 3d"
  - "bpy"
  - "generate 3d"
  - "3d scene"
  - "glb"
  - "gltf"
---

# Blender 3D Studio & Procedural Modeling

Use this skill when the user requests generating 3D models, exporting GLB/GLTF assets, or creating raytraced renders using Blender.

## Quick Start & Available Tools

When Blender is available on the system, the following tools in the `blender-3d` toolset are exposed:

- `blender_status()`: Checks Blender binary path and version.
- `blender_render(prompt, output_format="glb"|"png", preset="auto"|"nature"|"architecture"|"scifi"|"furniture"|"abstract", quality="draft"|"final", custom_bpy_script=None)`:
  Generates a 3D model (GLB) for the JettsTUI 3D Viewer or renders a photorealistic image (PNG).
- `blender_run_script(script, output_path=None)`:
  Executes an arbitrary Python `bpy` script in background mode (`blender -b -P <script>`).

---

## Writing `bpy` Scripts for Blender 4.x / 5.x

When generating custom Blender Python code (`custom_bpy_script`), follow these modern Blender API standards:

### 1. Scene Reset
Always clear existing objects safely:
```python
import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
if not bpy.data.collections:
    col = bpy.data.collections.new("SceneCollection")
    bpy.context.scene.collection.children.link(col)
```

### 2. Principled BSDF Materials (Blender 4.0+)
Note that in Blender 4.0+, the shader node socket names were updated:
- `Base Color` (RGBA tuple)
- `Roughness` (float 0.0 - 1.0)
- `Metallic` (float 0.0 - 1.0)
- `Emission Color` and `Emission Strength` (separated from old `Emission`)

```python
def make_mat(name, color=(0.8, 0.2, 0.2, 1.0), roughness=0.3, metallic=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = color
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
    return mat
```

### 3. Studio Lighting Setup
A three-point lighting setup ensures 3D models look dimensional and clean in both the viewport and renders:
```python
import math

# Key Sun / Directional Light
bpy.ops.object.light_add(type='SUN', location=(5, -5, 8))
sun = bpy.context.active_object
sun.data.energy = 4.0
sun.rotation_euler = (math.radians(45), math.radians(20), math.radians(45))

# Fill Light (Cool ambient soft light)
bpy.ops.object.light_add(type='AREA', location=(-6, -4, 4))
fill = bpy.context.active_object
fill.data.energy = 80.0
fill.data.size = 5.0
fill.data.color = (0.7, 0.85, 1.0)

# Rim Light (Contour highlight)
bpy.ops.object.light_add(type='AREA', location=(0, 6, 5))
rim = bpy.context.active_object
rim.data.energy = 150.0
rim.data.size = 3.0
```

### 4. Auto-Framing Camera
Target the camera at the scene bounding box center:
```python
bpy.ops.object.camera_add(location=(4.0, -4.0, 3.2))
cam = bpy.context.active_object
bpy.context.scene.camera = cam

target = bpy.data.objects.new("Cam_Target", None)
bpy.context.scene.collection.objects.link(target)
target.location = (0, 0, 0.8)

constraint = cam.constraints.new(type='TRACK_TO')
constraint.target = target
constraint.track_axis = 'TRACK_NEGATIVE_Z'
constraint.up_axis = 'UP_Y'
cam.data.lens = 50
```

### 5. GLB Export vs Render
For viewing in the JettsTUI Desktop 3D Viewer:
```python
bpy.ops.export_scene.gltf(
    filepath=out_path,
    export_format='GLB',
    export_materials='EXPORT',
    export_colors=True,
    export_cameras=False,
    export_lights=True
)
```

For rendering still frames (PNG):
```python
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT' # or 'CYCLES'
scene.render.resolution_x = 1080
scene.render.resolution_y = 1080
scene.render.filepath = out_path
scene.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)
```

---

## Viewing Generated Models in JettsTUI Desktop

1. Open JettsTUI Desktop.
2. Click **Blender 3D** in the sidebar navigation or navigate to `/blender`.
3. The interactive WebGL 3D viewer renders the GLB model in real time:
   - Left click + drag: Rotate / Orbit
   - Right click + drag or Shift + Left click: Pan
   - Scroll wheel: Zoom
   - Top bar: Wireframe mode, Studio lights, Camera reset, Snapshot, Download GLB.
   - Sidebar: Enter natural language prompts, select style presets, and generate models directly.
