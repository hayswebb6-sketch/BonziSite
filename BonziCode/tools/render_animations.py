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
    "globe":       (36, "a lit 3D globe he holds at chest height while it turns"),
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


def _value_noise(shape, cells, rng):
    """Smooth value noise on a lat/lon grid, wrapping in longitude.

    The wrap matters: the texture is equirectangular and gets wrapped around a
    sphere, so a seam where the noise jumps would show as a hard meridian line
    on the finished globe.
    """
    height, width=shape
    cols=max(2, cells * 2)
    grid=rng.random((cells, cols)).astype(np.float32)

    ys=np.linspace(0.0, cells - 1, height)
    xs=np.linspace(0.0, cols, width, endpoint=False)
    y0=np.floor(ys).astype(int)
    y1=np.minimum(y0 + 1, cells - 1)
    x0=np.floor(xs).astype(int)
    x1=(x0 + 1) % cols

    ty=(ys - y0)[:, None]
    tx=(xs - x0)[None, :]
    ty=ty * ty * (3.0 - 2.0 * ty)
    tx=tx * tx * (3.0 - 2.0 * tx)

    a=grid[np.ix_(y0, x0)]
    b=grid[np.ix_(y0, x1)]
    c=grid[np.ix_(y1, x0)]
    d=grid[np.ix_(y1, x1)]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def make_globe_texture(width=1024, height=512):
    """Equirectangular globe: ocean, continent noise, latitude biomes, ice caps.

    This used to place seven random ellipses of green on a flat blue field. On a
    sphere that reads as a face, because random ellipses on a ball inevitably
    produce a roughly symmetric pair, and a symmetric pair of dark spots on a
    round lit object is a face whether or not anyone meant it to be.

    Fractal noise fixes the face problem structurally: the coastlines are
    irregular at every scale, so there is nothing to pair up. The latitude
    bands then do most of the remaining work, because a planet with green
    tropics, tan deserts around the subtropics and white poles reads as Earth
    long before the coastline detail resolves at this size.

    Deliberately no clouds and no specular highlight. Both add a bright
    off-centre blob, which is another way to accidentally draw eyes.
    """
    rng=np.random.default_rng(20260928)

    lat=np.linspace(-math.pi / 2, math.pi / 2, height)[:, None]
    lon=np.linspace(-math.pi, math.pi, width)[None, :]
    shape=(height, width)

    # four octaves: continents, then progressively smaller detail
    field=np.zeros(shape, dtype=np.float32)
    amplitude=1.0
    total=0.0
    for cells in (3, 6, 12, 24):
        field+=amplitude * _value_noise(shape, cells, rng)
        total+=amplitude
        amplitude*=0.5
    field/=total

    # Push the distribution toward land or sea rather than sitting on the
    # threshold, so coastlines are crisp instead of 50% speckle. 0.65 lands
    # near 30% land, which is about what Earth actually has; the lower values
    # tried first came out at 40% and read as a mostly-land planet.
    field=(field - field.mean()) / (field.std() + 1e-6)
    land=field > 0.65

    depth=np.clip(0.5 + field * 0.5, 0.0, 1.0)
    ocean=np.zeros((height, width, 4), dtype=np.float32)
    ocean[..., 0]=0.05 + 0.04 * (1.0 - depth)
    ocean[..., 1]=0.24 + 0.16 * (1.0 - depth)
    ocean[..., 2]=0.52 + 0.22 * (1.0 - depth)
    ocean[..., 3]=1.0

    abs_lat=np.abs(lat)
    # green near the equator, tan through the desert belts, olive toward the
    # poles before the ice takes over.
    # abs_lat is (height, 1), so these masks have to be repeated across width
    # before they are combined with the (3,) colour vectors. Without that, the
    # where() below collapses to (height, 3) and the boolean assignment fails.
    desert=np.repeat((abs_lat > 0.32) & (abs_lat < 0.82), width, axis=1)
    cold=np.repeat(abs_lat >= 0.82, width, axis=1)
    green=np.array((0.13, 0.42, 0.19), dtype=np.float32)
    tan=np.array((0.55, 0.47, 0.28), dtype=np.float32)
    olive=np.array((0.33, 0.36, 0.28), dtype=np.float32)
    land_colour=np.where(desert, tan, green)
    land_colour=np.where(cold, olive, land_colour).astype(np.float32)
    ocean[land]=np.concatenate(
        [land_colour, np.ones((land_colour.shape[0], land_colour.shape[1], 1),
                              dtype=np.float32)], axis=2
    )

    caps=np.repeat(abs_lat > 1.30, width, axis=1)
    ocean[caps]=(0.88, 0.93, 0.97, 1.0)

    img=bpy.data.images.new("globe", width=width, height=height, alpha=True)
    img.pixels=ocean.ravel()
    return img


