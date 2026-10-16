from dataclasses import dataclass

from gmod_scene_importer.SourceIO_adv.library.source1.bsp.bsp_file import VBSPFile
from gmod_scene_importer.SourceIO_adv.library.utils.file_utils import Buffer


@dataclass(slots=True)
class MaterialSort:
    texdata_index: int
    lightmap_header_index: int
    unk_1: int
    vertex_offset: int

    @classmethod
    def from_buffer(cls, buffer: Buffer, version: int, bsp: VBSPFile):
        return cls(*buffer.read_fmt('Hh2I'))
