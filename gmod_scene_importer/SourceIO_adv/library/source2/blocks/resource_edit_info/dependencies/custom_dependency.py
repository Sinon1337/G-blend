from dataclasses import dataclass

from gmod_scene_importer.SourceIO_adv.library.utils import Buffer
from gmod_scene_importer.SourceIO_adv.library.source2.keyvalues3.types import Object
from .dependency import Dependency, DependencyList


@dataclass(slots=True)
class CustomDependency(Dependency):
    @classmethod
    def from_vkv3(cls, vkv: Object) -> 'Dependency':
        raise NotImplementedError('Unsupported, if found please report to ValveResourceFormat repo and to SourceIO_adv2')

    @classmethod
    def from_buffer(cls, buffer: Buffer):
        raise NotImplementedError('Unsupported, if found please report to ValveResourceFormat repo and to SourceIO_adv2')


class CustomDependencies(DependencyList[CustomDependency]):
    dependency_type = CustomDependency