def make_globe_material(image, name):
    """A lit material, unlike every other surface in this scene.

    The flat emission material is right for Bonzi, who is a 2D cutout and would
    look wrong under a light. A sphere needs the opposite: a diffuse term with
    a real light behind it, so it has a terminator and a shaded side and reads
    as a solid ball. Pure emission on a sphere is what made the old globe look
    like a flat mask with a face painted on it.

    The emission term is kept at a low weight so the globe still sits at the
    same brightness as the rest of the art instead of going dark on the side
    away from the light.
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

    diff=nodes.new("ShaderNodeBsdfDiffuse")
    diff.location=(-340, 120)
    diff.inputs["Color"].default_value=(1.0, 1.0, 1.0, 1.0)
    diff.inputs["Roughness"].default_value=0.85

    emit=nodes.new("ShaderNodeEmission")
    emit.location=(-340, -120)
    emit.inputs["Strength"].default_value=0.45

    mix=nodes.new("ShaderNodeMixShader")
    mix.location=(-100, 0)
    mix.inputs[0].default_value=0.42

    out=nodes.new("ShaderNodeOutputMaterial")
    out.location=(140, 0)

    links.new(tex.outputs["Color"], diff.inputs["Color"])
    links.new(tex.outputs["Color"], emit.inputs["Color"])
    links.new(diff.outputs["BSDF"], mix.inputs[1])
    links.new(emit.outputs["Emission"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


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

    # One light, upper left, so the globe gets a terminator. Bonzi's plane is
    # emission-only and is unaffected by this, so it does not wash him out.
    light_data=bpy.data.lights.new("key", type="SUN")
    light_data.energy=3.2
    light_data.angle=math.radians(12.0)
    light=bpy.data.objects.new("key", light_data)
    light.location=(-0.6, 0.8, 0.9)
    light.rotation_euler=Euler((math.radians(42.0), 0.0, math.radians(38.0)))
    scene.collection.objects.link(light)
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


# Where the globe sits relative to Bonzi. The frame is 0.256 x 0.384 world
# units (half of 0.256 is 0.128, half of 0.384 is 0.192), so these numbers are
# small fractions of the visible area.
#
# The old values put the ball at z=+0.05, which is a fifth of the frame height
# floating in front of the picture plane with nothing touching it, and gave it
# its own bob on top of Bonzi's. Two independent bobs on a detached object is
# exactly the levitating look. It now sits low and forward, overlapping his
# silhouette at chest height so it reads as something he is holding, and it
# moves with him instead of on its own.
GLOBE_RADIUS=0.042
GLOBE_HOME=(0.050, -0.044, 0.016)
GLOBE_TILT=math.radians(24.0)


def add_globe(scene):
    mat=make_globe_material(make_globe_texture(), "globe")
    bpy.ops.mesh.primitive_uv_sphere_add(radius=GLOBE_RADIUS, segments=64,
                                         ring_count=32, location=GLOBE_HOME)
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
    # Bob with him rather than independently. The amplitude used to be 0.010
    # here plus 0.006 on the globe, and the two drifted against each other,
    # which measured as a 26px twitch on the silhouette across the loop and
    # read as the globe hovering rather than being held.
    bob=math.sin(t * 2.0)
    plane.location=(0.0, 0.004 * bob, 0.0)
    plane.scale=(FRAME_W / 2000.0, FRAME_H / 2000.0 * (1.0 + 0.008 * bob), 1.0)


def spin_globe(globe, f, t):
    # Rotation is the point of this motion, so it stays a full turn per loop.
    # The tilt is on X so the poles are visible, and the location carries only
    # the same small bob as Bonzi.
    globe.rotation_euler=(GLOBE_TILT, 0.0, -t)
    globe.location=(GLOBE_HOME[0],
                    GLOBE_HOME[1] + 0.0025 * math.sin(t * 2.0),
                    GLOBE_HOME[2])


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
