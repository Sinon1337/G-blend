from gmod_scene_importer.SourceIO_adv.blender_bindings.utils.bpy_utils import get_or_create_material
from gmod_scene_importer.SourceIO_adv.blender_bindings.material_loader.material_loader import ShaderRegistry, ExtraMaterialParameters
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager import ContentManager
from gmod_scene_importer.SourceIO_adv.library.source2 import CompiledMaterialResource
from gmod_scene_importer.SourceIO_adv.library.utils.perf_sampler import timed
from gmod_scene_importer.SourceIO_adv.library.utils.tiny_path import TinyPath



def load_material(content_manager: ContentManager, material_resource: CompiledMaterialResource, material_path: TinyPath,
                  tinted: bool = False):
    material = get_or_create_material(material_path.stem, material_path.as_posix())
    ShaderRegistry.source2_create_nodes(content_manager,material,material_resource, {ExtraMaterialParameters.USE_OBJECT_TINT:tinted})
