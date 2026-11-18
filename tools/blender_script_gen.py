"""Blender Python (bpy) procedural script generator.

Produces modern, robust Blender 4.x/5.x scripts from natural language prompts,
handling clean scene setup, procedural geometry generation, PBR materials,
three-point studio lighting, auto-framing cameras, and GLB/PNG export.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

_COLOR_PALETTE: Dict[str, Tuple[float, float, float, float]] = {
    "red": (0.85, 0.14, 0.14, 1.0),
    "crimson": (0.78, 0.08, 0.18, 1.0),
    "ruby": (0.88, 0.06, 0.22, 1.0),
    "blue": (0.14, 0.42, 0.92, 1.0),
    "navy": (0.07, 0.14, 0.38, 1.0),
    "cyan": (0.08, 0.82, 0.92, 1.0),
    "teal": (0.08, 0.58, 0.56, 1.0),
    "green": (0.16, 0.68, 0.28, 1.0),
    "emerald": (0.08, 0.72, 0.42, 1.0),
    "yellow": (0.96, 0.82, 0.14, 1.0),
    "gold": (1.0, 0.76, 0.18, 1.0),
    "golden": (1.0, 0.76, 0.18, 1.0),
    "orange": (0.96, 0.45, 0.10, 1.0),
    "bronze": (0.72, 0.45, 0.20, 1.0),
    "copper": (0.82, 0.42, 0.24, 1.0),
    "purple": (0.56, 0.22, 0.88, 1.0),
    "violet": (0.54, 0.30, 0.94, 1.0),
    "pink": (0.94, 0.36, 0.68, 1.0),
    "magenta": (0.90, 0.14, 0.64, 1.0),
    "white": (0.95, 0.95, 0.96, 1.0),
    "silver": (0.82, 0.84, 0.88, 1.0),
    "gray": (0.45, 0.47, 0.50, 1.0),
    "grey": (0.45, 0.47, 0.50, 1.0),
    "black": (0.08, 0.08, 0.10, 1.0),
}

_NUMBER_WORDS: Dict[str, int] = {
    "one": 1,
    "a": 1,
    "an": 1,
    "two": 2,
    "pair": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

_PRIMITIVE_ALIASES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("monkey", ("monkey", "suzanne")),
    ("torus", ("torus", "donut", "doughnut", "ring")),
    ("pyramid", ("pyramid",)),
    ("cone", ("cone", "spike")),
    ("cylinder", ("cylinder", "pillar", "column", "tube", "rod", "pipe")),
    ("icosphere", ("icosphere", "gem", "diamond", "polyhedron")),
    ("sphere", ("sphere", "ball", "orb", "globe", "marble", "planet")),
    ("cube", ("cube", "box", "block", "brick", "die", "dice")),
)


def find_blender_binary() -> Optional[str]:
    """Locate the Blender executable across Windows, macOS, and Linux."""
    import os
    import shutil
    import sys
    from pathlib import Path

    # 1. PATH lookup
    binary = shutil.which("blender")
    if binary and Path(binary).is_file():
        return binary

    # 2. Windows standard installation locations
    if sys.platform == "win32":
        program_files = [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local"),
        ]
        for pf in program_files:
            base = Path(pf) / "Blender Foundation"
            if base.is_dir():
                for sub in sorted(base.glob("Blender*"), reverse=True):
                    candidate = sub / "blender.exe"
                    if candidate.is_file():
                        return str(candidate)

        steam_paths = [
            r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
            r"C:\Program Files\Steam\steamapps\common\Blender\blender.exe",
        ]
        for sp in steam_paths:
            if Path(sp).is_file():
                return sp

    # 3. macOS standard locations
    elif sys.platform == "darwin":
        mac_candidates = [
            "/Applications/Blender.app/Contents/MacOS/Blender",
            "/Applications/Blender.app/Contents/MacOS/blender",
            os.path.expanduser("~/Applications/Blender.app/Contents/MacOS/Blender"),
        ]
        for mc in mac_candidates:
            if Path(mc).is_file():
                return mc

    # 4. Linux standard locations
    else:
        linux_candidates = [
            "/usr/bin/blender",
            "/usr/local/bin/blender",
            "/snap/bin/blender",
            "/var/lib/flatpak/exports/bin/org.blender.Blender",
            os.path.expanduser("~/.local/share/flatpak/exports/bin/org.blender.Blender"),
        ]
        for lc in linux_candidates:
            if Path(lc).is_file():
                return lc

    return None


def parse_prompt_attributes(prompt: str) -> Dict[str, object]:
    """Extract color, surface shader properties, primitive shape, and object count from a prompt."""
    tokens = re.findall(r"[a-z0-9]+", prompt.lower())
    token_set = set(tokens)

    color: Optional[Tuple[float, float, float, float]] = None
    for tok in tokens:
        if tok in _COLOR_PALETTE:
            color = _COLOR_PALETTE[tok]
            break

    is_metallic = bool(
        token_set & {"metal", "metallic", "chrome", "steel", "iron", "gold", "golden", "silver", "bronze", "copper"}
    )
    is_glossy = bool(token_set & {"glass", "crystal", "glossy", "shiny", "polished", "mirror", "ceramic"})
    is_matte = bool(token_set & {"matte", "rough", "clay", "stone", "concrete", "wood", "wooden"})
    is_glowing = bool(token_set & {"glow", "glowing", "neon", "emissive", "laser", "plasma"})

    roughness = 0.15 if is_glossy else (0.85 if is_matte else (0.28 if is_metallic else 0.42))
    metallic = 0.92 if is_metallic else 0.05
    emission_strength = 6.0 if is_glowing else 0.0

    primitive: Optional[str] = None
    for canonical, words in _PRIMITIVE_ALIASES:
        if any(w in token_set or f"{w}s" in token_set or f"{w}es" in token_set for w in words):
            primitive = canonical
            break

    count = 1
    for tok in tokens:
        if tok.isdigit():
            val = int(tok)
            if 1 <= val <= 12 and val not in (3,):  # guard "3d" already tokenized as "3d"
                count = val
                break
        elif tok in _NUMBER_WORDS and _NUMBER_WORDS[tok] > 1:
            count = _NUMBER_WORDS[tok]
            break

    return {
        "color": color,
        "roughness": roughness,
        "metallic": metallic,
        "emission_strength": emission_strength,
        "primitive": primitive,
        "count": count,
    }


def wrap_custom_bpy_script(
    custom_script: str,
    output_path: str,
    output_format: str = "glb",
    quality: str = "draft",
    samples: int = 32,
) -> str:
    """Wrap a custom bpy script so it receives JETTSTUI_BLENDER_OUTPUT_PATH and auto-exports if needed."""
    out_escaped = output_path.replace("\\", "/")
    render_engine = "BLENDER_EEVEE_NEXT" if quality == "draft" else "CYCLES"
    fmt = output_format.lower()

    return f'''import os as _jettstui_os
_jettstui_os.environ.setdefault("JETTSTUI_BLENDER_OUTPUT_PATH", "{out_escaped}")
_jettstui_os.environ.setdefault("JETTSTUI_BLENDER_FORMAT", "{fmt}")

{custom_script}

# --- JettsTUI Post-Script Export Guard ---
def _jettstui_ensure_output():
    import os
    import bpy
    target = "{out_escaped}"
    fmt = "{fmt}"
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        return
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if fmt in ("glb", "gltf"):
        bpy.ops.export_scene.gltf(
            filepath=target,
            export_format='GLB' if fmt == 'glb' else 'GLTF_SEPARATE',
            export_materials='EXPORT',
            export_colors=True,
        )
    else:
        scene = bpy.context.scene
        if not scene.camera:
            bpy.ops.object.camera_add(location=(4.0, -4.0, 3.0))
            cam = bpy.context.active_object
            cam.rotation_euler = (1.1, 0.0, 0.785)
            scene.camera = cam
        if not any(o.type == 'LIGHT' for o in scene.objects):
            bpy.ops.object.light_add(type='SUN', location=(5.0, -5.0, 8.0))
        scene.render.engine = '{render_engine}'
        scene.render.filepath = target
        scene.render.image_settings.file_format = 'PNG'
        if '{render_engine}' == 'CYCLES':
            scene.cycles.samples = {samples}
        bpy.ops.render.render(write_still=True)

_jettstui_ensure_output()
'''


def generate_blender_script(
    prompt: str,
    output_path: str,
    output_format: str = "glb",
    preset: str = "auto",
    quality: str = "draft",
    samples: int = 32,
    resolution: tuple[int, int] = (1080, 1080),
) -> str:
    """Generate a self-contained, executable Blender Python script based on prompt and settings."""
    out_escaped = output_path.replace("\\", "/")
    p_lower = prompt.lower()
    attrs = parse_prompt_attributes(prompt)

    is_nature = any(w in p_lower for w in ["tree", "forest", "mountain", "rock", "terrain", "island", "nature", "landscape"])
    is_house = any(w in p_lower for w in ["house", "building", "cabin", "cottage", "tower", "castle", "temple", "room", "door", "roof"])
    is_scifi = any(w in p_lower for w in ["scifi", "sci-fi", "cyber", "robot", "spaceship", "drone", "reactor", "generator"])
    is_furniture = any(w in p_lower for w in ["chair", "table", "desk", "sofa", "lamp", "furniture", "bed", "stool"])
    is_sculpture = any(w in p_lower for w in ["mobius", "knot", "abstract", "sculpture", "spiral", "helix", "math"])
    is_chest = any(w in p_lower for w in ["chest", "treasure", "coffer", "trunk"])

    if preset == "nature" or (preset == "auto" and is_nature):
        builder_call = "_build_nature_scene()"
    elif preset == "architecture" or (preset == "auto" and is_house):
        builder_call = "_build_architecture_scene()"
    elif preset == "scifi" or (preset == "auto" and is_scifi):
        builder_call = "_build_scifi_scene()"
    elif preset == "furniture" or (preset == "auto" and is_furniture):
        builder_call = "_build_furniture_scene()"
    elif preset == "abstract" or (preset == "auto" and is_sculpture):
        builder_call = "_build_sculpture_scene()"
    elif is_chest:
        builder_call = "_build_stylized_prop_scene()"
    elif attrs["primitive"] is not None or attrs["color"] is not None:
        shape_name = attrs["primitive"] or "sphere"
        rgba = attrs["color"] or (0.54, 0.30, 0.94, 1.0)
        builder_call = (
            f"_build_custom_primitive_scene("
            f"shape={shape_name!r}, count={attrs['count']}, color={rgba!r}, "
            f"roughness={attrs['roughness']}, metallic={attrs['metallic']}, "
            f"emission_strength={attrs['emission_strength']})"
        )
    else:
        builder_call = "_build_stylized_prop_scene()"

    render_engine = "BLENDER_EEVEE_NEXT" if quality == "draft" else "CYCLES"
    accent_override = repr(attrs["color"]) if attrs["color"] is not None else "None"

    script = f'''# Generated by JettsTUI 3D Studio for Blender 4.x / 5.x
import bpy
import math
import random
from mathutils import Vector, Euler

PROMPT_ACCENT_COLOR = {accent_override}

# --- Reset and Clean Factory Scene ---
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if not bpy.data.collections:
        col = bpy.data.collections.new("SceneCollection")
        bpy.context.scene.collection.children.link(col)

# --- PBR Material Helper ---
def create_pbr_material(name, color=(0.8, 0.8, 0.8, 1.0), roughness=0.5, metallic=0.0, emission_color=None, emission_strength=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = color
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
        if emission_color and emission_strength > 0:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = emission_color
            elif "Emission" in bsdf.inputs:
                bsdf.inputs["Emission"].default_value = emission_color
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat

def apply_material(obj, mat):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

# --- Lighting Setup ---
def setup_studio_lighting():
    bpy.ops.object.light_add(type='SUN', location=(5, -5, 8))
    sun = bpy.context.active_object
    sun.name = "Key_Light"
    sun.data.energy = 3.5
    sun.data.color = (1.0, 0.98, 0.95)
    sun.rotation_euler = (math.radians(45), math.radians(20), math.radians(45))

    bpy.ops.object.light_add(type='AREA', location=(-6, -4, 4))
    fill = bpy.context.active_object
    fill.name = "Fill_Light"
    fill.data.energy = 80.0
    fill.data.size = 5.0
    fill.data.color = (0.7, 0.85, 1.0)
    fill.rotation_euler = (math.radians(60), 0, math.radians(-45))

    bpy.ops.object.light_add(type='AREA', location=(0, 6, 5))
    rim = bpy.context.active_object
    rim.name = "Rim_Light"
    rim.data.energy = 150.0
    rim.data.size = 3.0
    rim.data.color = (1.0, 0.9, 0.8)
    rim.rotation_euler = (math.radians(-45), 0, 0)

# --- Auto Framing Camera ---
def setup_camera(target_loc=(0, 0, 0.8), distance=5.5):
    bpy.ops.object.camera_add(location=(distance * 0.75, -distance * 0.75, distance * 0.6))
    cam = bpy.context.active_object
    cam.name = "Main_Camera"
    bpy.context.scene.camera = cam

    target_empty = bpy.data.objects.new("Cam_Target", None)
    bpy.context.scene.collection.objects.link(target_empty)
    target_empty.location = target_loc

    constraint = cam.constraints.new(type='TRACK_TO')
    constraint.target = target_empty
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'
    cam.data.lens = 50

# --- Procedural Geometry Generators ---
def _add_primitive_object(shape, loc):
    if shape == "cube":
        bpy.ops.mesh.primitive_cube_add(size=1.4, location=loc)
        obj = bpy.context.active_object
        bevel = obj.modifiers.new(name="Bevel", type='BEVEL')
        bevel.width = 0.06
        bevel.segments = 3
        return obj
    if shape == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(radius=0.6, depth=1.8, vertices=48, location=loc)
        return bpy.context.active_object
    if shape == "cone":
        bpy.ops.mesh.primitive_cone_add(radius1=0.8, depth=1.8, vertices=48, location=loc)
        return bpy.context.active_object
    if shape == "pyramid":
        bpy.ops.mesh.primitive_cone_add(radius1=1.0, depth=1.6, vertices=4, location=loc)
        obj = bpy.context.active_object
        obj.rotation_euler = (0, 0, math.radians(45))
        return obj
    if shape == "torus":
        bpy.ops.mesh.primitive_torus_add(major_radius=0.85, minor_radius=0.28, major_segments=64, minor_segments=32, location=loc)
        obj = bpy.context.active_object
        obj.rotation_euler = (math.radians(35), math.radians(20), 0)
        return obj
    if shape == "monkey":
        bpy.ops.mesh.primitive_monkey_add(size=1.6, location=loc)
        obj = bpy.context.active_object
        sub = obj.modifiers.new(name="Subsurf", type='SUBSURF')
        sub.levels = 2
        sub.render_levels = 2
        return obj
    if shape == "icosphere":
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.85, location=loc)
        return bpy.context.active_object
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=0.85, location=loc)
    return bpy.context.active_object

def _build_custom_primitive_scene(shape="sphere", count=1, color=(0.54, 0.30, 0.94, 1.0), roughness=0.35, metallic=0.1, emission_strength=0.0):
    em_col = color if emission_strength > 0 else None
    mat_main = create_pbr_material("Mat_Primary", color=color, roughness=roughness, metallic=metallic, emission_color=em_col, emission_strength=emission_strength)

    if count <= 1:
        obj = _add_primitive_object(shape, (0, 0, 0.9))
        obj.name = "Primary_" + shape.capitalize()
        apply_material(obj, mat_main)
    else:
        ring_radius = max(1.4, 0.55 * count)
        for idx in range(count):
            angle = (2.0 * math.pi * idx) / count
            px = ring_radius * math.cos(angle)
            py = ring_radius * math.sin(angle)
            obj = _add_primitive_object(shape, (px, py, 0.9))
            obj.name = f"{{shape.capitalize()}}_{{idx}}"
            apply_material(obj, mat_main)

    bpy.ops.mesh.primitive_cylinder_add(radius=max(2.4, 0.8 * count + 1.2), depth=0.12, vertices=64, location=(0, 0, -0.06))
    stage = bpy.context.active_object
    stage.name = "Studio_Stage"
    mat_stage = create_pbr_material("Mat_Stage", color=(0.14, 0.15, 0.18, 1.0), roughness=0.65, metallic=0.2)
    apply_material(stage, mat_stage)
    setup_camera(target_loc=(0, 0, 0.85), distance=max(4.6, 1.2 * count + 3.4))

def _build_nature_scene():
    bpy.ops.mesh.primitive_grid_add(size=8, x_subdivisions=20, y_subdivisions=20, location=(0, 0, 0))
    terrain = bpy.context.active_object
    terrain.name = "Ground"
    mat_ground = create_pbr_material("Mat_Grass", color=(0.18, 0.45, 0.22, 1.0), roughness=0.8)
    apply_material(terrain, mat_ground)

    for (rx, ry, rz_scale) in [(-2.5, 2.0, 1.8), (2.0, 2.5, 2.2), (-2.8, -1.8, 1.2)]:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1.0, location=(rx, ry, 0.5))
        rock = bpy.context.active_object
        rock.scale = (1.0, 0.9, rz_scale)
        mat_rock = create_pbr_material("Mat_Stone", color=(0.35, 0.38, 0.42, 1.0), roughness=0.85)
        apply_material(rock, mat_rock)

    leaf_col = PROMPT_ACCENT_COLOR or (0.12, 0.42, 0.20, 1.0)
    def add_tree(x, y, scale=1.0):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.15 * scale, depth=1.2 * scale, location=(x, y, 0.6 * scale))
        trunk = bpy.context.active_object
        mat_wood = create_pbr_material("Mat_Wood", color=(0.35, 0.22, 0.12, 1.0), roughness=0.9)
        apply_material(trunk, mat_wood)

        mat_leaf = create_pbr_material("Mat_Pine", color=leaf_col, roughness=0.7)
        for i, (z_off, rad, h) in enumerate([(1.1, 0.9, 1.3), (1.8, 0.7, 1.1), (2.4, 0.45, 0.9)]):
            bpy.ops.mesh.primitive_cone_add(radius1=rad * scale, depth=h * scale, location=(x, y, (z_off + 0.1) * scale))
            cone = bpy.context.active_object
            cone.name = "Foliage_" + str(i)
            apply_material(cone, mat_leaf)

    add_tree(-0.8, -0.6, scale=1.2)
    add_tree(1.2, -0.8, scale=0.9)
    add_tree(0.2, 1.2, scale=1.1)

    stone_mat = create_pbr_material("Camp_Stone", color=(0.4, 0.4, 0.45, 1.0), roughness=0.9)
    for i in range(8):
        angle = i * (2 * math.pi / 8)
        sx = 0.6 * math.cos(angle)
        sy = 0.6 * math.sin(angle)
        bpy.ops.mesh.primitive_cube_add(size=0.18, location=(sx, sy, 0.08))
        st = bpy.context.active_object
        st.rotation_euler = (random.uniform(0, 0.5), random.uniform(0, 0.5), random.uniform(0, 3))
        apply_material(st, stone_mat)

    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.15, location=(0, 0, 0.15))
    ember = bpy.context.active_object
    mat_fire = create_pbr_material("Fire_Glow", color=(1.0, 0.4, 0.05, 1.0), emission_color=(1.0, 0.35, 0.02, 1.0), emission_strength=10.0)
    apply_material(ember, mat_fire)
    setup_camera(target_loc=(0, 0, 0.8), distance=5.2)

def _build_architecture_scene():
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 0.8))
    body = bpy.context.active_object
    body.name = "House_Body"
    body.scale = (1.2, 1.0, 0.8)
    mat_wall = create_pbr_material("Mat_Wall", color=(0.92, 0.88, 0.82, 1.0), roughness=0.6)
    apply_material(body, mat_wall)

    roof_col = PROMPT_ACCENT_COLOR or (0.75, 0.22, 0.15, 1.0)
    bpy.ops.mesh.primitive_cone_add(radius1=1.8, depth=1.0, vertices=4, location=(0, 0, 2.0))
    roof = bpy.context.active_object
    roof.name = "House_Roof"
    roof.rotation_euler = (0, 0, math.radians(45))
    mat_roof = create_pbr_material("Mat_Roof", color=roof_col, roughness=0.5)
    apply_material(roof, mat_roof)

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, -1.02, 0.55))
    door = bpy.context.active_object
    door.scale = (0.35, 0.05, 0.6)
    mat_door = create_pbr_material("Mat_Door", color=(0.35, 0.18, 0.08, 1.0), roughness=0.7)
    apply_material(door, mat_door)

    for wx in [-0.7, 0.7]:
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(wx, -1.02, 0.9))
        win = bpy.context.active_object
        win.scale = (0.25, 0.04, 0.3)
        mat_glass = create_pbr_material("Mat_Window", color=(0.8, 0.95, 1.0, 1.0), roughness=0.1, emission_color=(1.0, 0.9, 0.6, 1.0), emission_strength=2.0)
        apply_material(win, mat_glass)

    bpy.ops.mesh.primitive_cube_add(size=0.3, location=(0.7, 0.4, 2.3))
    chimney = bpy.context.active_object
    chimney.scale = (1.0, 1.0, 2.5)
    mat_brick = create_pbr_material("Mat_Chimney", color=(0.5, 0.3, 0.25, 1.0), roughness=0.8)
    apply_material(chimney, mat_brick)

    bpy.ops.mesh.primitive_cylinder_add(radius=2.8, depth=0.1, location=(0, 0, -0.05))
    base = bpy.context.active_object
    mat_base = create_pbr_material("Mat_Pavement", color=(0.3, 0.32, 0.35, 1.0), roughness=0.8)
    apply_material(base, mat_base)
    setup_camera(target_loc=(0, 0, 1.1), distance=6.0)

def _build_scifi_scene():
    core_col = PROMPT_ACCENT_COLOR or (0.1, 0.8, 1.0, 1.0)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.9, location=(0, 0, 1.2))
    crystal = bpy.context.active_object
    crystal.scale = (0.7, 0.7, 1.4)
    mat_crystal = create_pbr_material("SciFi_Core", color=core_col, roughness=0.1, metallic=0.2, emission_color=core_col, emission_strength=8.0)
    apply_material(crystal, mat_crystal)

    mat_metal = create_pbr_material("Dark_Alloy", color=(0.12, 0.14, 0.18, 1.0), roughness=0.35, metallic=0.9)
    for i, rad in enumerate([1.2, 1.5, 1.8]):
        bpy.ops.mesh.primitive_torus_add(major_radius=rad, minor_radius=0.06, location=(0, 0, 1.2))
        ring = bpy.context.active_object
        ring.name = "Ring_" + str(i)
        ring.rotation_euler = (math.radians(30 * (i + 1)), math.radians(45 * i), 0)
        apply_material(ring, mat_metal)

    bpy.ops.mesh.primitive_cylinder_add(radius=1.8, depth=0.3, vertices=8, location=(0, 0, 0.15))
    base = bpy.context.active_object
    apply_material(base, mat_metal)

    bpy.ops.mesh.primitive_torus_add(major_radius=1.6, minor_radius=0.03, location=(0, 0, 0.3))
    neon = bpy.context.active_object
    mat_neon = create_pbr_material("Neon_Glow", color=core_col, emission_color=core_col, emission_strength=12.0)
    apply_material(neon, mat_neon)
    setup_camera(target_loc=(0, 0, 1.1), distance=5.0)

def _build_furniture_scene():
    wood_col = PROMPT_ACCENT_COLOR or (0.76, 0.55, 0.35, 1.0)
    mat_wood = create_pbr_material("Natural_Oak", color=wood_col, roughness=0.45)
    mat_metal = create_pbr_material("Black_Steel", color=(0.1, 0.1, 0.12, 1.0), roughness=0.3, metallic=0.9)

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 1.0))
    top = bpy.context.active_object
    top.scale = (1.8, 1.0, 0.08)
    apply_material(top, mat_wood)

    for lx in [-0.8, 0.8]:
        for ly in [-0.4, 0.4]:
            bpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=0.96, location=(lx, ly, 0.48))
            leg = bpy.context.active_object
            apply_material(leg, mat_metal)

    bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=0.03, location=(0.6, 0.25, 1.05))
    lamp_base = bpy.context.active_object
    apply_material(lamp_base, mat_metal)

    bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=0.45, location=(0.6, 0.25, 1.28))
    lamp_stem = bpy.context.active_object
    apply_material(lamp_stem, mat_metal)

    bpy.ops.mesh.primitive_cone_add(radius1=0.14, depth=0.18, location=(0.6, 0.25, 1.55))
    lamp_shade = bpy.context.active_object
    lamp_shade.rotation_euler = (math.radians(180), 0, 0)
    mat_shade = create_pbr_material("Lamp_Shade", color=(0.95, 0.9, 0.8, 1.0), emission_color=(1.0, 0.95, 0.8, 1.0), emission_strength=4.0)
    apply_material(lamp_shade, mat_shade)
    setup_camera(target_loc=(0, 0, 0.85), distance=4.5)

def _build_sculpture_scene():
    sculp_col = PROMPT_ACCENT_COLOR or (0.9, 0.3, 0.6, 1.0)
    bpy.ops.mesh.primitive_torus_add(major_radius=1.2, minor_radius=0.35, major_segments=64, minor_segments=32, location=(0, 0, 1.3))
    torus = bpy.context.active_object
    torus.rotation_euler = (math.radians(45), math.radians(30), 0)
    mat_iridescent = create_pbr_material("Prismatic_Ceramic", color=sculp_col, roughness=0.15, metallic=0.85)
    apply_material(torus, mat_iridescent)

    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=(0, 0, 1.3))
    inner = bpy.context.active_object
    mat_inner = create_pbr_material("Glowing_Core", color=(0.2, 0.8, 1.0, 1.0), emission_color=(0.2, 0.8, 1.0, 1.0), emission_strength=5.0)
    apply_material(inner, mat_inner)

    bpy.ops.mesh.primitive_cylinder_add(radius=1.0, depth=0.4, vertices=32, location=(0, 0, 0.2))
    pedestal = bpy.context.active_object
    mat_pedestal = create_pbr_material("White_Marble", color=(0.96, 0.96, 0.96, 1.0), roughness=0.3)
    apply_material(pedestal, mat_pedestal)
    setup_camera(target_loc=(0, 0, 1.1), distance=4.8)

def _build_stylized_prop_scene():
    bpy.ops.mesh.primitive_cube_add(size=1.2, location=(0, 0, 0.6))
    box = bpy.context.active_object
    box.scale = (1.2, 0.8, 0.7)
    mat_gold = create_pbr_material("Mat_Gold", color=(1.0, 0.76, 0.15, 1.0), roughness=0.25, metallic=0.95)
    mat_wood = create_pbr_material("Mat_DarkWood", color=(0.25, 0.15, 0.08, 1.0), roughness=0.6)
    apply_material(box, mat_wood)

    bpy.ops.mesh.primitive_cylinder_add(radius=0.48, depth=1.44, location=(0, 0, 1.05))
    lid = bpy.context.active_object
    lid.rotation_euler = (0, math.radians(90), 0)
    apply_material(lid, mat_wood)

    bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0, -0.5, 0.75))
    clasp = bpy.context.active_object
    apply_material(clasp, mat_gold)

    gem_col = PROMPT_ACCENT_COLOR or (0.9, 0.05, 0.2, 1.0)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.15, location=(0, -0.45, 1.15))
    gem = bpy.context.active_object
    mat_gem = create_pbr_material("Ruby", color=gem_col, roughness=0.1, emission_color=gem_col, emission_strength=4.0)
    apply_material(gem, mat_gem)
    setup_camera(target_loc=(0, 0, 0.8), distance=4.2)

# --- Execution Entrypoint ---
def main():
    reset_scene()
    setup_studio_lighting()
    {builder_call}

    scene = bpy.context.scene
    scene.render.resolution_x = {resolution[0]}
    scene.render.resolution_y = {resolution[1]}

    if not scene.world:
        scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    bg_node = scene.world.node_tree.nodes.get("Background")
    if bg_node:
        bg_node.inputs["Color"].default_value = (0.05, 0.05, 0.07, 1.0)
        bg_node.inputs["Strength"].default_value = 0.5

    out_file = "{out_escaped}"
    fmt = "{output_format}".lower()

    if fmt == "glb" or fmt == "gltf":
        print(f"Exporting GLB scene to {{out_file}}...")
        bpy.ops.export_scene.gltf(
            filepath=out_file,
            export_format='GLB',
            export_materials='EXPORT',
            export_colors=True,
            export_cameras=False,
            export_lights=True
        )
        print("GLB export complete.")

    if fmt == "png" or fmt == "render":
        print(f"Rendering frame to {{out_file}}...")
        scene.render.engine = '{render_engine}'
        scene.render.filepath = out_file
        scene.render.image_settings.file_format = 'PNG'
        if '{render_engine}' == 'CYCLES':
            scene.cycles.samples = {samples}
        bpy.ops.render.render(write_still=True)
        print("Render complete.")

if __name__ == "__main__":
    main()
'''
    return script
