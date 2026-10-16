import bpy
from bpy.types import NodeSocket


class SourceIO_advBodygroupSocket(NodeSocket):
    bl_idname = 'SourceIO_advBodygroupSocket'
    bl_lable = 'Bodygroup socket'
    type = "BODYGROUP"

    def draw(self, context, layout, node, text):
        layout.label(text=text)

    def draw_color(self, context, node):
        return 0.5, 0.2, 0.2, 1.0
