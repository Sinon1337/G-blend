import nodeitems_utils
from nodeitems_utils import NodeCategory, NodeItem

from gmod_scene_importer.SourceIO_adv.blender_bindings.ui.export_nodes import nodes, sockets
from gmod_scene_importer.SourceIO_adv.blender_bindings.ui.export_nodes.model_tree_nodes import SourceIO_adv_NT_ModelTree, \
    SourceIO_adv_OP_EvaluateNodeTree
from gmod_scene_importer.SourceIO_adv.blender_bindings.ui.export_nodes.nodes.textures.texture_preview import SourceIO_adv_OP_EvaluatePreview


### Node Categories ###
# Node categories are a python system for automatically
# extending the Add menu, toolbar panels and search operator.
# For more examples see release/scripts/startup/nodeitems_builtins.py


# our own base class with an appropriate poll function,
# so the categories only show up in our own tree type


class SourceIO_advNodeCategory(NodeCategory):
    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'sourceio_adv.model_definition'


# all categories in a list
node_categories = [
    # identifier, label, items list
    SourceIO_advNodeCategory('Output', "Output", items=[
        # our basic node
        NodeItem("SourceIO_advModelNode"),
    ]),
    SourceIO_advNodeCategory("Inputs", "Inputs", items=[
        NodeItem("SourceIO_advObjectNode"),
        NodeItem("SourceIO_advMaterialNode"),
    ]),
    SourceIO_advNodeCategory("Skins", "Skins", items=[
        NodeItem("SourceIO_advSkingroupNode"),
        NodeItem("SourceIO_advSkinNode"),
    ]),
    SourceIO_advNodeCategory("Bodygroups", "Bodygroups", items=[
        NodeItem("SourceIO_advBodygroupNode")
    ]),
    SourceIO_advNodeCategory("Materials", "Materials", items=[
        NodeItem("SourceIO_advVertexLitGenericNode")
    ]),
    SourceIO_advNodeCategory("Textures", "Textures", items=[
        NodeItem("SourceIO_advTextureInputNode"),
        NodeItem("SourceIO_advTextureInvertChannelsNode"),
        NodeItem("SourceIO_advTextureSplitChannelsNode"),
        NodeItem("SourceIO_advTextureCombineChannelsNode"),
        NodeItem("SourceIO_advTextureBrightnessContrastNode"),
        NodeItem("SourceIO_advTextureMathNode"),
        NodeItem("SourceIO_advChannelRemapNode"),
        NodeItem("SourceIO_advNormalOpsNode"),
        NodeItem("SourceIO_advHeightToNormalNode"),
        NodeItem("SourceIO_advNormalBlendNode"),
        NodeItem("SourceIO_advColorSpaceNode"),
        NodeItem("SourceIO_advTexturePreviewNode"),
        NodeItem("SourceIO_advTextureToVTFNode")
    ])
]

classes = (
    SourceIO_adv_NT_ModelTree,

    nodes.SourceIO_advObjectNode,
    nodes.SourceIO_advModelNode,
    nodes.SourceIO_advMaterialNode,

    nodes.SourceIO_advBodygroupNode,
    nodes.SourceIO_advSkinNode,
    nodes.SourceIO_advSkingroupNode,

    nodes.SourceIO_advVertexLitGenericNode,

    nodes.SourceIO_advTextureInputNode,
    nodes.SourceIO_advTextureToVTFNode,
    nodes.SourceIO_advTextureInvertChannelsNode,
    nodes.SourceIO_advTextureSplitChannelsNode,
    nodes.SourceIO_advTextureCombineChannelsNode,
    nodes.SourceIO_advTextureBrightnessContrastNode,
    nodes.SourceIO_advTexturePreviewNode,
    nodes.SourceIO_advTextureMathNode,
    nodes.SourceIO_advChannelRemapNode,
    nodes.SourceIO_advNormalOpsNode,
    nodes.SourceIO_advHeightToNormalNode,
    nodes.SourceIO_advNormalBlendNode,
    nodes.SourceIO_advColorSpaceNode,

    sockets.SourceIO_advObjectSocket,
    sockets.SourceIO_advBodygroupSocket,
    sockets.SourceIO_advMaterialSocket,
    sockets.SourceIO_advSkinSocket,
    sockets.SourceIO_advSkinGroupSocket,
    sockets.SourceIO_advTextureSocket,
    sockets.SourceIO_advTextureVtfSocket,
    sockets.SourceIO_advTextureChannelSocket,


    SourceIO_adv_OP_EvaluateNodeTree,
    SourceIO_adv_OP_EvaluatePreview
)


def register_nodes():
    print('Registered nodes')
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)

    nodeitems_utils.register_node_categories('SourceIO_adv_Nodes', node_categories)


def unregister_nodes():
    nodeitems_utils.unregister_node_categories('SourceIO_adv_Nodes')

    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
