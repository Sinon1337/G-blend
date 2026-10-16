from dataclasses import dataclass

from gmod_scene_importer.SourceIO_adv.library.shared.types import Vector3
from gmod_scene_importer.SourceIO_adv.library.source1.bsp.bsp_file import BSPFile
from gmod_scene_importer.SourceIO_adv.library.utils.file_utils import Buffer


@dataclass(slots=True)
class Quake3Plane:
    normal: Vector3[float]
    dist: float

    @classmethod
    def from_buffer(cls, buffer: Buffer, version: int, bsp: BSPFile):
        return cls(buffer.read_fmt('3f'), buffer.read_float())


@dataclass(slots=True)
class ValvePlane(Quake3Plane):
    type: int

    @classmethod
    def from_buffer(cls, buffer: Buffer, version: int, bsp: BSPFile):
        return cls(buffer.read_fmt('fff'), buffer.read_float(), buffer.read_int32())

