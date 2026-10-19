import sys
import os
import importlib
import fnmatch
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Iterator, Type, Any

# ==============================================================================
# SOURCEIO DETECTION & BRIDGING
# ==============================================================================
# When an external SourceIO is present in Blender, we MUST use it and avoid
# importing internal SourceIO_adv native modules to prevent C-extension conflicts
# (such as duplicate pylib.pyd initialization).
# ==============================================================================

SOURCEIO_AVAILABLE = False
IS_EXTERNAL_SOURCEIO = False
BASE_MODULE = None
SOURCEIO_ERROR = None

def _find_external_sourceio():
    # 1. Check loaded modules in sys.modules
    for name in list(sys.modules.keys()):
        if name in ("SourceIO", "sourceio") or (name.startswith("bl_ext.") and "sourceio" in name.lower()):
            try:
                mod = sys.modules[name]
                if hasattr(mod, "__path__"):
                    importlib.import_module(f"{name}.library.shared.content_manager")
                    return name
            except Exception:
                pass

    # 2. Try direct import
    for cand in ("SourceIO", "sourceio"):
        try:
            importlib.import_module(f"{cand}.library.shared.content_manager")
            return cand
        except Exception:
            pass

    # 3. Check addon_utils / extensions if running inside Blender
    try:
        import addon_utils
        for mod in addon_utils.modules():
            m_name = getattr(mod, "__name__", "")
            if "sourceio" in m_name.lower() and "gmod_scene_importer" not in m_name:
                try:
                    importlib.import_module(f"{m_name}.library.shared.content_manager")
                    return m_name
                except Exception:
                    pass
    except Exception:
        pass

    return None

# Try external first
ext_name = _find_external_sourceio()
if ext_name:
    try:
        BASE_MODULE = ext_name
        ContentManager = getattr(importlib.import_module(f"{BASE_MODULE}.library.shared.content_manager"), "ContentManager")
        VPKContentProvider = getattr(importlib.import_module(f"{BASE_MODULE}.library.shared.content_manager.providers.vpk_provider"), "VPKContentProvider")
        LooseFilesContentProvider = getattr(importlib.import_module(f"{BASE_MODULE}.library.shared.content_manager.providers.loose_files"), "LooseFilesContentProvider")
        _utils_mod = importlib.import_module(f"{BASE_MODULE}.library.utils")
        TinyPath = getattr(_utils_mod, "TinyPath")
        Buffer = getattr(_utils_mod, "Buffer")
        FileBuffer = getattr(_utils_mod, "FileBuffer")
        import_model = getattr(importlib.import_module(f"{BASE_MODULE}.blender_bindings.models"), "import_model")
        serialize_mounted_content = getattr(importlib.import_module(f"{BASE_MODULE}.blender_bindings.utils.resource_utils"), "serialize_mounted_content")
        get_or_create_material = getattr(importlib.import_module(f"{BASE_MODULE}.blender_bindings.utils.bpy_utils"), "get_or_create_material")
        ShaderRegistry = getattr(importlib.import_module(f"{BASE_MODULE}.blender_bindings.material_loader.material_loader"), "ShaderRegistry")
        ShaderBase = getattr(importlib.import_module(f"{BASE_MODULE}.blender_bindings.material_loader.shader_base"), "ShaderBase")
        VMT = getattr(importlib.import_module(f"{BASE_MODULE}.library.source1.vmt"), "VMT")
        BSPFile = getattr(importlib.import_module(f"{BASE_MODULE}.library.source1.bsp.bsp_file"), "BSPFile")
        import_bsp = getattr(importlib.import_module(f"{BASE_MODULE}.blender_bindings.source1.bsp.import_bsp"), "import_bsp")
        ModelOptions = getattr(importlib.import_module(f"{BASE_MODULE}.blender_bindings.operators.import_settings_base"), "ModelOptions")
        ContentProvider = getattr(importlib.import_module(f"{BASE_MODULE}.library.shared.content_manager.provider"), "ContentProvider")

        IS_EXTERNAL_SOURCEIO = True
        SOURCEIO_AVAILABLE = True
        print(f"[GModImporter] Successfully hooked into external SourceIO addon: '{BASE_MODULE}'")
    except Exception as e:
        import traceback
        print(f"[GModImporter] Failed to hook into external SourceIO '{ext_name}': {e}")
        traceback.print_exc()
        ext_name = None

