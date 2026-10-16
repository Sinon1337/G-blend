from typing import Optional

from gmod_scene_importer.SourceIO_adv.blender_bindings.models.model_tags import register_model_importer
from gmod_scene_importer.SourceIO_adv.blender_bindings.operators.import_settings_base import ModelOptions
from gmod_scene_importer.SourceIO_adv.blender_bindings.shared.model_container import ModelContainer
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.provider import ContentProvider
from gmod_scene_importer.SourceIO_adv.library.utils import Buffer
from gmod_scene_importer.SourceIO_adv.library.utils.tiny_path import TinyPath
from .import_mdl import import_model


@register_model_importer(b"IDST", 6)
def import_mdl6(model_path: TinyPath, buffer: Buffer,
                content_manager: ContentProvider, options: ModelOptions) -> ModelContainer | None:
    texture_mdl = content_manager.find_file(model_path.with_name(model_path.stem + "t.mdl"))

    return import_model(buffer, texture_mdl, options)
