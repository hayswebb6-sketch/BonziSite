"""Render Bonzi's animation frames with Blender.

Run headless:

    blender --background --python tools/render_animations.py

Bonzi is a flat 2D image, so every motion here is a transform of a single
textured plane rather than a rigged character. That keeps the result
consistent with the existing artwork instead of fighting it.

The globe is the one genuinely 3D element: a real UV sphere spinning on
its polar axis, so it turns the way a globe actually does.

Frames land in BonziCode/frames/<motion>/frame_NNN.png at exactly the size
the app displays (256x384), so playback needs no scaling.
"""

import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Euler

HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(HERE)

SOURCE=os.path.join(ROOT, "Designer.png")
OUT_ROOT=os.path.join(ROOT, "frames")

# must match the app: Designer.png is 1024x1536, displayed subsample(4,4)
FRAME_W=256
FRAME_H=384
FPS=15

MOTIONS={
    # name        frames  description
    "wave":        (24, "leans side to side with a lift, like a wave"),
    "dance":       (30, "shuffles left and right, squashing on the beat"),
    "spin":        (32, "pinches to zero width and back: a 2D 360 spin"),
    "globe":       (36, "a real 3D globe spins in front of him"),
}


def log(*args):
    print("[render]", *args, flush=True)


def pick_engine(scene):
    for name in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        try:
            scene.render.engine=name
            log("engine:", name)
            return
        except TypeError:
            continue
    raise RuntimeError("no usable render engine")


def make_flat_material(image, name):
    """Unlit textured quad that keeps the source colours and its alpha.

    Blender 5.x's Emission node has no Alpha input, so transparency comes
    from mixing the emission against a Transparent BSDF using the texture's
    own alpha as the factor.
    """
    mat=bpy.data.materials.new(name)
    mat.use_nodes=True
    nodes=mat.node_tree.nodes
    links=mat.node_tree.links
    nodes.clear()

    tex=nodes.new("ShaderNodeTexImage")
    tex.image=image
    tex.interpolation="Linear"
    tex.location=(-620, 0)

    emit=nodes.new("ShaderNodeEmission")
    emit.location=(-360, 120)
    emit.inputs["Strength"].default_value=1.0

    clear=nodes.new("ShaderNodeBsdfTransparent")
    clear.location=(-360, -140)

    mix=nodes.new("ShaderNodeMixShader")
    mix.location=(-120, 0)

    out=nodes.new("ShaderNodeOutputMaterial")
    out.location=(120, 0)

    links.new(tex.outputs["Color"], emit.inputs["Color"])
    alpha_socket=tex.outputs.get("Alpha")
    if alpha_socket is not None:
        links.new(alpha_socket, mix.inputs["Fac"])
    links.new(clear.outputs["BSDF"], mix.inputs[1])
    links.new(emit.outputs["Emission"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])

    # EEVEE Next needs this for real alpha blending; harmless elsewhere.
    for attr, value in (("surface_render_method", "BLENDED"),
                        ("blend_method", "BLEND")):
        if hasattr(mat, attr):
            try:
                setattr(mat, attr, value)
            except (TypeError, ValueError):
                pass
    return mat


def make_globe_texture(width=1024, height=512):
    """Equirectangular globe: ocean, landmasses, ice caps."""
    rng=np.random.default_rng(7)
    lat=np.linspace(-math.pi / 2, math.pi / 2, height)[:, None]
    lon=np.linspace(-math.pi, math.pi, width)[None, :]

    ocean=np.zeros((height, width, 4), dtype=np.float32)
    ocean[..., 0]=0.09
    ocean[..., 1]=0.32
    ocean[..., 2]=0.62
    ocean[..., 3]=1.0

    # a few soft landmasses so the rotation is legible
    land=np.zeros((height, width), dtype=bool)
    for _ in range(7):
        clat=rng.uniform(-1.1, 1.1)
        clon=rng.uniform(-math.pi, math.pi)
        rlat=rng.uniform(0.22, 0.62)
        rlon=rng.uniform(0.35, 0.9)
        blob=(((lat - clat) / rlat) ** 2 + (((lon - clon + math.pi) % (2 * math.pi) - math.pi) / rlon) ** 2) < 1.0
        land |= blob

    for row, colour in ((land, (0.16, 0.52, 0.24, 1.0)),):
        ocean[row]=colour

    # ice caps - lat is (height, 1), so broadcast before boolean indexing
    caps=np.repeat(np.abs(lat) > 1.28, width, axis=1)
    ocean[caps]=(0.92, 0.95, 0.98, 1.0)

    img=bpy.data.images.new("globe", width=width, height=height, alpha=True)
    img.pixels=ocean.ravel()
    return img


def setup_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    pick_engine(scene)

    scene.render.resolution_x=FRAME_W
    scene.render.resolution_y=FRAME_H
    scene.render.resolution_percentage=100
    scene.render.film_transparent=True
    scene.render.image_settings.file_format="PNG"
    scene.render.image_settings.color_mode="RGBA"
    scene.render.image_settings.compression=15
    scene.render.use_file_extension=True

    if scene.render.engine=="CYCLES":
        scene.cycles.samples=16

    cam_data=bpy.data.cameras.new("cam")
    cam_data.type="ORTHO"
    # ortho_scale maps to the larger render dimension, which is height here
    cam_data.ortho_scale=FRAME_H / 1000.0
    cam_data.clip_start=0.01
    cam_data.clip_end=100.0
    cam=bpy.data.objects.new("cam", cam_data)
    cam.location=(0.0, 0.0, 1.0)
    scene.collection.objects.link(cam)
    scene.camera=cam
    return scene


