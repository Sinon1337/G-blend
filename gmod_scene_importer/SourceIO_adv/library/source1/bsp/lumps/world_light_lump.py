from gmod_scene_importer.SourceIO_adv.library.source1.bsp import Lump, ValveLumpInfo, lump_tag
from gmod_scene_importer.SourceIO_adv.library.source1.bsp.bsp_file import VBSPFile
from gmod_scene_importer.SourceIO_adv.library.source1.bsp.datatypes.world_light import WorldLight
from gmod_scene_importer.SourceIO_adv.library.utils import Buffer


@lump_tag(15, 'LUMP_WORLDLIGHTS')
class WorldLightLump(Lump):
    def __init__(self, lump_info: ValveLumpInfo):
        super().__init__(lump_info)
        self.lights: list[WorldLight] = []

    def parse(self, buffer: Buffer, bsp: VBSPFile):
        while buffer:
            self.lights.append(WorldLight.from_buffer(buffer, self.version, bsp))
        return self
