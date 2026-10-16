from gmod_scene_importer.SourceIO_adv.library.goldsrc.bsp.bsp_file import BspFile
from gmod_scene_importer.SourceIO_adv.library.goldsrc.bsp.lump import Lump, LumpInfo, LumpType
from gmod_scene_importer.SourceIO_adv.library.goldsrc.bsp.structs.model import Model
from gmod_scene_importer.SourceIO_adv.library.utils import Buffer


class ModelLump(Lump):
    LUMP_TYPE = LumpType.LUMP_MODELS

    def __init__(self, info: LumpInfo):
        super().__init__(info)
        self.values: list[Model] = []

    def parse(self, buffer: Buffer, bsp: BspFile):
        while buffer:
            self.values.append(Model.from_buffer(buffer))
