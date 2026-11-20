"""Asset 2, the shape cube: Blender's default scene, with the cube remade
from many faces (still flat-sided), a shape key that turns it into a
sphere, and a Geometry Nodes modifier that twists it. It shows that a
button can drive more than bones: a shape key's value, a modifier's input,
the object's own turn.

    blender --background --factory-startup --python dev/scenes/shape_cube.py

Saved as tutorials/_scenes/shape_cube.blend. The tutorials refer to these
names:

- the object Cube;
- its shape key Sphere (0 is a cube, 1 a sphere);
- its modifier Twist, with the input Twist (an angle: how far the top is
  turned against the bottom).
"""

import os
import sys

import bmesh  # type: ignore
import bpy  # type: ignore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

CUTS = 7                       # each side of the cube 8 x 8 faces: round enough as a sphere
RADIUS = 1.25                  # the sphere's radius: about the cube's volume

bpy.ops.wm.read_homefile(use_factory_startup=True)
cube = bpy.data.objects["Cube"]

# the cube: many faces to a side, every one lying on the cube's flat sides
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=2.0)
bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=CUTS, use_grid_fill=True)
bm.to_mesh(cube.data)
bm.free()
cube.data.update()

# Sphere: each vertex pushed out to the same distance from the middle
cube.shape_key_add(name="Basis", from_mix=False)
sphere = cube.shape_key_add(name="Sphere", from_mix=False)
for point, v in zip(sphere.data, cube.data.vertices):
    point.co = v.co.normalized() * RADIUS
sphere.slider_min, sphere.slider_max, sphere.value = 0.0, 1.0, 0.0

# Twist: every point turned about Z by Twist times its height (the cube is 2 tall)
group = bpy.data.node_groups.new("Twist", "GeometryNodeTree")
group.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
twist = group.interface.new_socket("Twist", in_out="INPUT", socket_type="NodeSocketFloat")
twist.subtype, twist.default_value, twist.min_value, twist.max_value = "ANGLE", 0.0, -6.2832, 6.2832
group.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
nodes, links = group.nodes, group.links
inp, out = nodes.new("NodeGroupInput"), nodes.new("NodeGroupOutput")
position = nodes.new("GeometryNodeInputPosition")
split = nodes.new("ShaderNodeSeparateXYZ")
half = nodes.new("ShaderNodeMath")
half.operation = "MULTIPLY"
half.inputs[1].default_value = 0.5             # the top at +Twist / 2, the bottom at -Twist / 2
angle = nodes.new("ShaderNodeMath")
angle.operation = "MULTIPLY"
turn = nodes.new("ShaderNodeVectorRotate")
turn.rotation_type = "Z_AXIS"
move = nodes.new("GeometryNodeSetPosition")
links.new(position.outputs["Position"], split.inputs["Vector"])
links.new(inp.outputs["Twist"], half.inputs[0])
links.new(half.outputs["Value"], angle.inputs[0])
links.new(split.outputs["Z"], angle.inputs[1])
links.new(position.outputs["Position"], turn.inputs["Vector"])
links.new(angle.outputs["Value"], turn.inputs["Angle"])
links.new(inp.outputs["Geometry"], move.inputs["Geometry"])
links.new(turn.outputs["Vector"], move.inputs["Position"])
links.new(move.outputs["Geometry"], out.inputs["Geometry"])
for k, node in enumerate((inp, position, split, half, angle, turn, move, out)):
    node.location = (k * 180.0, 0.0)
modifier = cube.modifiers.new("Twist", "NODES")
modifier.node_group = group

# checked: as made it is the cube; Sphere at 1 a sphere; Twist turns the top
depsgraph = bpy.context.evaluated_depsgraph_get()
top = max(v.co.z for v in cube.evaluated_get(depsgraph).data.vertices)
assert abs(top - 1.0) < 1e-5, top
common.save("shape_cube")
