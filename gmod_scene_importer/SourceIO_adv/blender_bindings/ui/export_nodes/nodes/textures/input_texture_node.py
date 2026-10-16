import bpy
import numpy as np
from bpy.types import Node

from gmod_scene_importer.SourceIO_adv.blender_bindings.ui.export_nodes.nodes.base_node import SourceIO_advTextureTreeNode


class SourceIO_advTextureInputNode(SourceIO_advTextureTreeNode):
    bl_idname = 'SourceIO_advTextureInputNode'
    bl_label = "Texture"
    texture: bpy.props.PointerProperty(type=bpy.types.Image, name="Texture")

    _cached_result: np.ndarray | None = None

    def draw_buttons(self, context, layout):
        self.update()
        layout.prop(self, 'texture')

    def init(self, context):
        self.outputs.new('SourceIO_advTextureSocket', "texture")

    def process(self, inputs: dict) -> dict|None:
        width, height = self.texture.size
        data = np.zeros((height, width, 4), dtype=np.float32)
        self.texture.pixels.foreach_get(data.ravel())
        return {"texture": data}