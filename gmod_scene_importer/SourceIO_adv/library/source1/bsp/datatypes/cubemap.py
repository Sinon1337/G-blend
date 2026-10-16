from dataclasses import dataclass

from gmod_scene_importer.SourceIO_adv.library.shared.types import Vector3
from gmod_scene_importer.SourceIO_adv.library.source1.bsp.bsp_file import VBSPFile
from gmod_scene_importer.SourceIO_adv.library.utils.file_utils import Buffer


@dataclass(slots=True)
class Cubemap:
    origin: Vector3[int]
    size: int

    @classmethod
    def from_buffer(cls, buffer: Buffer, version: int, bsp: VBSPFile):
        return cls(buffer.read_fmt("3i"), buffer.read_uint32())
