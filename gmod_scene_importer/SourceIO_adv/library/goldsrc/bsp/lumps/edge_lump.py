import numpy as np

from gmod_scene_importer.SourceIO_adv.library.goldsrc.bsp.bsp_file import BspFile
from gmod_scene_importer.SourceIO_adv.library.goldsrc.bsp.lump import Lump, LumpInfo, LumpType
from gmod_scene_importer.SourceIO_adv.library.utils import Buffer


class EdgeLump(Lump):
    LUMP_TYPE = LumpType.LUMP_EDGES

    def __init__(self, info: LumpInfo):
        super().__init__(info)
        self.values = np.array([])

    def parse(self, buffer: Buffer, bsp: BspFile):
        self.values = np.frombuffer(buffer.read(self.info.length), np.uint16).reshape((-1, 2))
