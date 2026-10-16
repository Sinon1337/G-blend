import bpy
import os
import shutil
import concurrent.futures
from . import gma_reader
from . import utils

# Global Index: {"models/props/foo.mdl": "C:/Cache/workshop_123/models/props/foo.mdl"}
ASSET_INDEX = {}

def extract_vmt_paths_from_mdl(mdl_data):
    try:
        if len(mdl_data) < 220: return []
        id_str = mdl_data[:4]
        if id_str != b'IDST': return []
        import struct
        version = struct.unpack('<i', mdl_data[4:8])[0]
        if version < 44 or version > 49: return []
        
        texture_count, texture_offset = struct.unpack('<ii', mdl_data[204:212])
        texturedir_count, texturedir_offset = struct.unpack('<ii', mdl_data[212:220])
        
        dirs = []
        for i in range(texturedir_count):
            off = texturedir_offset + i*4
            if off + 4 > len(mdl_data): break
            dir_offset = struct.unpack('<i', mdl_data[off : off+4])[0]
            dir_str = b""
            idx = dir_offset
            while idx < len(mdl_data) and mdl_data[idx] != 0:
                dir_str += bytes([mdl_data[idx]])
                idx += 1
            dirs.append(dir_str.decode('utf-8', errors='ignore'))
            
        textures = []
        for i in range(texture_count):
            entry_offset = texture_offset + i*64
            if entry_offset + 4 > len(mdl_data): break
            name_offset = struct.unpack('<i', mdl_data[entry_offset : entry_offset+4])[0]
            actual_offset = entry_offset + name_offset
            
            name_str = b""
            idx = actual_offset
            while idx < len(mdl_data) and mdl_data[idx] != 0:
                name_str += bytes([mdl_data[idx]])
                idx += 1
            textures.append(name_str.decode('utf-8', errors='ignore'))
            
        vmt_paths = []
        for d in dirs:
            for t in textures:
                vmt_path = f"materials/{d}{t}.vmt".lower().replace('\\', '/').replace('//', '/')
                vmt_paths.append(vmt_path)
        return vmt_paths
    except Exception as e:
        print(f"[GModCache] Failed to parse MDL header: {e}")
        return []

class WorkshopCacheManager:
    @staticmethod
    def get_cache_path(context, is_weapon=False):
        if is_weapon and context.scene.gmod_weapon_cache_path:
            return context.scene.gmod_weapon_cache_path
        path = context.scene.gmod_cache_path
        if not path:
            # Default to Blender Config/gmod_cache
            # Or User Home
            path = os.path.join(bpy.utils.resource_path('USER'), "gmod_workshop_cache")
        return path

    # Track which cache dir was last indexed to detect path changes
    _last_indexed_cache_dir = ""
    
    @staticmethod
    def rebuild_index(context, force=False, is_weapon=False):
        """Scans the Cache folder and rebuilds the global ASSET_INDEX"""
        global ASSET_INDEX
        
        cache_dir_raw = WorkshopCacheManager.get_cache_path(context, is_weapon)
        cache_dir = os.path.join(os.path.abspath(cache_dir_raw), "merged_content")
        
        # Skip rebuild only if index is populated AND the cache path hasn't changed
        if (not force 
                and len(ASSET_INDEX) > 0 
                and WorkshopCacheManager._last_indexed_cache_dir == cache_dir):
            return len(ASSET_INDEX)
            
        ASSET_INDEX.clear()
        
        print(f"[GModCache] Indexing assets in: {cache_dir}")
        
        if not os.path.exists(cache_dir):
            return 0
            
        count = 0
        # Walk ALL files in cache
        for root, dirs, files in os.walk(cache_dir):
            for file in files:
                ext = file.lower().split('.')[-1]
                if ext in {'mdl', 'vmt', 'vtf', 'wav', 'mp3'}:
                    abs_path = os.path.join(root, file)
                    
                    try:
                        rel_path = os.path.relpath(abs_path, cache_dir)
                    except ValueError:
                        continue 
                    
                    # SIMPLIFIED: Since we extract to a merged root, rel_path IS the virtual path.
                    # e.g. "models/props/file.mdl"
                    virtual_path = rel_path.replace('\\', '/').lower()
                    
                    ASSET_INDEX[virtual_path] = abs_path.replace('\\', '/')
                    count += 1
                        
                    if count <= 5:
                        print(f"[GModCache] Indexed ({count}): '{virtual_path}'")
                        
        print(f"[GModCache] Index complete. Found {count} assets.")
        WorkshopCacheManager._last_indexed_cache_dir = cache_dir
        return count

    @staticmethod
    def resolve_path(virtual_path):
        """Returns absolute path from index or None"""
        # virtual_path ex: "models/props_junk/wood_crate001a.mdl"
        # normalize
        key = virtual_path.replace('\\', '/').lower()
        return ASSET_INDEX.get(key)

