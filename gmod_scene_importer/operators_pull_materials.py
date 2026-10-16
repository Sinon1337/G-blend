import bpy
import os
import glob
from .operators import ImportGModScene, SOURCEIO_AVAILABLE, get_content_manager, setup_gmod_mounts, apply_mat_fixes
from . import operators_cache

def pull_materials_for_targets(operator_instance, context, target_objs, is_weapon=False):
    if not SOURCEIO_AVAILABLE:
        operator_instance.report({'ERROR'}, "SourceIO Addon not found!")
        return {'CANCELLED'}
        
    from gmod_scene_importer.SourceIO_adv.blender_bindings.material_loader.material_loader import ShaderRegistry
    from gmod_scene_importer.SourceIO_adv.blender_bindings.material_loader.shader_base import ShaderBase
    from gmod_scene_importer.SourceIO_adv.library.source1.vmt import VMT
    from gmod_scene_importer.SourceIO_adv.library.utils.tiny_path import TinyPath
    
    # --- Resolve armatures to their child meshes ---
    resolved_targets = []
    for obj in target_objs:
        if obj.type == 'MESH':
            resolved_targets.append(obj)
        elif obj.type == 'ARMATURE':
            def collect_meshes(o):
                if o.type == 'MESH':
                    resolved_targets.append(o)
                for child in o.children:
                    collect_meshes(child)
            collect_meshes(obj)
    
    resolved_targets = list(set(resolved_targets))
    
    mode = context.scene.gmod_weapon_pull_material_mode if is_weapon else context.scene.gmod_pull_material_mode
    ShaderBase.use_bvlg(mode == 'SOURCEIO')
    
    # Setup ContentManager
    cm = get_content_manager(force_recreate=True)
    
    gmod_root = context.scene.gmod_weapon_root_path if is_weapon else context.scene.gmod_root_path
    if not gmod_root:
        gmod_root = context.scene.gmod_root_path
        
    cache_path_str = context.scene.gmod_weapon_cache_path if is_weapon else context.scene.gmod_cache_path
    if not cache_path_str:
        cache_path_str = context.scene.gmod_cache_path
        
    if gmod_root and os.path.exists(gmod_root):
        setup_gmod_mounts(context, cm, TinyPath(gmod_root), override_cache_path=cache_path_str)
    
    operators_cache.WorkshopCacheManager.rebuild_index(context, is_weapon=is_weapon)
    
    # --- Restore material slots from cache master if cleared by Skip Materials ---
    for obj in resolved_targets:
        gmod_model = obj.get("gmod_model")
        if not gmod_model and obj.parent:
            gmod_model = obj.parent.get("gmod_model")
            
        if gmod_model:
            sanitized_path = gmod_model.lower().replace('\\', '/').lstrip('/')
            import hashlib
            short_hash = hashlib.md5(sanitized_path.encode()).hexdigest()[:8]
            base = os.path.basename(sanitized_path)
            cache_name = f"CACHE:{short_hash}_{base}"[:63]
            
            master_root = bpy.data.objects.get(cache_name)
            if master_root:
                master_meshes = []
                def collect_master_meshes(o):
                    if o.type == 'MESH': master_meshes.append(o)
                    for c in o.children: collect_master_meshes(c)
                collect_master_meshes(master_root)
                
                # Find root of selected obj hierarchy
                root = obj
                while root.parent:
                    root = root.parent
                
                current_meshes = []
                def collect_current_meshes(o):
                    if o.type == 'MESH': current_meshes.append(o)
                    for c in o.children: collect_current_meshes(c)
                collect_current_meshes(root)
                
                for cur_m in current_meshes:
                    if len(cur_m.material_slots) == 0:
                        matched_master = None
                        cur_clean = cur_m.name.split(':')[-1].split('.')[-1]
                        for mast_m in master_meshes:
                            mast_clean = mast_m.name.split(':')[-1].split('.')[-1]
                            if cur_clean == mast_clean:
                                matched_master = mast_m
                                break
                        if not matched_master and len(master_meshes) == len(current_meshes):
                            idx = current_meshes.index(cur_m)
                            matched_master = master_meshes[idx]
                            
                        if matched_master:
                            for m_material in matched_master.data.materials:
                                cur_m.data.materials.append(m_material)
    
    mats_processed = set()
    count = 0
    debug_log = []
    
    for obj in resolved_targets:
        if obj.type not in {'MESH'}: continue
        if len(obj.material_slots) == 0:
            operator_instance.report({'WARNING'}, f"Object '{obj.name}' has no material slots!")
            debug_log.append(f"[{obj.name}] No material slots.")
            continue
            
        print(f"[GModPullMat] Checking object: {obj.name} (type: {obj.type}), Slots: {len(obj.material_slots)}")
        mats_to_process = []
        for mat_slot in obj.material_slots:
            if mat_slot.material and mat_slot.material not in mats_to_process:
                mats_to_process.append(mat_slot.material)
        if "skin_groups" in obj and obj["skin_groups"]:
            for skin_name, skin_mats in obj["skin_groups"].items():
                for mat in skin_mats:
                    if mat and isinstance(mat, bpy.types.Material) and mat not in mats_to_process:
                        mats_to_process.append(mat)
                        
        for mat in mats_to_process:
            if mat in mats_processed:
                continue
            mats_processed.add(mat)
            
            vmt_path_raw = mat.get("full_path") or mat.get("gmod_path")
            if not vmt_path_raw:
                import re
                base_name = re.sub(r'\.\d{3}$', '', mat.name)
                vmt_path_raw = base_name.replace('.bmp', '').replace('.vtf', '').replace('.vmt', '')
            else:
                vmt_path_raw = str(vmt_path_raw)
                
            vmt_path = vmt_path_raw.replace('\\', '/')
            if not vmt_path.startswith('materials/'):
                vmt_path = f"materials/{vmt_path}"
            if not vmt_path.endswith('.vmt'):
                vmt_path = f"{vmt_path}.vmt"
                
            vmt_f = cm.find_file(TinyPath(vmt_path))
            
            if not vmt_f:
                vmt_filename = os.path.basename(vmt_path)
                # glob returns an iterator of (TinyPath, Buffer)
                try:
                    for match_path, match_buffer in cm.glob(f"**/{vmt_filename}"):
                        vmt_f = match_buffer
                        vmt_path = str(match_path) # Update path so it prints correctly
                        print(f"    -> Found via glob: {vmt_path}")
                        break
                except Exception as e:
                    print(f"Glob search error: {e}")
                
                # 2. Try resolving exactly via cache index
                if not vmt_f:
                    abs_cached_vmt = None
                    for key, abs_path in operators_cache.ASSET_INDEX.items():
                        if key.endswith(vmt_filename):
                            abs_cached_vmt = abs_path
                            break
                            
                    if not abs_cached_vmt:
                        # Glob search in cache dir as absolute last resort
                        search_pattern = os.path.join(operators_cache.WorkshopCacheManager.get_cache_path(context), "merged_content", "**", vmt_filename)
                        matches = glob.glob(search_pattern, recursive=True)
                        if matches:
                            abs_cached_vmt = matches[0]
                            
                    if abs_cached_vmt and os.path.exists(abs_cached_vmt):
                        from gmod_scene_importer.SourceIO_adv.library.utils import FileBuffer
                        vmt_f = FileBuffer(abs_cached_vmt)
            
            if vmt_f:
                print(f"[GModPullMat] Loading nodes for {mat.name} from {vmt_path}")
                try:
                    if hasattr(vmt_f, 'seek'):
                        vmt_f.seek(0)
                    vmt = VMT(vmt_f, vmt_path, cm)
                    if 'source_loaded' in mat:
                        del mat['source_loaded']
                    mat.use_nodes = True
                    if mat.node_tree:
                        mat.node_tree.nodes.clear()
                    ShaderRegistry.source1_create_nodes(cm, mat, vmt, {})
                    apply_mat_fixes(mat)
                    count += 1
                except Exception as e:
                    print(f"[GModPullMat] Error on {mat.name}: {e}")
                    debug_log.append(f"[{mat.name}] Shader error: {e}")
            else:
                print(f"[GModPullMat] VMT not found: {vmt_path}")
                debug_log.append(f"[{mat.name}] VMT '{vmt_path}' not found!")

    if count > 0:
        operator_instance.report({'INFO'}, f"Pulled materials for {count} slots.")
    else:
        err_msg = " | ".join(debug_log) if debug_log else "Unknown error or no slots selected."
        if len(err_msg) > 200: err_msg = err_msg[:197] + "..."
        operator_instance.report({'ERROR'}, f"Failed: {err_msg}")
        
    return {'FINISHED'}

class GModPullMaterialsAllOperator(bpy.types.Operator):
    bl_idname = "gmod.pull_materials_all"
    bl_label = "Pull Materials (ALL)"
    bl_description = "Pull textures and materials for ALL models in the scene"
    bl_options = {'UNDO', 'REGISTER'}
    
    is_weapon: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    
    def execute(self, context):
        targets = [o for o in context.scene.objects if o.type == 'MESH']
        return pull_materials_for_targets(self, context, targets, self.is_weapon)

class GModPullMaterialsSelectedOperator(bpy.types.Operator):
    bl_idname = "gmod.pull_materials_selected"
    bl_label = "Pull Materials (1)"
    bl_description = "Pull textures and materials for the SELECTED model"
    bl_options = {'UNDO', 'REGISTER'}
    
    is_weapon: bpy.props.BoolProperty(default=False, options={'HIDDEN'})
    
    def execute(self, context):
        targets = []
        if context.active_object:
            def add_child(o):
                if o.type == 'MESH': targets.append(o)
                for c in o.children: add_child(c)
            add_child(context.active_object)
            if context.active_object.type == 'MESH':
                targets.append(context.active_object)
        return pull_materials_for_targets(self, context, targets, self.is_weapon)