# Fallback to bundled SourceIO_adv if no external SourceIO is present
if not ext_name:
    try:
        BASE_MODULE = "gmod_scene_importer.SourceIO_adv"
        from gmod_scene_importer.SourceIO_adv.library.shared.content_manager import ContentManager
        from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.vpk_provider import VPKContentProvider
        from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.loose_files import LooseFilesContentProvider
        from gmod_scene_importer.SourceIO_adv.library.utils import TinyPath, Buffer, FileBuffer
        from gmod_scene_importer.SourceIO_adv.blender_bindings.models import import_model
        from gmod_scene_importer.SourceIO_adv.blender_bindings.utils.resource_utils import serialize_mounted_content
        from gmod_scene_importer.SourceIO_adv.blender_bindings.utils.bpy_utils import get_or_create_material
        from gmod_scene_importer.SourceIO_adv.blender_bindings.material_loader.material_loader import ShaderRegistry
        from gmod_scene_importer.SourceIO_adv.blender_bindings.material_loader.shader_base import ShaderBase
        from gmod_scene_importer.SourceIO_adv.library.source1.vmt import VMT
        from gmod_scene_importer.SourceIO_adv.library.source1.bsp.bsp_file import BSPFile
        from gmod_scene_importer.SourceIO_adv.blender_bindings.source1.bsp.import_bsp import import_bsp
        from gmod_scene_importer.SourceIO_adv.blender_bindings.operators.import_settings_base import ModelOptions
        from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.provider import ContentProvider

        IS_EXTERNAL_SOURCEIO = False
        SOURCEIO_AVAILABLE = True
        print("[GModImporter] Using internal SourceIO_adv package.")
    except Exception as e:
        import traceback
        print("[GModImporter] Failed to load internal SourceIO_adv:")
        traceback.print_exc()
        SOURCEIO_ERROR = str(e)
        SOURCEIO_AVAILABLE = False
        IS_EXTERNAL_SOURCEIO = False
        ContentManager = None
        VPKContentProvider = None
        LooseFilesContentProvider = None
        TinyPath = None
        Buffer = None
        FileBuffer = None
        import_model = None
        serialize_mounted_content = None
        get_or_create_material = None
        ShaderRegistry = None
        ShaderBase = None
        VMT = None
        BSPFile = None
        import_bsp = None
        ModelOptions = None
        ContentProvider = object

# ==============================================================================
# GMA & GMAContentProvider (Independent Pure-Python Implementation)
# ==============================================================================
# Works with both external SourceIO and internal SourceIO_adv.

@dataclass(slots=True)
class _GMAFileEntry:
    id: int
    name: str
    size: int
    crc: int
    offset: int = field(init=False)

    @classmethod
    def from_buffer(cls, buf) -> Optional['_GMAFileEntry']:
        entry_id = buf.read_uint32()
        if entry_id == 0:
            return None
        name = buf.read_ascii_string()
        size, crc = buf.read_fmt('IQ')
        return cls(entry_id, name, size, crc)

class _GMAParser:
    def __init__(self, filepath, buf_cls):
        self.filepath = filepath
        self.buffer = buf_cls(filepath)
        self.version = 0
        self.steam_id = b''
        self.timestamp = datetime(1970, 1, 1)
        self.required_content = ''
        self.addon_name = ''
        self.addon_description = ''
        self.addon_author = ''
        self.addon_version = 0
        self._content_offset = 0
        self.file_entries = {}

    def read(self):
        buf = self.buffer
        magic = buf.read(4)
        if magic != b"GMAD":
            raise ValueError(f"Invalid GMA file: {self.filepath}")
        self.version, self.steam_id, timestamp = buf.read_fmt('BQQ')
        self.timestamp = timestamp
        if self.version > 1:
            self.required_content = buf.read_ascii_string()
        self.addon_name = buf.read_ascii_string()
        self.addon_description = buf.read_ascii_string()
        self.addon_author = buf.read_ascii_string()
        self.addon_version = buf.read_uint32()

        offset = 0
        while True:
            entry = _GMAFileEntry.from_buffer(buf)
            if entry is None:
                break
            entry.offset = offset
            offset += entry.size
            if TinyPath:
                self.file_entries[TinyPath(entry.name.lower())] = entry
            else:
                self.file_entries[entry.name.lower()] = entry
        self._content_offset = buf.tell()

    def find_file(self, filename):
        fname = filename.as_posix().lower() if hasattr(filename, "as_posix") else str(filename).replace('\\', '/').lower()
        if fname in self.file_entries:
            entry = self.file_entries[fname]
            return self.buffer.slice(self._content_offset + entry.offset, entry.size)
        return None

    def has_file(self, filename) -> bool:
        fname = filename.as_posix().lower() if hasattr(filename, "as_posix") else str(filename).replace('\\', '/').lower()
        return fname in self.file_entries

# Try loading existing GMAContentProvider if available in package
GMAContentProvider = None
if SOURCEIO_AVAILABLE and not IS_EXTERNAL_SOURCEIO:
    try:
        from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.gma_provider import GMAContentProvider
    except Exception:
        pass