class GModScanWorkshop(bpy.types.Operator):
    """Scan Workshop folder and extract new GMAs to Cache"""
    bl_idname = "gmod.scan_workshop"
    bl_label = "Scan & Cache Workshop"
    
    is_weapon: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    
    def execute(self, context):
        workshop_content = context.scene.gmod_workshop_path
        if not workshop_content or not os.path.exists(workshop_content):
            # Auto-resolve relative to GMod folder
            gmod_root = context.scene.gmod_weapon_root_path if self.is_weapon else context.scene.gmod_root_path
            if not gmod_root:
                gmod_root = context.scene.gmod_root_path
            if gmod_root:
                import pathlib
                auto_path = pathlib.Path(gmod_root).parent.parent / "workshop/content/4000"
                if auto_path.exists():
                    workshop_content = str(auto_path)
                    
        cache_dir = WorkshopCacheManager.get_cache_path(context, self.is_weapon)
        json_path = context.scene.gmod_weapon_json_path if self.is_weapon else context.scene.gmod_json_path
        
        if not workshop_content or not os.path.exists(workshop_content):
            self.report({'ERROR'}, "Workshop Content path does not exist! Please configure your GMod Folder or Workshop Content path first.")
            return {'CANCELLED'}
            
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
            
        # 1. Build Whitelist from JSON
        pending_vmts = set()
        pending_models = set()
        required_prefixes = set() # For model parts (.vtx, .vvd, etc)
        all_resolved_files = set() # For textures (.vtf)
        
        models_to_scan = []
        initial_pending_vmts = []
        discovered_vmts_all = set()
        
        import re
        vmt_texture_pattern = re.compile(r'"\$[a-z0-9_]+"[\s\t]+"([^"]+)"', re.IGNORECASE)

        if json_path and os.path.exists(json_path):
            try:
                import json
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    def collect_paths(obj):
                        if isinstance(obj, dict):
                            # 1. Models
                            m = obj.get('model') or obj.get('Model')
                            if isinstance(m, str) and m.lower().endswith('.mdl'):
                                m_low = m.lower().replace('\\', '/').strip().lstrip('/')
                                base = os.path.splitext(m_low)[0]
                                pending_models.add(m_low)
                                
                                # Auxiliary model files (.vvd, .vtx, .phy)
                                required_prefixes.add(base + ".")
                                
                                # Heuristic: Materials associated with the model path
                                # e.g. models/props/hydrant.mdl -> materials/models/props/hydrant/
                                mat_prefix = "materials/" + base
                                required_prefixes.add(mat_prefix + "/")
                                # Or materials/models/props/hydrant.vmt
                                pending_vmts.add(mat_prefix + ".vmt")

                            # 2. Materials (Explicit)
                            mats = []
                            m_ov = obj.get('material') or obj.get('Material')
                            if m_ov: mats.append(m_ov)
                            m_in = obj.get('intrinsic_materials')
                            if isinstance(m_in, list): mats.extend(m_in)

                            for mat_raw in mats:
                                if not isinstance(mat_raw, str) or not mat_raw.strip(): continue
                                im_norm = mat_raw.replace('\\', '/').lower().strip().lstrip('/')
                                if not im_norm.startswith('materials/'):
                                    vmt = f"materials/{im_norm}.vmt"
                                else:
                                    vmt = im_norm if im_norm.endswith('.vmt') else im_norm + ".vmt"
                                pending_vmts.add(vmt)

                            for v in obj.values(): collect_paths(v)
                        elif isinstance(obj, list):
                            for item in obj: collect_paths(item)
                            
                    collect_paths(data)
                
                # Copy VMTS to resolved list so we look for them too if already cached
                all_resolved_files.update(pending_vmts)
                models_to_scan = list(pending_models)
                initial_pending_vmts = list(pending_vmts)
                print(f"[GModCache] JSON Whitelist: {len(pending_models)} models, {len(pending_vmts)} materials.")
            except Exception as e:
                print(f"[GModCache] JSON Error: {e}")
                return {'CANCELLED'}
        else:
            return {'CANCELLED'}

        # 2. Collect GMAs from Workshop AND garrysmod/addons
        gma_queue = []
        if os.path.exists(workshop_content):
            for item in os.listdir(workshop_content):
                p = os.path.join(workshop_content, item)
                if os.path.isdir(p):
                    for f in os.listdir(p):
                        if f.lower().endswith((".gma", ".bin")):
                            gma_queue.append((os.path.abspath(os.path.join(p, f)), item))
                            break
                elif item.lower().endswith((".gma", ".bin")):
                     gma_queue.append((os.path.abspath(p), os.path.splitext(item)[0]))
        
        root_path = context.scene.gmod_root_path
        if root_path and os.path.exists(root_path):
            addons_dir = os.path.join(root_path, "garrysmod", "addons")
            if os.path.exists(addons_dir):
                for item in os.listdir(addons_dir):
                    p = os.path.join(addons_dir, item)
                    if item.lower().endswith(".gma"):
                        gma_queue.append((os.path.abspath(p), os.path.splitext(item)[0]))
                    elif os.path.isdir(p):
                        gma_queue.append((os.path.abspath(p), item))
            
            # 2. garrysmod/cache/workshop (In-game downloads / cache)
            cache_ws_dir = os.path.join(root_path, "garrysmod", "cache", "workshop")
            if os.path.exists(cache_ws_dir):
                for item in os.listdir(cache_ws_dir):
                    p = os.path.join(cache_ws_dir, item)
                    if item.lower().endswith((".gma", ".bin")):
                        gma_queue.append((os.path.abspath(p), os.path.splitext(item)[0]))

        # 3. Smart Surgical Matching (SMART PASS)
        merged_dir = os.path.join(cache_dir, "merged_content")
        catalog_dir = os.path.join(cache_dir, "catalogs")
        if not os.path.exists(merged_dir): os.makedirs(merged_dir)
        if not os.path.exists(catalog_dir): os.makedirs(catalog_dir)

        # The sets pending_vmts, pending_models, all_resolved_files are already initialized from JSON
        
        # Robust VMT dependency finder
        def get_vmt_dependencies(vmt_path):
            deps = set()
            try:
                with open(vmt_path, 'rb') as vf:
                    text = vf.read().decode('utf-8', errors='ignore')
                    # Flexible regex: matches $baseTexture "path", "$basetexture" path, etc.
                    # It looks for any $keyword followed by a string that looks like a path.
                    pattern = re.compile(r'["\']?\$[a-z0-9_]+["\']?[\s\t]+["\']?([^"\'\r\n\s\t\}\[\]]+)["\']?', re.IGNORECASE)
                    for item in pattern.findall(text):
                        item_low = item.lower().replace('\\', '/').strip().lstrip('/')
                        # Ignore common non-path values (numbers, booleans)
                        if any(c.isalpha() for c in item_low) and '/' in item_low:
                            # It's likely a texture path
                            t_full = item_low if item_low.endswith('.vtf') else item_low + ".vtf"
                            if not t_full.startswith('materials/'): t_full = "materials/" + t_full
                            deps.add(t_full)
                        elif item_low.endswith('.vmt'):
                            # It might be an $include
                            v_full = item_low if item_low.startswith('materials/') else "materials/" + item_low
                            deps.add(v_full)
            except: pass
            return deps

        # Check cache physical presence
        print("[GModCache] Verifying cache and resolving dependencies...")
        for root, dirs, files in os.walk(merged_dir):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), merged_dir).replace('\\', '/').lower().lstrip('/')
                if rel in pending_models: pending_models.discard(rel)
                if rel in pending_vmts:
                    pending_vmts.discard(rel)
                    all_resolved_files.update(get_vmt_dependencies(os.path.join(root, f)))

        # Build pending list
        pending_textures = set()
        for t in all_resolved_files:
            if not os.path.exists(os.path.join(merged_dir, t)):
                 # If it's a VMT we found in another VMT ($include), add to pending_vmts
                 if t.endswith('.vmt'): pending_vmts.add(t)
                 else: pending_textures.add(t)

        print(f"[GModCache] Checking for {len(pending_vmts)} materials and {len(pending_models)} models...")

        gmas_to_extract = []
        used_catalogs = set()

        # 3. Dual-Pass Surgical Matching
        # Pass 1: Extract Models and VMTs to resolve dependencies
        print("[GModCache] Pass 1: Identifying Models and Materials...")
        extract_queue_p1 = []
        for gma_path, gma_id in gma_queue:
            if not pending_vmts and not pending_models: break
            catalog_path = os.path.join(catalog_dir, f"{gma_id}.json")
            arc_files = []
            if os.path.exists(catalog_path):
                try:
                    with open(catalog_path, 'r', encoding='utf-8') as f: arc_files = json.load(f)
                except: pass
            
            is_folder = os.path.isdir(gma_path)
            if not arc_files:
                try:
                    if is_folder:
                        for r_root, r_dirs, r_files in os.walk(gma_path):
                            for f in r_files:
                                rel = os.path.relpath(os.path.join(r_root, f), gma_path).replace('\\', '/').lower().lstrip('/')
                                arc_files.append(rel)
                    else:
                        with gma_reader.GMAReader(gma_path) as reader:
                            arc_files = [e.name.lower().replace('\\', '/').lstrip('/') for e in reader.file_entries]
                    with open(catalog_path, 'w', encoding='utf-8') as f: json.dump(arc_files, f)
                except: continue

            gma_matches = set()
            found_logic = False
            for f in arc_files:
                if f in pending_models:
                    gma_matches.add(f)
                    pending_models.discard(f)
                    found_logic = True
                elif any(f.startswith(pref) for pref in required_prefixes):
                    gma_matches.add(f)
                    found_logic = True
                elif f in pending_vmts:
                    gma_matches.add(f)
                    pending_vmts.discard(f)
                    found_logic = True
            
            if found_logic:
                # Greedy Maps/Lua
                for f in arc_files:
                    if f.startswith(('maps/', 'lua/')):
                        gma_matches.add(f)
                extract_queue_p1.append((gma_path, gma_id, catalog_path, gma_matches))
                used_catalogs.add(f"{gma_id}.json")

        # Execute Pass 1 Extraction
        if extract_queue_p1:
            print(f"[GModCache] Extracting {len(extract_queue_p1)} critical addons...")
            self.do_extraction(context, extract_queue_p1, merged_dir)
            
            # --- Surgical MDL Header Scan ---
            # Scan only the models that are part of the JSON whitelist
            discovered_vmts = set()
            for model_rel_path in models_to_scan:
                mdl_abs_path = os.path.join(merged_dir, model_rel_path)
                if os.path.exists(mdl_abs_path):
                    try:
                        with open(mdl_abs_path, 'rb') as mdl_file:
                            mdl_data = mdl_file.read()
                        vmts = extract_vmt_paths_from_mdl(mdl_data)
                        discovered_vmts_all.update(vmts)
                        for vmt in vmts:
                            if not os.path.exists(os.path.join(merged_dir, vmt)):
                                discovered_vmts.add(vmt)
                    except Exception as e:
                        print(f"[GModCache] Error scanning mdl {model_rel_path}: {e}")
            
            if discovered_vmts:
                print(f"[GModCache] Pass 1.2: Extracting {len(discovered_vmts)} discovered VMT dependencies...")
                extract_queue_p12 = []
                for gma_path, gma_id in gma_queue:
                    if not discovered_vmts: break
                    catalog_path = os.path.join(catalog_dir, f"{gma_id}.json")
                    if not os.path.exists(catalog_path): continue
                    with open(catalog_path, 'r', encoding='utf-8') as f_cat:
                        arc_files = json.load(f_cat)
                    gma_matches = set()
                    for file_in_gma in arc_files:
                        if file_in_gma in discovered_vmts:
                            gma_matches.add(file_in_gma)
                            discovered_vmts.discard(file_in_gma)
                    if gma_matches:
                        extract_queue_p12.append((gma_path, gma_id, catalog_path, gma_matches))
                        used_catalogs.add(f"{gma_id}.json")
                if extract_queue_p12:
                    self.do_extraction(context, extract_queue_p12, merged_dir)

        # Intermediate Pass: Scan extracted .bsp maps for materials
        print("[GModCache] Intermediate Pass: Scanning Maps for embedded materials...")
        maps_dir = os.path.join(merged_dir, "maps")
        if os.path.exists(maps_dir):
            for map_file in os.listdir(maps_dir):
                if map_file.endswith('.bsp'):
                    bsp_path = os.path.join(maps_dir, map_file)
                    try:
                        from gmod_scene_importer.SourceIO_adv.library.source1.bsp.bsp_file import BSPFile
                        import re
                        strip_patch_coordinates = re.compile(r"_-?\d+_-?\d+_-?\d+$")
                        bsp = BSPFile(bsp_path)
                        bsp.parse()
                        
                        tex_data_lump = bsp.get_lump('LUMP_TEXDATA')
                        strings_lump = bsp.get_lump('LUMP_TEXDATA_STRING_DATA')
                        
                        if tex_data_lump and strings_lump:
                            added_count = 0
                            for texture_data in tex_data_lump.texture_data:
                                material_name = strings_lump.strings[texture_data.name_id] or "NO_NAME"
                                material_name = strip_patch_coordinates.sub("", material_name).lower().replace('\\', '/')
                                vmt_path = f"materials/{material_name}.vmt"
                                if vmt_path not in pending_vmts and vmt_path not in all_resolved_files:
                                    pending_vmts.add(vmt_path)
                                    added_count += 1
                            print(f"    -> Parsed {map_file}: Queued {added_count} map materials.")
                    except Exception as e:
                        print(f"    -> Failed to parse map {map_file}: {e}")

        # Need to re-scan GMAs if pending_vmts was updated!
        if pending_vmts:
            print(f"[GModCache] Pass 1.5: Extracting {len(pending_vmts)} map materials...")
            extract_queue_p15 = []
            for gma_path, gma_id in gma_queue:
                if not pending_vmts: break
                catalog_path = os.path.join(catalog_dir, f"{gma_id}.json")
                if not os.path.exists(catalog_path): continue
                with open(catalog_path, 'r', encoding='utf-8') as f: arc_files = json.load(f)
                
                gma_matches = set()
                for f in arc_files:
                    if f in pending_vmts:
                        gma_matches.add(f)
                        pending_vmts.discard(f)
                if gma_matches:
                    extract_queue_p15.append((gma_path, gma_id, catalog_path, gma_matches))
                    used_catalogs.add(f"{gma_id}.json")
            if extract_queue_p15:
                self.do_extraction(context, extract_queue_p15, merged_dir)

        # Pass 2: Re-scan ONLY the relevant VMTs for textures
        print("[GModCache] Pass 2: Resolving Texture Dependencies...")
        all_vmts_to_scan = set(initial_pending_vmts) | discovered_vmts_all
        for vmt_rel_path in all_vmts_to_scan:
            vmt_abs_path = os.path.join(merged_dir, vmt_rel_path)
            if os.path.exists(vmt_abs_path):
                try:
                    with open(vmt_abs_path, 'r', encoding='utf-8', errors='ignore') as vmt_file:
                        content = vmt_file.read()
                        matches = vmt_texture_pattern.findall(content)
                        for match in matches:
                            mat_low = match.lower().replace('\\', '/')
                            if not mat_low.startswith('materials/'): mat_low = 'materials/' + mat_low
                            if not mat_low.endswith('.vtf'): mat_low += '.vtf'
                            pending_textures.add(mat_low)
                except: pass
        
        extract_queue_p2 = []
        if pending_textures:
            print(f"    -> Found {len(pending_textures)} textures to extract.")
            for gma_path, gma_id in gma_queue:
                if not pending_textures: break
                
                catalog_path = os.path.join(catalog_dir, f"{gma_id}.json")
                if not os.path.exists(catalog_path): continue
                with open(catalog_path, 'r', encoding='utf-8') as f: arc_files = json.load(f)
                
                gma_matches = set()
                for f in arc_files:
                    if f in pending_textures:
                        gma_matches.add(f)
                        pending_textures.discard(f)
                if gma_matches:
                    extract_queue_p2.append((gma_path, gma_id, catalog_path, gma_matches))
                    used_catalogs.add(f"{gma_id}.json")
            
            if extract_queue_p2:
                self.do_extraction(context, extract_queue_p2, merged_dir)

        # Catalog Cleanup
        if os.path.exists(catalog_dir):
            for f in os.listdir(catalog_dir):
                if f.endswith(".json") and f not in used_catalogs:
                    try: os.remove(os.path.join(catalog_dir, f))
                    except: pass

        WorkshopCacheManager.rebuild_index(context, force=True)
        self.report({'INFO'}, f"Cache Scan Complete. {len(used_catalogs)} addons matched.")
        return {'FINISHED'}

    def do_extraction(self, context, task_list, merged_dir):
        if not task_list: return
        worker_count = getattr(context.scene, "gmod_cache_workers", 8)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            def sync_worker(task):
                g_p, w_id, c_p, files = task
                try:
                    if os.path.isdir(g_p):
                        import shutil
                        for f in files:
                            src = os.path.join(g_p, f); dst = os.path.join(merged_dir, f)
                            os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy2(src, dst)
                        return True
                    else:
                        with gma_reader.GMAReader(g_p) as r:
                            return r.extract_files(merged_dir, files) > 0
                except: return False
            list(executor.map(sync_worker, task_list))

