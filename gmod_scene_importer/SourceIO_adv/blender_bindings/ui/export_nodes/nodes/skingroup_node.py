
import bpy
from bpy.types import Node

from ..sockets import SourceIO_advMaterialSocket, SourceIO_advSkinGroupSocket
from .base_node import SourceIO_advModelTreeNode
from .input_material_node import SourceIO_advMaterialNode


class SourceIO_advSkinGroupProto:
    def __init__(self):
        self.name: str = ""
        self.materials: list[bpy.types.Material] = []

    def __str__(self):
        tmp = f'Skingroup\n'
        for obj in self.materials:
            tmp += "\t" + obj.name
        tmp += '\n'
        return tmp


class SourceIO_advSkingroupNode(Node, SourceIO_advModelTreeNode):
    bl_idname = 'SourceIO_advSkingroupNode'
    bl_label = "Skingroup"

    def init(self, context):
        self.inputs.new('SourceIO_advMaterialSocket', "Material")
        self.outputs.new('SourceIO_advSkinGroupSocket', "Skingroup")

    def update(self, ):
        unused_count = 0
        total_inputs = 0
        for o in self.inputs:  # type:SourceIO_advMaterialSocket
            if (not o.is_linked and o.material is None) and o.bl_idname == "SourceIO_advMaterialSocket":
                unused_count += 1
            else:
                total_inputs += 1
        while unused_count >= 1:
            self.inputs.remove(self.inputs[-1])
            unused_count -= 1
        if not unused_count == 0 and total_inputs <= 32:
            self.inputs.new("SourceIO_advMaterialSocket", "Material")

    def draw_buttons(self, context, layout):
        self.update()

    def get_value(self):
        proto = SourceIO_advSkinGroupProto()
        for input_socket in self.inputs:  # type:SourceIO_advMaterialSocket
            if input_socket.is_linked:
                obj_node: SourceIO_advMaterialNode = input_socket.links[0].from_node
                proto.materials.append(obj_node.get_value().mat)
            else:
                if input_socket.material:
                    proto.materials.append(input_socket.material)
        return proto


class SourceIO_advSkinProto:
    def __init__(self):
        self.skins: list[SourceIO_advSkinGroupProto] = []

    def __str__(self):
        tmp = "Skins:\n"
        for skin in self.skins:
            tmp += '\t' + str(skin) + '\n'
        return tmp


class SourceIO_advSkinNode(Node, SourceIO_advModelTreeNode):
    bl_idname = 'SourceIO_advSkinNode'
    bl_label = "Skin"

    def init(self, context):
        self.inputs.new('SourceIO_advSkinGroupSocket', "Skingroup")

        self.outputs.new('SourceIO_advSkinSocket', "Skin")

    def update(self, ):
        unused_count = 0
        for o in self.inputs:
            if (not o.is_linked) and o.bl_idname == "SourceIO_advSkinGroupSocket":
                unused_count += 1
        if unused_count > 1:
            for _ in range(unused_count - 1):
                self.inputs.remove(self.inputs[-1])
        if unused_count == 0:
            self.inputs.new("SourceIO_advSkinGroupSocket", "Skingroup")

    def draw_buttons(self, context, layout):
        self.update()

    def get_value(self):
        proto = SourceIO_advSkinProto()
        for input_socket in self.inputs:  # type:SourceIO_advSkinGroupSocket
            if input_socket.is_linked:
                obj_node: SourceIO_advMaterialNode = input_socket.links[0].from_node
                proto.skins.append(obj_node.get_value())
        return proto
