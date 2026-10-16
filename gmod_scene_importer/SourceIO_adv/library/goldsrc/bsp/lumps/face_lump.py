from gmod_scene_importer.SourceIO_adv.library.goldsrc.bsp.bsp_file import BspFile
from gmod_scene_importer.SourceIO_adv.library.goldsrc.bsp.lump import Lump, LumpInfo, LumpType
from gmod_scene_importer.SourceIO_adv.library.goldsrc.bsp.structs.face import Face
from gmod_scene_importer.SourceIO_adv.library.utils import Buffer


class FaceLump(Lump):
    LUMP_TYPE = LumpType.LUMP_FACES

    def __init__(self, info: LumpInfo):
        super().__init__(info)
        self.values: list[Face] = []

    def parse(self, buffer: Buffer, bsp: BspFile):
        while buffer:
            face = Face.from_buffer(buffer)
            self.values.append(face)