class GModClearCache(bpy.types.Operator):
    """Delete the entire Workshop Cache folder"""
    bl_idname = "gmod.clear_cache"
    bl_label = "Clear Cache"
    bl_options = {'REGISTER', 'INTERNAL'} # Internal confirmation?
    
    is_weapon: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    
    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
        
    def execute(self, context):
        cache_dir = WorkshopCacheManager.get_cache_path(context, self.is_weapon)
        # Clean path
        cache_dir = bpy.path.abspath(cache_dir).strip().strip('"').strip("'")
        
        print(f"[GModCache] Attempting to clear folder: {cache_dir}")
        
        if os.path.exists(cache_dir):
            try:
                # Delete contents but keep root to avoid lock issues
                for item in os.listdir(cache_dir):
                    item_path = os.path.join(cache_dir, item)
                    try:
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                    except Exception as e:
                        print(f"    [!] Could not delete {item}: {e}")
                
                global ASSET_INDEX
                ASSET_INDEX.clear()
                try:
                    from gmod_scene_importer.operators_livelink import FAILED_REFINE_IDS, BONE_UPDATE_THROTTLE
                    FAILED_REFINE_IDS.clear()
                    BONE_UPDATE_THROTTLE.clear()
                    print("[GModCache] Cleared JIT Refine failures cache and bone throttle.")
                except Exception as e:
                    print(f"[GModCache] Could not import livelink caches: {e}")
                self.report({'INFO'}, "Cache Cleared.")
            except Exception as e:
                self.report({'ERROR'}, f"Failed to clear cache: {e}")
        else:
            self.report({'WARNING'}, f"Folder not found: {cache_dir}")
            
        return {'FINISHED'}

class GModDumpIndex(bpy.types.Operator):
    """Print the current Asset Index to Console for debugging"""
    bl_idname = "gmod.dump_index"
    bl_label = "Dump Index to Console"
    
    def execute(self, context):
        global ASSET_INDEX
        print("\n=== GMOD WORKSHOP ASSET INDEX ===")
        print(f"Total Entries: {len(ASSET_INDEX)}")
        count = 0
        sorted_keys = sorted(ASSET_INDEX.keys())
        for k in sorted_keys:
            v = ASSET_INDEX[k]
            print(f" '{k}' -> '{v}'")
            count += 1
            if count > 200:
                print("... (truncated 200 entries) ...")
                break
        print("=================================\n")
        self.report({'INFO'}, f"Index Dumped ({len(ASSET_INDEX)} entries). Check Console.")
        return {'FINISHED'}
