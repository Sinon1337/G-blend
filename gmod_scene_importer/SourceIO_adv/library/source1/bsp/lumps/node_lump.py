from gmod_scene_importer.SourceIO_adv.library.shared.app_id import SteamAppId
from gmod_scene_importer.SourceIO_adv.library.source1.bsp import Lump, ValveLumpInfo, lump_tag
from gmod_scene_importer.SourceIO_adv.library.source1.bsp.bsp_file import VBSPFile
from gmod_scene_importer.SourceIO_adv.library.source1.bsp.datatypes.node import Node, VNode
from gmod_scene_importer.SourceIO_adv.library.utils import Buffer


@lump_tag(5, 'LUMP_NODES')
class NodeLump(Lump):

    def __init__(self, lump_info: ValveLumpInfo):
        super().__init__(lump_info)
        self.nodes: list[Node] = []

    def parse(self, buffer: Buffer, bsp: VBSPFile):
        while buffer:
            plane = Node.from_buffer(buffer, self.version, bsp)
            self.nodes.append(plane)
        return self


@lump_tag(5, 'LUMP_NODES', steam_id=SteamAppId.VINDICTUS)
class VNodeLump(Lump):

    def __init__(self, lump_info: ValveLumpInfo):
        super().__init__(lump_info)
        self.nodes: list[VNode] = []

    def parse(self, buffer: Buffer, bsp: VBSPFile):
        while buffer:
            plane = VNode.from_buffer(buffer, self.version, bsp)
            self.nodes.append(plane)
        return self