def add_bonzi(scene):
    image=bpy.data.images.load(SOURCE)
    mat=make_flat_material(image, "bonzi")

    bpy.ops.mesh.primitive_plane_add(size=2.0, location=(0.0, 0.0, 0.0))
    plane=bpy.context.object
    plane.name="bonzi"
    plane.data.materials.append(mat)
    # default plane spans 2x2, so scale is half the wanted size
    plane.scale=(FRAME_W / 2000.0, FRAME_H / 2000.0, 1.0)
    return plane


def add_globe(scene):
    mat=make_flat_material(make_globe_texture(), "globe")
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.040, segments=64, ring_count=32,
                                         location=(0.058, -0.030, 0.05))
    globe=bpy.context.object
    globe.name="globe"
    globe.data.materials.append(mat)
    for poly in globe.data.polygons:
        poly.use_smooth=True
    return globe


def reset(plane):
    plane.location=(0.0, 0.0, 0.0)
    plane.rotation_euler=Euler((0.0, 0.0, 0.0))
    plane.scale=(FRAME_W / 2000.0, FRAME_H / 2000.0, 1.0)


def render_sequence(scene, plane, name, count, pose, extra=None):
    out_dir=os.path.join(OUT_ROOT, name)
    os.makedirs(out_dir, exist_ok=True)
    for f in range(count):
        t=(f / max(1, count - 1)) * 2.0 * math.pi
        reset(plane)
        if extra is not None:
            extra(f, t, frame_reset=True)
        pose(plane, f, t)
        if extra is not None:
            extra(f, t, frame_reset=False)
        scene.render.filepath=os.path.join(out_dir, "frame_%03d.png" % f)
        bpy.ops.render.render(write_still=True)
    log("rendered", name, count, "frames")


# ---- motions -------------------------------------------------------------

def pose_wave(plane, f, t):
    swing=math.sin(t)
    plane.rotation_euler=(0.0, 0.0, math.radians(11.0) * swing)
    plane.location=(0.008 * swing, 0.010 * swing, 0.0)
    plane.scale=(FRAME_W / 2000.0 * (1.0 - 0.05 * abs(swing)),
                 FRAME_H / 2000.0 * (1.0 + 0.05 * swing), 1.0)


def pose_dance(plane, f, t):
    beat=math.sin(t * 2.0)
    plane.location=(0.030 * beat, 0.008 * abs(beat), 0.0)
    plane.rotation_euler=(0.0, 0.0, math.radians(-9.0) * beat)
    squash=0.07 * beat
    plane.scale=(FRAME_W / 2000.0 * (1.0 - squash),
                 FRAME_H / 2000.0 * (1.0 + squash), 1.0)


def pose_spin(plane, f, t):
    # squeeze through zero width: reads as a full turn without ever showing
    # the back of a flat image
    phase=(f / 32.0) * math.pi
    width=abs(math.cos(phase))
    pinch=max(0.0, 1.0 - width)
    plane.scale=(FRAME_W / 2000.0 * max(0.004, width),
                 FRAME_H / 2000.0 * (1.0 + 0.10 * pinch), 1.0)
    plane.location=(0.0, 0.012 * pinch, 0.0)


def pose_globe(plane, f, t):
    bob=math.sin(t * 2.0)
    plane.location=(0.0, 0.010 * bob, 0.0)
    plane.scale=(FRAME_W / 2000.0, FRAME_H / 2000.0 * (1.0 + 0.02 * bob), 1.0)


def spin_globe(globe, f, t):
    globe.rotation_euler=(math.radians(18.0), 0.0, -t)
    globe.location=(0.058, -0.030 + 0.006 * math.sin(t * 2.0), 0.05)


def main():
    log("source:", SOURCE, os.path.exists(SOURCE))
    if not os.path.exists(SOURCE):
        sys.exit("missing %s" % SOURCE)

    scene=setup_scene()
    plane=add_bonzi(scene)

    render_sequence(scene, plane, "wave", MOTIONS["wave"][0], pose_wave)
    render_sequence(scene, plane, "dance", MOTIONS["dance"][0], pose_dance)
    render_sequence(scene, plane, "spin", MOTIONS["spin"][0], pose_spin)

    # the globe motion needs a second object, so it gets its own pass
    globe=add_globe(scene)

    def extra(f, t, frame_reset=True):
        if frame_reset:
            globe.rotation_euler=Euler((0.0, 0.0, 0.0))
        else:
            spin_globe(globe, f, t)

    render_sequence(scene, plane, "globe", MOTIONS["globe"][0], pose_globe, extra)

    manifest={
        "frame_width": FRAME_W,
        "frame_height": FRAME_H,
        "fps": FPS,
        "motions": {
            name: {"frames": count, "description": desc}
            for name, (count, desc) in MOTIONS.items()
        },
    }
    with open(os.path.join(OUT_ROOT, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    log("wrote", os.path.join(OUT_ROOT, "manifest.json"))


main()
