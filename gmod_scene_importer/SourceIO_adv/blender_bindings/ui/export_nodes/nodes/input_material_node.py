import bpy
from bpy.types import Node

from .base_node import SourceIO_advModelTreeNode


class SourceIO_advMaterialProto:
    def __init__(self):
        self.mat = None


class SourceIO_advMaterialNode(Node, SourceIO_advModelTreeNode):
    bl_idname = 'SourceIO_advMaterialNode'
    bl_label = 'Material Node'
    mat: bpy.props.PointerProperty(type=bpy.types.Material, name="Material")

    def init(self, context):
        self.outputs.new('SourceIO_advMaterialSocket', "Material")

    def draw_buttons(self, context, layout):
        layout.prop(self, "mat")

    def get_value(self):
        obj = SourceIO_advMaterialProto()
        obj.mat = self.mat
        return obj
