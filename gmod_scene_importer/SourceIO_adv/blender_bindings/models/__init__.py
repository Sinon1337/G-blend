from typing import Optional

from gmod_scene_importer.SourceIO_adv.blender_bindings.models.model_tags import MODEL_HANDLERS, choose_model_importer
from gmod_scene_importer.SourceIO_adv.blender_bindings.operators.import_settings_base import ModelOptions
from gmod_scene_importer.SourceIO_adv.blender_bindings.shared.model_container import ModelContainer
from gmod_scene_importer.SourceIO_adv.library.shared.app_id import SteamAppId
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager import ContentManager
from gmod_scene_importer.SourceIO_adv.library.utils import Buffer
from gmod_scene_importer.SourceIO_adv.library.utils.tiny_path import TinyPath
from gmod_scene_importer.SourceIO_adv.logger import SourceLogMan
from . import mdl4, mdl6, mdl10, mdl36, mdl44, mdl49, md3_15, mdl2531, glm2_6

log_manager = SourceLogMan()
logger = log_manager.get_logger('MDL loader')


def import_model(model_path: TinyPath, buffer: Buffer,
                 content_provider: ContentManager,
                 options: ModelOptions,
                 override_steam_id: Optional[SteamAppId] = None,
                 ) -> ModelContainer | None:
    ident, version = buffer.read_fmt("4sI")
    logger.info(f"Trying to load model: {model_path}")
    logger.info(f"Detected magic: {ident!r}, version:{version}")
    steam_id = content_provider.get_steamid_from_asset(model_path)
    handler = choose_model_importer(ident, version, (override_steam_id or steam_id or None))
    if handler is None:
        logger.error(f"No handler found for ident {ident} version: {version}")
        raise ValueError(f"No handler found for ident {ident} version: {version}")
    buffer.seek(0)
    container = handler(model_path, buffer, content_provider, options)
    return container
