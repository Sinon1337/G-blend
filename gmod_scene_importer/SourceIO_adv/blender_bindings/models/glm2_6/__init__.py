from gmod_scene_importer.SourceIO_adv.blender_bindings.models.glm2_6.import_glm import import_model
from gmod_scene_importer.SourceIO_adv.blender_bindings.models.model_tags import register_model_importer
from gmod_scene_importer.SourceIO_adv.blender_bindings.operators.import_settings_base import ModelOptions
from gmod_scene_importer.SourceIO_adv.blender_bindings.shared.model_container import ModelContainer
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager import ContentManager
from gmod_scene_importer.SourceIO_adv.library.utils import TinyPath, Buffer


@register_model_importer(b"2LGM", 6)
def import_mdl4(model_path: TinyPath, buffer: Buffer,
                content_manager: ContentManager, options: ModelOptions) -> ModelContainer | None:
    return import_model(model_path.parent.stem, buffer, options, content_manager)
