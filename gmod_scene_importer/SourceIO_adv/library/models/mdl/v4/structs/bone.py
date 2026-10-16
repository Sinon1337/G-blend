from dataclasses import dataclass

from gmod_scene_importer.SourceIO_adv.library.shared.types import Vector3
from gmod_scene_importer.SourceIO_adv.library.utils import Buffer


@dataclass(slots=True)
class StudioBone:
    parent: int
    flags: int
    pos: Vector3[float]

    @classmethod
    def from_buffer(cls, buffer: Buffer):
        return cls(buffer.read_int32(), buffer.read_int32(), buffer.read_fmt('3f'))
