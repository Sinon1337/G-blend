from dataclasses import dataclass

from gmod_scene_importer.SourceIO_adv.library.source2.blocks.base import BaseBlock
from gmod_scene_importer.SourceIO_adv.library.source2.utils.ntro_reader import NTROBuffer
from gmod_scene_importer.SourceIO_adv.library.utils import MemoryBuffer, Buffer


@dataclass
class BinaryBlob(BaseBlock):
    data: MemoryBuffer

    @classmethod
    def from_buffer(cls, buffer: NTROBuffer) -> 'BaseBlock':
        data = buffer.read(buffer.size())
        return cls(MemoryBuffer(data))

    def to_buffer(self, buffer: Buffer) -> None:
        buffer.write(self.data.data)