if GMAContentProvider is None and SOURCEIO_AVAILABLE:
    class BridgeGMAContentProvider(ContentProvider):
        def __init__(self, filepath, override_steamid=0):
            super().__init__(filepath)
            self._override_steamid = override_steamid
            self._initialized = False
            self.gma_archive = _GMAParser(filepath, FileBuffer)

        def _init(self):
            if self._initialized:
                return
            try:
                self.gma_archive.read()
            except Exception as e:
                pass
            self._initialized = True

        def check(self, filepath) -> bool:
            self._init()
            return self.gma_archive.has_file(filepath)

        def get_relative_path(self, filepath):
            return None

        def get_provider_from_path(self, filepath):
            if self.check(filepath):
                return self
            return None

        def get_steamid_from_asset(self, asset_path):
            if self.check(asset_path):
                return self.steam_id
            return None

        @property
        def root(self):
            return self.filepath.parent

        @property
        def name(self) -> str:
            return self.filepath.stem

        def glob(self, pattern: str):
            self._init()
            files = []
            for file_name, entry in self.gma_archive.file_entries.items():
                p_str = file_name.as_posix() if hasattr(file_name, "as_posix") else str(file_name)
                if fnmatch.fnmatch(p_str, pattern):
                    files.append((file_name, self.gma_archive.find_file(file_name)))
            return iter(files)

        def find_file(self, filepath):
            self._init()
            entry = self.gma_archive.find_file(filepath)
            if entry:
                return entry
            return None

        @property
        def steam_id(self):
            return self._override_steamid or 4000

    GMAContentProvider = BridgeGMAContentProvider

# ==============================================================================
# GMOD MOUNT SETUP (Always defined and callable)
# ==============================================================================

