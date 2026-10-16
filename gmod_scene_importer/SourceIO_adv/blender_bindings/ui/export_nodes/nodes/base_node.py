from typing import TextIO
from bpy.types import Node

class SourceIO_advModelTreeNode:
    @classmethod
    def poll(cls, ntree):
        return ntree.bl_idname == 'SourceIO_advModelDefinition'

    def get_value(self):
        return None

    def update(self):
        return

    def write(self, buffer: TextIO):
        raise NotImplementedError

    def process(self, inputs: dict) -> dict|None:
        raise NotImplementedError(f"process method not implemented for {self.__class__.__name__}")


class SourceIO_advTextureTreeNode(Node, SourceIO_advModelTreeNode):

    def update(self):
        self._sync_io_visibility()

    def _sync_io_visibility(self):
        return