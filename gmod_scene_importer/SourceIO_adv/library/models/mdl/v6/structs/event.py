from dataclasses import dataclass

from gmod_scene_importer.SourceIO_adv.library.shared.types import Vector3
from gmod_scene_importer.SourceIO_adv.library.utils import Buffer


@dataclass(slots=True)
class StudioEvent:
    point: Vector3[float]
    start: int
    end: int

    @classmethod
    def from_buffer(cls, buffer: Buffer):
        point = buffer.read_fmt('3f')
        return cls(point, *buffer.read_fmt('2I'))
