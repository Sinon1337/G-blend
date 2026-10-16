from typing import TextIO

import bpy
from bpy.types import Node

from .base_node import SourceIO_advModelTreeNode


class SourceIO_advModelNode(Node, SourceIO_advModelTreeNode):
    bl_idname = 'SourceIO_advModelNode'
    bl_label = "Model output"
    model_name: bpy.props.StringProperty(name="$modelname")
    mostly_opaque: bpy.props.BoolProperty(name="$mostlyopaque", default=True)
    ambient_boost: bpy.props.BoolProperty(name="$ambientboost", default=True)

    def init(self, context):
        self.inputs.new('SourceIO_advObjectSocket', "Objects").link_limit = 32
        self.inputs.new('SourceIO_advBodygroupSocket', "Bodygroups").link_limit = 32
        self.inputs.new('SourceIO_advSkinSocket', "Skin")
        self.inputs.new('SourceIO_advTextureVtfSocket', "Textures")

    def draw_buttons(self, context, layout):
        layout.operator("SourceIO_adv.evaluate_nodetree")
        layout.prop(self, 'model_name')
        layout.prop(self, 'mostly_opaque')
        layout.prop(self, 'ambient_boost')

    def write(self, buffer: TextIO):
        buffer.write(f'$modelname "{self.model_name}"\n')
        if self.mostly_opaque:
            buffer.write(f'$mostlyopaque\n')
        if self.ambient_boost:
            buffer.write(f'$ambientboost\n')
