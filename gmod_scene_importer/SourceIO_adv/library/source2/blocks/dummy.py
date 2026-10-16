from dataclasses import dataclass

from gmod_scene_importer.SourceIO_adv.library.utils import Buffer
from .base import BaseBlock


@dataclass(slots=True)
class DummyBlock(BaseBlock):
    buffer: Buffer

    @classmethod
    def from_buffer(cls, buffer: Buffer):
        return cls(buffer)

    def to_buffer(self, buffer: Buffer) -> None:
        raise NotImplementedError("Not implemented")

