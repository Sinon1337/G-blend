
import bpy
from bpy.types import Node

from ..base_node import SourceIO_advModelTreeNode


class SourceIO_advVertexLitGenericNode(Node, SourceIO_advModelTreeNode):
    bl_idname = 'SourceIO_advVertexLitGenericNode'
    bl_label = "Vertex lit generic Shader"

    mat: bpy.props.PointerProperty(type=bpy.types.Material, name="Material")
    base_texture: bpy.props.PointerProperty(type=bpy.types.Image, name="Base texture")
    normal_texture: bpy.props.PointerProperty(type=bpy.types.Image, name="Normal texture")

    def init(self, context):
        self.outputs.new('SourceIO_advMaterialSocket', "Material")

        self.inputs.new('SourceIO_advTextureSocket', "Base texture")
        self.inputs.new('SourceIO_advTextureSocket', "Normal texture")
        self.inputs.new('NodeSocketFloat', "Phong boost")
        self.inputs.new('NodeSocketFloat', "Phong exponent")

    def draw_buttons(self, context, layout):
        layout.prop(self, "mat")
