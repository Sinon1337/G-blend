import bpy
import numpy as np
from bpy.types import Node

from gmod_scene_importer.SourceIO_adv.blender_bindings.ui.export_nodes.model_tree_nodes import evaluate_tree
from gmod_scene_importer.SourceIO_adv.blender_bindings.ui.export_nodes.nodes.base_node import SourceIO_advTextureTreeNode


class SourceIO_adv_OP_EvaluatePreview(bpy.types.Operator):
    bl_idname = "sourceio_adv.evaluate_texture_preview"
    bl_label = "Evaluate texture preview"

    def execute(self, context: bpy.types.Context):
        tree = context.space_data.node_tree
        node = context.active_node

        preview_nodes = []
        if node.type != "SourceIO_advTexturePreviewNode":
            for n in tree.nodes:
                if n.type == "SourceIO_advTexturePreviewNode":
                    preview_nodes.append(n)
        else:
            preview_nodes.append(node)
        evaluate_tree(tree, preview_nodes)
        return {"FINISHED"}


class SourceIO_advTexturePreviewNode(SourceIO_advTextureTreeNode):
    bl_idname = "SourceIO_advTexturePreviewNode"
    bl_label = "Texture Preview"
    bl_icon = "TEXTURE"

    def init(self, context):
        self.inputs.new("SourceIO_advTextureSocket", "texture")
        self.inputs.new("SourceIO_advTextureChannelSocket", "channel")

    def draw_buttons(self, context, layout):
        layout.label(text="Preview the texture connected to the input.")
        layout.operator(SourceIO_adv_OP_EvaluatePreview.bl_idname, text="Update Preview")

    def process(self, inputs: dict) -> dict | None:
        print(inputs, "texture" in inputs and inputs["texture"] is not None, "channel" in inputs and inputs["channel"] is not None)
        if "texture" in inputs and inputs["texture"] is not None:
            img_data: np.ndarray = inputs["texture"]
        elif "channel" in inputs and inputs["channel"] is not None:
            channel_data: np.ndarray = inputs["channel"]
            if channel_data.ndim == 2:
                img_data = np.stack([channel_data] * 3 + [np.ones_like(channel_data)], axis=-1)
            elif channel_data.ndim == 1:
                img_data = np.stack([channel_data] * 3 + [np.ones_like(channel_data)], axis=-1)
        else:
            return None
        image = bpy.data.images.get("SOURCE_NODES__Texture Preview" + self.name)
        if image is None:
            height, width = img_data.shape[:2]
            image = bpy.data.images.new("SOURCE_NODES__Texture Preview" + self.name, width=width, height=height,
                                        alpha=True)
        elif image.size[0] != img_data.shape[1] or image.size[1] != img_data.shape[0]:
            bpy.data.images.remove(image)
            height, width = img_data.shape[:2]
            image = bpy.data.images.new("SOURCE_NODES__Texture Preview", width=width, height=height)
        image.pixels.foreach_set(img_data.ravel())
        image.update()
        return None
