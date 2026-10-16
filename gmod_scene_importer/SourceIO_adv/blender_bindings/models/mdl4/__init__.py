from typing import Optional

from gmod_scene_importer.SourceIO_adv.blender_bindings.models.model_tags import register_model_importer
from gmod_scene_importer.SourceIO_adv.blender_bindings.operators.import_settings_base import ModelOptions
from gmod_scene_importer.SourceIO_adv.blender_bindings.shared.model_container import ModelContainer
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.provider import ContentProvider
from gmod_scene_importer.SourceIO_adv.library.utils import Buffer
from gmod_scene_importer.SourceIO_adv.library.utils.tiny_path import TinyPath
from .import_mdl import import_model


@register_model_importer(b"IDST", 4)
def import_mdl4(model_path: TinyPath, buffer: Buffer,
                content_manager: ContentProvider, options: ModelOptions) -> ModelContainer | None:
    return import_model(model_path.stem, buffer, options)
