from typing import Optional

from gmod_scene_importer.SourceIO_adv.blender_bindings.models.mdl36 import import_materials
from gmod_scene_importer.SourceIO_adv.blender_bindings.models.model_tags import register_model_importer
from gmod_scene_importer.SourceIO_adv.blender_bindings.models.mdl44.import_mdl import import_model
from gmod_scene_importer.SourceIO_adv.blender_bindings.operators.import_settings_base import ModelOptions
from gmod_scene_importer.SourceIO_adv.blender_bindings.shared.exceptions import RequiredFileNotFound
from gmod_scene_importer.SourceIO_adv.blender_bindings.shared.model_container import ModelContainer
from gmod_scene_importer.SourceIO_adv.blender_bindings.source1.phy import import_physics
from gmod_scene_importer.SourceIO_adv.library.models.mdl.v44 import MdlV44
from gmod_scene_importer.SourceIO_adv.library.models.phy.phy import Phy
from gmod_scene_importer.SourceIO_adv.library.models.vtx import open_vtx
from gmod_scene_importer.SourceIO_adv.library.models.vvd import Vvd
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager import ContentManager
from gmod_scene_importer.SourceIO_adv.library.utils import Buffer
from gmod_scene_importer.SourceIO_adv.library.utils.path_utilities import find_vtx_cm
from gmod_scene_importer.SourceIO_adv.library.utils.tiny_path import TinyPath
from gmod_scene_importer.SourceIO_adv.logger import SourceLogMan

log_manager = SourceLogMan()
logger = log_manager.get_logger('MDL loader')


@register_model_importer(b"IDST", 37)
@register_model_importer(b"IDST", 38)
@register_model_importer(b"IDST", 39)
@register_model_importer(b"IDST", 40)
@register_model_importer(b"IDST", 41)
@register_model_importer(b"IDST", 42)
@register_model_importer(b"IDST", 43)
@register_model_importer(b"IDST", 44)
def import_mdl44(model_path: TinyPath, buffer: Buffer,
                 content_manager: ContentManager, options: ModelOptions) -> ModelContainer | None:
    mdl = MdlV44.from_buffer(buffer)
    vtx_buffer = find_vtx_cm(model_path, content_manager)
    vvd_buffer = content_manager.find_file(model_path.with_suffix(".vvd"))
    if vtx_buffer is None or vvd_buffer is None:
        logger.error(f"Could not find VTX and/or VVD file for {model_path}")
        raise RequiredFileNotFound(f"Could not find VTX and/or VVD file for {model_path}")
    vtx = open_vtx(vtx_buffer)
    vvd = Vvd.from_buffer(vvd_buffer)
    if options.import_textures:
        try:
            import_materials(content_manager, mdl, use_bvlg=options.use_bvlg)
        except Exception as t_ex:
            logger.error(f'Failed to import materials, caused by {t_ex}')
            import traceback
            traceback.print_exc()
    container = import_model(content_manager, mdl, vtx, vvd, options.scale, options.create_flex_drivers)
    if options.import_physics:
        phy_buffer = content_manager.find_file(model_path.with_suffix(".phy"))
        if phy_buffer is None:
            logger.error(f"Could not find PHY file for {model_path}")
        else:
            phy = Phy.from_buffer(phy_buffer)
            import_physics(phy, phy_buffer, mdl, container, options.scale)
    

    return container
