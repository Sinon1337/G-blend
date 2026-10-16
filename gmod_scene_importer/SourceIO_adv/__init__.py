import sys
from pathlib import Path

# sys.modules aliasing removed as imports are fully qualified


if sys.version_info <= (3, 10, 0):
    raise Exception("SourceIO_adv requires python 3.10+ or Blender 4.0.0+")

from gmod_scene_importer.SourceIO_adv.library import loaded_as_addon, running_in_blender

try:
    import bpy
    if bpy.app.version < (3, 6, 0):
        raise Exception("SourceIO_adv only support blender 4.0.0 and above")
except ImportError:
    bpy = ...

bl_info = {
    "name": "SourceIO_adv",
    "author": "RED_EYE, ShadelessFox, Syborg64",
    "version": (5, 5, 3),
    "blender": (4, 0, 0),
    "location": "File > Import > SourceEngine assets",
    "description": "GoldSrc/Source1/Source2 Engine assets(.mdl, .bsp, .vmt, .vtf, .vmdl_c, .vwrld_c, .vtex_c)"
                   "Notice that you cannot delete this addon via blender UI, remove it manually from addons folder",
    "category": "Import-Export"
}

import warnings
warnings.simplefilter("always", DeprecationWarning)

from gmod_scene_importer.SourceIO_adv.library import loaded_as_addon, running_in_blender

if running_in_blender() and loaded_as_addon():
    from gmod_scene_importer.SourceIO_adv.blender_bindings.bindings import register, unregister
    if __name__ == "__main__":
        register()