def setup_gmod_mounts(context, cm, user_path, override_cache_path=None):
    if not SOURCEIO_AVAILABLE or cm is None:
        print("[GModImporter] Cannot setup mounts: SourceIO is not available.")
        return

    import bpy
    # 0. GMod Root (Loose Files from downloads/etc)
    garrysmod_dir = user_path / "garrysmod" if (user_path / "garrysmod").exists() else user_path
    if garrysmod_dir.exists():
        cm.add_child(LooseFilesContentProvider(TinyPath(str(garrysmod_dir))))

    # 1. Local Addons (Priority 1)
    addons_dir = None
    for p in [user_path / "garrysmod/addons", user_path / "addons"]:
        if p.exists():
            addons_dir = p
            break

    if addons_dir:
        for item in os.listdir(str(addons_dir)):
            item_path = addons_dir / item
            if item.lower().endswith(".gma") and GMAContentProvider:
                cm.add_child(GMAContentProvider(TinyPath(str(item_path))))
            elif os.path.isdir(str(item_path)):
                cm.add_child(LooseFilesContentProvider(TinyPath(str(item_path))))

    # 1.5 Local Workshop Cache (GarrysMod/garrysmod/cache/workshop)
    local_workshop = None
    for p in [user_path / "garrysmod/cache/workshop", user_path / "cache/workshop"]:
        if p.exists():
            local_workshop = p
            break

    if local_workshop:
        for item in os.listdir(str(local_workshop)):
            if item.lower().endswith(".gma") and GMAContentProvider:
                cm.add_child(GMAContentProvider(TinyPath(str(local_workshop / item))))

    # 3. Standard Games (HL2 / CSS)
    game_root = user_path
    if getattr(context.scene, "gmod_mount_standard", True):
        if game_root:
            hl2_dir = game_root / "hl2"
            se_dir = game_root / "sourceengine"
            target_dirs = [d for d in [hl2_dir, se_dir] if d.exists()]
            for t_dir in target_dirs:
                cm.add_child(LooseFilesContentProvider(TinyPath(str(t_dir))))
                cm.add_child(VPKContentProvider(TinyPath(str(t_dir / "hl2_textures_dir.vpk"))))
                cm.add_child(VPKContentProvider(TinyPath(str(t_dir / "hl2_misc_dir.vpk"))))
                if (t_dir / "content_hl2_dir.vpk").exists():
                    cm.add_child(VPKContentProvider(TinyPath(str(t_dir / "content_hl2_dir.vpk"))))

    # 2. Native Steam Workshop (.bin / .gma)
    workshop_path = getattr(context.scene, "gmod_workshop_path", None)
    if not workshop_path or not os.path.exists(workshop_path):
        auto_path = user_path.parent.parent / "workshop/content/4000"
        if auto_path.exists():
            workshop_path = str(auto_path)
        else:
            auto_path = user_path.parent.parent.parent / "workshop/content/4000"
            if auto_path.exists():
                workshop_path = str(auto_path)

    if workshop_path and os.path.exists(workshop_path) and GMAContentProvider:
        workshop_p = TinyPath(workshop_path)
        import itertools
        for gma in itertools.chain(workshop_p.glob('**/*.gma'), workshop_p.glob('**/*.bin')):
            try:
                cm.add_child(GMAContentProvider(gma))
            except Exception:
                pass

    # 3. Workshop Cache (Priority 3)
    cache_path = override_cache_path
    if not cache_path:
        cache_path = getattr(context.scene, "gmod_cache_path", None)
    if not cache_path:
        cache_path = os.path.join(bpy.utils.resource_path('USER'), "gmod_workshop_cache")
    merged_cache_path = os.path.join(cache_path, "merged_content")
    if os.path.exists(merged_cache_path):
        cm.add_child(LooseFilesContentProvider(TinyPath(merged_cache_path)))

    # 3. GMod Base Content (Priority 3)
    gmod_base_dir = user_path / 'garrysmod' if (user_path / 'garrysmod').exists() else user_path
    if gmod_base_dir.exists():
        for f in os.listdir(str(gmod_base_dir)):
            f_low = f.lower()
            if f_low.endswith(".vpk"):
                if "_dir.vpk" in f_low or not any(c.isdigit() for c in f_low.replace(".vpk", "")[-3:]):
                    try:
                        cm.add_child(VPKContentProvider(TinyPath(str(gmod_base_dir / f))))
                    except Exception as e:
                        print(f"    [!] Failed to mount {f}: {e}")

    # 4. Standard Games (Priority 4: Lowest)
    if getattr(context.scene, "gmod_mount_css_hl2", False):
        game_root = user_path
        if (user_path / 'hl2').exists():
            game_root = user_path
        elif (user_path.parent / 'hl2').exists():
            game_root = user_path.parent

        common_parents = [game_root, game_root.parent]
        dirs_to_mount = ['hl2', 'cstrike', 'episodic', 'ep2', 'tf', 'portal', 'lostcoast']
        for p_dir in common_parents:
            for d in dirs_to_mount:
                p = p_dir / d
                if p.exists():
                    cm.scan_for_content(p)

        mount_cfg = (user_path / "garrysmod/cfg/mount.cfg") if (user_path / "garrysmod").exists() else (user_path / "cfg/mount.cfg")
        if mount_cfg.exists():
            try:
                with open(mount_cfg, 'r') as f:
                    import re
                    matches = re.findall(r'"(.*?)"\s+"(.*?)"', f.read())
                    for m_key, m_val in matches:
                        if m_key == "mountcfg":
                            continue
                        pm = TinyPath(m_val.replace('\\', '/'))
                        if pm.exists():
                            cm.scan_for_content(pm)
            except Exception:
                pass

    # Nuclear filter
    if not getattr(context.scene, "gmod_mount_css_hl2", False):
        try:
            filtered = []
            for provider in cm.children:
                p_str = str(provider.root).lower().replace('\\', '/')
                is_leaked = any(x in p_str for x in ["/hl2", "/cstrike", "/episodic", "/ep2", "/tf", "/portal"])
                is_trusted = ("merged_content" in p_str or "garrysmod" in p_str or "garrys mod" in p_str or "addons" in p_str or "steamapps" in p_str)
                if is_leaked and not is_trusted:
                    continue
                filtered.append(provider)
            cm.children = filtered
        except Exception as e:
            print(f"[GModImporter] Filter Error: {e}")

# ==============================================================================
# UI REGISTRATION HELPERS
# ==============================================================================

def register_sourceio_ui():
    if IS_EXTERNAL_SOURCEIO:
        print("[GModImporter] Using external SourceIO UI (skipping internal UI registration).")
        return

    if not SOURCEIO_AVAILABLE:
        print("[GModImporter] SourceIO not available, skipping UI registration.")
        return

    try:
        from gmod_scene_importer.SourceIO_adv.blender_bindings.bindings import register as sio_register
        sio_register()
        print("[GModImporter] Registered internal SourceIO_adv UI.")
    except Exception as e:
        print(f"[GModImporter] Failed to register internal SourceIO_adv UI: {e}")

    try:
        from gmod_scene_importer.SourceIO_adv.blender_bindings.attributes import register_props
        register_props()
    except Exception as e:
        print(f"[GModImporter] Failed to register internal SourceIO_adv props: {e}")

def unregister_sourceio_ui():
    if IS_EXTERNAL_SOURCEIO or not SOURCEIO_AVAILABLE:
        return

    try:
        from gmod_scene_importer.SourceIO_adv.blender_bindings.bindings import unregister as sio_unregister
        sio_unregister()
    except Exception:
        pass

    try:
        from gmod_scene_importer.SourceIO_adv.blender_bindings.attributes import unregister_props
        unregister_props()
    except Exception:
        pass
