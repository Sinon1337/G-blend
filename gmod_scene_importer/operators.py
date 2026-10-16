import bpy
import json
import os
import math
import mathutils
from . import utils
from . import operators_cache

# SourceIO Imports
try:
    from gmod_scene_importer.SourceIO_adv.library.shared.content_manager import ContentManager
    from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.vpk_provider import VPKContentProvider
    from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.gma_provider import GMAContentProvider
    from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.loose_files import LooseFilesContentProvider
    from gmod_scene_importer.SourceIO_adv.library.utils import TinyPath, FileBuffer
    from gmod_scene_importer.SourceIO_adv.blender_bindings.models import import_model
    from gmod_scene_importer.SourceIO_adv.blender_bindings.utils.resource_utils import serialize_mounted_content
    from gmod_scene_importer.SourceIO_adv.blender_bindings.utils.bpy_utils import get_or_create_material

    def setup_gmod_mounts(context, cm, user_path, override_cache_path=None):
        from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.loose_files import LooseFilesContentProvider
        from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.vpk_provider import VPKContentProvider
        from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.gma_provider import GMAContentProvider
        
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
                if item.lower().endswith(".gma"):
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
                if item.lower().endswith(".gma"):
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
                    # Also try to mount content_hl2_dir.vpk if it exists
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
                    
        if workshop_path and os.path.exists(workshop_path):
            workshop_p = TinyPath(workshop_path)
            import itertools
            for gma in itertools.chain(workshop_p.glob('**/*.gma'), workshop_p.glob('**/*.bin')):
                try: cm.add_child(GMAContentProvider(gma))
                except Exception: pass

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
                    is_numbered_part = any(char.isdigit() for char in f_low.split('.')[-2][-3:]) if len(f_low.split('.')) > 1 else False
                    if "_dir.vpk" in f_low or not any(c.isdigit() for c in f_low.replace(".vpk", "")[-3:]):
                        try: cm.add_child(VPKContentProvider(TinyPath(str(gmod_base_dir / f))))
                        except Exception as e: print(f"    [!] Failed to mount {f}: {e}")

        # 4. Standard Games (Priority 4: Lowest)
        if getattr(context.scene, "gmod_mount_css_hl2", False):
            game_root = user_path
            if (user_path / 'hl2').exists(): game_root = user_path
            elif (user_path.parent / 'hl2').exists(): game_root = user_path.parent
            
            common_parents = [game_root, game_root.parent]
            dirs_to_mount = ['hl2', 'cstrike', 'episodic', 'ep2', 'tf', 'portal', 'lostcoast']
            for p_dir in common_parents:
                for d in dirs_to_mount:
                    p = p_dir / d
                    if p.exists(): cm.scan_for_content(p)
            
            mount_cfg = (user_path / "garrysmod/cfg/mount.cfg") if (user_path / "garrysmod").exists() else (user_path / "cfg/mount.cfg")
            if mount_cfg.exists():
                try:
                    with open(mount_cfg, 'r') as f:
                        import re
                        matches = re.findall(r'"(.*?)"\s+"(.*?)"', f.read())
                        for m_key, m_val in matches:
                            if m_key == "mountcfg": continue
                            pm = TinyPath(m_val.replace('\\', '/'))
                            if pm.exists(): cm.scan_for_content(pm)
                except: pass
        
        # --- NUCLEAR FILTER: Extra layer of security ---
        if not getattr(context.scene, "gmod_mount_css_hl2", False):
             try:
                 filtered = []
                 for provider in cm.children:
                     p_str = str(provider.root).lower().replace('\\', '/')
                     is_leaked = any(x in p_str for x in ["/hl2", "/cstrike", "/episodic", "/ep2", "/tf", "/portal"])
                     is_trusted = ("merged_content" in p_str or "garrysmod" in p_str or "garrys mod" in p_str or "addons" in p_str or "steamapps" in p_str)
                     if is_leaked and not is_trusted: continue
                     filtered.append(provider)
                 cm.children = filtered
             except Exception as e: print(f"[GModImporter] Filter Error: {e}")

    SOURCEIO_AVAILABLE = True
except Exception as e:
    import traceback
    print("[GModImporter] Failed to import SourceIO_adv:")
    traceback.print_exc()
    SOURCEIO_AVAILABLE = False

# Global Persistent Content Manager
_SHARED_CONTENT_MANAGER = None

def get_content_manager(force_recreate=False):
    global _SHARED_CONTENT_MANAGER
    if force_recreate or _SHARED_CONTENT_MANAGER is None:
        if SOURCEIO_AVAILABLE:
            _SHARED_CONTENT_MANAGER = ContentManager()
    return _SHARED_CONTENT_MANAGER

# Helper for Posing
def _find_armature(obj):
    if obj.type == 'ARMATURE':
        return obj
    for child in obj.children:
        found = _find_armature(child)
        if found:
            return found
    return None

def apply_skeleton_pose(armature_obj, skeleton_data, global_scale, weapon_root_obj, entity_class=""):
    if not skeleton_data:
        return
    import mathutils
    import bpy
    from gmod_scene_importer import utils
    
    # Save active object to restore later
    prev_active = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = armature_obj
    
    # Force view layer update so parented world matrix is correct
    bpy.context.view_layer.update()
    
    # Decompose armature world matrix without scale
    loc, rot, scale = armature_obj.matrix_world.decompose()
    armature_world_no_scale = mathutils.Matrix.Translation(loc) @ rot.to_matrix().to_4x4()
    armature_world_inv = armature_world_no_scale.inverted()
    
    if isinstance(skeleton_data, list):
        bones = skeleton_data
    else:
        bones = skeleton_data.get("bones", [])
    
    # Sort bones by depth (parents first)
    def bone_depth_sort(b_data):
        b_name = b_data.get("name")
        pb = find_matching_bone(armature_obj, b_name)
        if not pb:
            return 999
        d = 0
        p = pb.parent
        while p:
            d += 1
            p = p.parent
        return d

    sorted_bones = sorted(bones, key=bone_depth_sort)
    
    SKIP_BONE_PREFIXES = ()

    for bone_data in sorted_bones:
        b_name = bone_data.get("name")
        pose_bone = find_matching_bone(armature_obj, b_name)
        if not pose_bone:
            continue
            
        # Posing all bones, including root bones, to ensure perfect alignment

        # Skip player-rig bones that leak in via bone-merge
        b_lower = b_name.lower()
        if any(b_lower.startswith(p) for p in SKIP_BONE_PREFIXES):
            continue

        pos = bone_data.get("pos")
        ang = bone_data.get("ang")
        if not pos or not ang:
            continue
            
        # Read bone scale from JSON if available, otherwise default to 1.0
        scl = bone_data.get("scale", [1.0, 1.0, 1.0])
        
        # Convert local GMod bone transform relative to WeaponRoot to Blender space
        M_local_blender = utils.convert_source_transform(pos, ang, scl, global_scale)
        M_world_blender = weapon_root_obj.matrix_world @ M_local_blender
        
        target_matrix_armature = armature_world_inv @ M_world_blender
        
        # Apply the explicit bone scale to the pose matrix
        loc_gmod, rot_gmod, scale_gmod = target_matrix_armature.decompose()
        scale_matrix = mathutils.Matrix.Diagonal((scl[0], scl[1], scl[2], 1.0))
        target_matrix_clean = mathutils.Matrix.Translation(loc_gmod) @ rot_gmod.to_matrix().to_4x4() @ scale_matrix
        
        # Assign directly to pose_bone.matrix and let Blender solve it!
        pose_bone.matrix = target_matrix_clean
        
        # view_layer.update() is deferred to after the full loop to avoid N re-evaluations per tick
        
    # Single update after all bones are set — avoids N*20Hz full scene re-evaluations
    bpy.context.view_layer.update()
    bpy.context.view_layer.objects.active = prev_active

def find_matching_bone(armature_obj, bone_name):
    if not bone_name:
        return None
    b_name_lower = bone_name.lower().strip().replace("valvebiped.", "")
    for bone in armature_obj.pose.bones:
        b_name_low = bone.name.lower().replace("valvebiped.", "")
        if b_name_low == b_name_lower:
            return bone
        if b_name_low == f"attachment_{b_name_lower}":
            return bone
        if b_name_low == f"attach_{b_name_lower}":
            return bone
    return None

def apply_bone_poses(obj, bones_data, scene_origin=None, global_scale=0.0254, is_weapon=False, is_bsp_mode=False):
    if not bones_data:
        return
    if scene_origin is None:
        scene_origin = [0.0, 0.0, 0.0]

    armature_obj = _find_armature(obj)
    if not armature_obj:
        return
    if armature_obj.mode == 'POSE':
        return

    print(f"[GModPosing] Applying poses to {armature_obj.name} ({len(bones_data)} bones)...")
    import mathutils
    import bpy

    items = bones_data.items() if isinstance(bones_data, dict) else enumerate(bones_data)

    # Собираем все кости в очередь
    bone_queue = []
    for bone_key, bone_info in items:
        if not isinstance(bone_info, dict):
            continue

        pos = bone_info.get('pos')
        ang = bone_info.get('ang', bone_info.get('angle'))
        bone_name = bone_info.get('name', bone_key if isinstance(bone_key, str) else None)

        pose_bone = None
        if bone_name:
            pose_bone = armature_obj.pose.bones.get(bone_name) or find_matching_bone(armature_obj, bone_name)
        if not pose_bone and isinstance(bone_key, (int, str)) and str(bone_key).isdigit():
            idx = int(bone_key)
            if idx < len(armature_obj.pose.bones):
                pose_bone = armature_obj.pose.bones[idx]

        if pos and ang and pose_bone:
            bone_queue.append((pose_bone, pos, ang, bone_info))

    # Сортируем: сначала корневые кости, потом дочерние — иначе цепочка разъезжается
    def bone_depth(item):
        pb = item[0]
        d = 0
        b = pb.parent
        while b:
            d += 1
            b = b.parent
        return d

    bone_queue.sort(key=bone_depth)

    # Compute armature world matrix manually to bypass Blender's lazy matrix_world evaluation lag
    loc = armature_obj.location
    rot = armature_obj.rotation_euler
    armature_world_no_scale = mathutils.Matrix.Translation(loc) @ rot.to_matrix().to_4x4()
    armature_world_inv = armature_world_no_scale.inverted()



    # Check if this armature is a standard character (has Bip01 bones)
    has_bip_bones = any("bip01_" in b.name.lower() for b in armature_obj.pose.bones)

    for pose_bone, pos, ang, bone_info in bone_queue:
        if has_bip_bones and not is_weapon:
            # For characters, only apply GMod poses to core body bones (containing Bip01_).
            # Auxiliary bones (helmets, attachments, face bones, gear) should inherit their poses from their parents.
            is_body_bone = "bip01_" in pose_bone.name.lower() or pose_bone.parent is None
            if not is_body_bone:
                continue

        # World-space bone poses format (perfectly stable for all MDL types)
        rel_pos = utils.subtract_origin(pos, scene_origin)
        if is_bsp_mode:
            loc_vec = mathutils.Vector((rel_pos[0], rel_pos[1], rel_pos[2])) * global_scale
            mat_x = mathutils.Matrix.Rotation(math.radians(ang[2]), 4, 'X')
            mat_y = mathutils.Matrix.Rotation(math.radians(ang[0]), 4, 'Y')
            mat_z = mathutils.Matrix.Rotation(math.radians(ang[1]), 4, 'Z')
            rot_mat = mat_z @ mat_y @ mat_x
            target_matrix_world = mathutils.Matrix.Translation(loc_vec) @ rot_mat
        else:
            target_matrix_world = utils.convert_source_transform(rel_pos, ang, [1, 1, 1], global_scale)
            
        target_matrix_armature = armature_world_inv @ target_matrix_world
        
        loc_gmod, rot_gmod, scale_gmod = target_matrix_armature.decompose()
        
        # Support custom bone scales from GMod bone manipulation
        custom_scale = bone_info.get('scale')
        if custom_scale:
            scale_matrix = mathutils.Matrix.Diagonal((custom_scale[0], custom_scale[1], custom_scale[2], 1.0))
        else:
            scale_matrix = mathutils.Matrix.Scale(1.0, 4)
            
        target_matrix_clean = mathutils.Matrix.Translation(loc_gmod) @ rot_gmod.to_matrix().to_4x4() @ scale_matrix
        
        if pose_bone.parent is None:
            pose_bone.matrix = target_matrix_clean
        else:
            clean_name = pose_bone.name.replace("ValveBiped.", "")
            prevent_stretch = clean_name in ["Bip01_Head1", "Bip01_Neck1", "Bip01_Neck", "Bip01_Head"]
            
            if prevent_stretch:
                parent_matrix = pose_bone.parent.matrix
                child_bone = pose_bone.bone
                parent_bone = pose_bone.parent.bone
                
                rest_local_matrix = parent_bone.matrix_local.inverted() @ child_bone.matrix_local
                rest_local_translation = rest_local_matrix.to_translation()
                anatomical_loc = parent_matrix @ rest_local_translation
                
                pose_bone.matrix = mathutils.Matrix.Translation(anatomical_loc) @ rot_gmod.to_matrix().to_4x4() @ scale_matrix
            else:
                pose_bone.matrix = target_matrix_clean
                
        # view_layer.update() is deferred to once after all bones to avoid freeze with ragdolls

    # Single update after all bones are applied — avoids N*20Hz freeze with ragdolls/vehicles
    bpy.context.view_layer.update()

def apply_skin(obj, skin_index):
    """
    Apply GMod Skin index to Blender Object and its children.
    Supports SourceIO_adv's skin_groups property and standard material slots.
    """
    if skin_index is None:
        return
    try:
        skin_idx = int(skin_index)
    except:
        return

    skin_name = str(skin_idx)

    def set_skin_recursive(o):
        # 1. SourceIO skin_groups custom property style
        if "skin_groups" in o and o["skin_groups"]:
            skin_groups = o["skin_groups"]
            active_skin = o.get("active_skin", "0")
            
            # GMod might ask for a skin index that doesn't exist. Fallback to "0"
            target_skin_name = skin_name
            if target_skin_name not in skin_groups:
                target_skin_name = "0"
            
            if target_skin_name in skin_groups:
                skin_materials = skin_groups[target_skin_name]
                
                if o.data and hasattr(o.data, "materials"):
                    if o.data.users > 1:
                        o.data = o.data.copy()
                    for n in range(min(len(o.data.materials), len(skin_materials))):
                        replacement = skin_materials[n]
                        if isinstance(replacement, bpy.types.Material):
                            o.data.materials[n] = replacement
                        elif isinstance(replacement, str):
                            rep_mat = bpy.data.materials.get(replacement) or bpy.data.materials.new(name=replacement)
                            o.data.materials[n] = rep_mat
                
                o["active_skin"] = target_skin_name
                print(f"[GModSkin] Set skin of {o.name} to {target_skin_name} using skin_groups")
        
        # 2. Simple material index fallback
        elif o.type == 'MESH':
            if o.data.materials and len(o.data.materials) > skin_idx:
                o.active_material_index = skin_idx
        
        for child in o.children:
            set_skin_recursive(child)

    print(f"[GModSkin] Applying Skin {skin_idx} to {obj.name}")
    set_skin_recursive(obj)

def apply_bodygroups(obj, bodygroups_data, bodygroup_names=None):
    """
    Apply GMod Bodygroups to Blender Object hierarchy.
    """
    import re
    bg_map = {}
    if isinstance(bodygroups_data, list):
        if len(bodygroups_data) == 0 and bpy.context.scene.gmod_ignore_empty_bodygroups:
            print(f"[GModBodygroups] Empty bodygroups data for {obj.name}. Ignoring.")
            return
        for i, v in enumerate(bodygroups_data):
            bg_map[i] = int(v)
    elif isinstance(bodygroups_data, dict):
        if len(bodygroups_data) == 0 and bpy.context.scene.gmod_ignore_empty_bodygroups:
            print(f"[GModBodygroups] Empty bodygroups data for {obj.name}. Ignoring.")
            return
        for k, v in bodygroups_data.items():
            try: bg_map[int(k)] = int(v)
            except: pass

    print(f"[GModBodygroups] Extracted bg_map {bg_map} for {obj.name}")

    bg_json = obj.get("source_bodygroups_json")
    if not bg_json:
        print("[GModBodygroups] No bodygroup metadata found on master object.")
        return

    source_bgs = json.loads(bg_json)
    source_bgs_keys = list(source_bgs.keys())

    # Persist the applied bodygroup values to the object custom properties
    for bg_id, bg_val in bg_map.items():
        if bg_id < len(source_bgs_keys):
            bg_name = source_bgs_keys[bg_id]
            if bodygroup_names:
                json_name = str(bodygroup_names.get(str(bg_id), bodygroup_names.get(bg_id, "")))
                if json_name and json_name in source_bgs:
                    bg_name = json_name
            obj[f"bg_val_{bg_name}"] = bg_val
    
    # 1. Collect all child objects
    child_objects = []
    def get_children(o):
        if o != obj:
            child_objects.append(o)
        for c in o.children:
            get_children(c)
    get_children(obj)

    processed_meshes = set()

    # PASS 1: JSON Name Matching (This fixes the Plate Carrier because its custom properties are broken)
    mesh_map = {}
    for m in child_objects:
        clean_name = re.sub(r'\.\d{3}$', '', m.name).lower()
        base_name = m.name.split('.')[0].lower()
        exact_name = m.name.lower()
        
        if clean_name not in mesh_map: mesh_map[clean_name] = []
        if base_name not in mesh_map: mesh_map[base_name] = []
        if exact_name not in mesh_map: mesh_map[exact_name] = []
        
        if m not in mesh_map[clean_name]: mesh_map[clean_name].append(m)
        if m not in mesh_map[base_name]: mesh_map[base_name].append(m)
        if m not in mesh_map[exact_name]: mesh_map[exact_name].append(m)

    for bg_id, bg_name in enumerate(source_bgs.keys()):
        if bodygroup_names:
            json_name = str(bodygroup_names.get(str(bg_id), bodygroup_names.get(bg_id, "")))
            if json_name and json_name in source_bgs:
                bg_name = json_name
        
        bg_val = bg_map.get(bg_id, 0)
        options = source_bgs.get(bg_name)
        
        if options is not None:
            for opt_idx, opt_name in enumerate(options):
                if opt_name is None: continue
                opt_name_low = opt_name.lower()
                mesh_objs = mesh_map.get(opt_name_low, [])
                if not mesh_objs:
                    mesh_objs = mesh_map.get(opt_name_low.split('.')[0], [])
                    
                if mesh_objs:
                    is_active = (opt_idx == bg_val)
                    for mesh_obj in mesh_objs:
                        print(f"  -> [Pass 1] Mesh: {mesh_obj.name} (BG: {bg_name}, Idx: {opt_idx}) -> Active: {is_active}")
                        try:
                            mesh_obj.hide_viewport = not is_active
                            mesh_obj.hide_render = not is_active
                            mesh_obj.hide_set(not is_active)
                            processed_meshes.add(mesh_obj)
                        except Exception as e:
                            pass

    # PASS 2: Custom Properties Fallback (This fixes Kornet's multi-material orphaned meshes that Pass 1 missed)
    for child in child_objects:
        if child in processed_meshes: continue
        
        if 'bodygroup_name' in child and 'bodygroup_index' in child:
            bg_name = str(child['bodygroup_name'])
            bg_idx = int(child['bodygroup_index'])
            
            # If the bodygroup is not registered in the armature's metadata, skip it
            is_known = bg_name in source_bgs_keys
            if not is_known and bodygroup_names:
                for json_id_str, json_name in bodygroup_names.items():
                    if json_name == bg_name:
                        is_known = True
                        break
            if not is_known:
                continue

            active_opt = 0
            if bg_name in source_bgs_keys:
                bg_id = source_bgs_keys.index(bg_name)
                active_opt = bg_map.get(bg_id, 0)
            else:
                for json_id_str, json_name in (bodygroup_names or {}).items():
                    if json_name == bg_name and json_id_str.isdigit():
                        active_opt = bg_map.get(int(json_id_str), 0)
                        break
            
            is_active = (bg_idx == active_opt)
            print(f"  -> [Pass 2 Fallback] Mesh: {child.name} (BG: {bg_name}, Idx: {bg_idx}) -> Active: {is_active}")
            
            try:
                child.hide_viewport = not is_active
                child.hide_render = not is_active
                child.hide_set(not is_active)
                processed_meshes.add(child)
            except Exception as e:
                pass

class GModBoneMergeOperator(bpy.types.Operator):
    """Merge selected clothing/prop armatures into the active character armature"""
    bl_idname = "gmod.bone_merge"
    bl_label = "Bone Merge (Attach to Character)"
    bl_options = {'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) >= 2
        
    def execute(self, context):
        target_armature = context.active_object
        if not target_armature or target_armature.type != 'ARMATURE':
            self.report({'ERROR'}, "Active (last selected) object must be the Character Armature!")
            return {'CANCELLED'}
            
        merged_count = 0
        for obj in context.selected_objects:
            if obj == target_armature: continue
            
            if obj.type == 'ARMATURE':
                for child in list(obj.children):
                    if child.type == 'MESH':
                        for mod in child.modifiers:
                            if mod.type == 'ARMATURE':
                                mod.object = target_armature
                        
                        child_matrix = child.matrix_world.copy()
                        child.parent = target_armature
                        child.matrix_world = child_matrix
                        merged_count += 1
                        
                obj.hide_viewport = True
                obj.hide_render = True
                obj.hide_set(True)
                
            elif obj.type == 'MESH':
                for mod in obj.modifiers:
                    if mod.type == 'ARMATURE':
                        mod.object = target_armature
                
                obj_matrix = obj.matrix_world.copy()
                obj.parent = target_armature
                obj.matrix_world = obj_matrix
                merged_count += 1
                
        self.report({'INFO'}, f"Bone Merged {merged_count} meshes to {target_armature.name}")
        return {'FINISHED'}

class GModCreateCustomBodygroupOperator(bpy.types.Operator):
    """Assign selected objects as a custom bodygroup to the active Object"""
    bl_idname = "gmod.create_custom_bodygroup"
    bl_label = "Add Selected to Bodygroup"
    bl_options = {'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.active_object and len(context.selected_objects) > 1
        
    def execute(self, context):
        armature = context.active_object
        bg_name = context.scene.gmod_custom_bg_name
        
        if not bg_name:
            self.report({'ERROR'}, "Please enter a Bodygroup Name!")
            return {'CANCELLED'}
            
        import json
        bgs = {}
        if "source_bodygroups_json" in armature:
            try: bgs = json.loads(armature["source_bodygroups_json"])
            except: pass
            
        if bg_name not in bgs:
            bgs[bg_name] = ["Off"]
            
        opt_idx = len(bgs[bg_name])
        bgs[bg_name].append(f"Option {opt_idx}")
        
        for obj in context.selected_objects:
            if obj == armature: continue
            
            # Parent to main object if not already parented
            if obj.parent != armature:
                obj_matrix = obj.matrix_world.copy()
                obj.parent = armature
                if context.mode == 'POSE' and context.active_pose_bone and armature.type == 'ARMATURE':
                    obj.parent_type = 'BONE'
                    obj.parent_bone = context.active_pose_bone.name
                else:
                    obj.parent_type = 'OBJECT'
                obj.matrix_world = obj_matrix
                
            # Assign bodygroup properties
            if obj.type == 'ARMATURE':
                for child in obj.children:
                    child["bodygroup_name"] = bg_name
                    child["bodygroup_index"] = opt_idx
            else:
                obj["bodygroup_name"] = bg_name
                obj["bodygroup_index"] = opt_idx
                
        armature["source_bodygroups_json"] = json.dumps(bgs)
        
        # If there's an active category, assign the bodygroup to it
        if len(armature.gmod_bg_categories) > 0 and 0 <= armature.gmod_bg_active_category < len(armature.gmod_bg_categories):
            active_cat_name = armature.gmod_bg_categories[armature.gmod_bg_active_category].name
            bg_map = {}
            if "gmod_bg_categories_map" in armature:
                try: bg_map = json.loads(armature["gmod_bg_categories_map"])
                except: pass
            bg_map[bg_name] = active_cat_name
            armature["gmod_bg_categories_map"] = json.dumps(bg_map)
            
        # Update visibility
        prop_name = f"bg_val_{bg_name}"
        armature[prop_name] = opt_idx
            
        bodygroups_data = {}
        for bg_id, name in enumerate(bgs.keys()):
            bodygroups_data[bg_id] = armature.get(f"bg_val_{name}", 0)
            
        apply_bodygroups(armature, bodygroups_data, None)
        
        self.report({'INFO'}, f"Added option {opt_idx} to '{bg_name}'")
        return {'FINISHED'}

class GModToggleVisibilityOperator(bpy.types.Operator):
    bl_idname = "gmod.toggle_visibility"
    bl_label = "Toggle Visibility"
    bl_description = "Toggle viewport visibility (both Eye and Monitor icons)"
    bl_options = {'UNDO', 'INTERNAL'}
    
    obj_name: bpy.props.StringProperty()
    
    def execute(self, context):
        obj = bpy.data.objects.get(self.obj_name)
        if not obj: return {'CANCELLED'}
        
        target_state = not obj.hide_viewport
        
        def hide_recursive(o, state):
            o.hide_viewport = state
            if hasattr(o, "hide_set"):
                try: o.hide_set(state)
                except: pass
            for child in o.children:
                hide_recursive(child, state)
                
        hide_recursive(obj, target_state)
        return {'FINISHED'}

class GModToggleRenderVisibilityOperator(bpy.types.Operator):
    bl_idname = "gmod.toggle_render_visibility"
    bl_label = "Toggle Render Visibility"
    bl_description = "Toggle render visibility (Camera icon)"
    bl_options = {'UNDO', 'INTERNAL'}
    
    obj_name: bpy.props.StringProperty()
    
    def execute(self, context):
        obj = bpy.data.objects.get(self.obj_name)
        if not obj: return {'CANCELLED'}
        
        target_state = not obj.hide_render
        
        def hide_render_recursive(o, state):
            o.hide_render = state
            for child in o.children:
                hide_render_recursive(child, state)
                
        hide_render_recursive(obj, target_state)
        return {'FINISHED'}

class GModSelectUncategorized(bpy.types.Operator):
    """Show Uncategorized bodygroups"""
    bl_idname = "gmod.select_uncategorized"
    bl_label = "Show Uncategorized"
    
    def execute(self, context):
        obj = context.active_object
        if obj:
            # Set index out of valid range to trigger "Uncategorized" display
            obj.gmod_bg_active_category = -1
        return {'FINISHED'}

class GModAddCategoryOperator(bpy.types.Operator):
    bl_idname = "gmod.add_category"
    bl_label = "Add Category"
    bl_options = {'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if obj:
            new_cat = obj.gmod_bg_categories.add()
            new_cat.name = f"Category {len(obj.gmod_bg_categories)}"
            obj.gmod_bg_active_category = len(obj.gmod_bg_categories) - 1
        return {'FINISHED'}

class GModRemoveCategoryOperator(bpy.types.Operator):
    bl_idname = "gmod.remove_category"
    bl_label = "Remove Category"
    bl_options = {'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if obj and len(obj.gmod_bg_categories) > 0:
            idx = obj.gmod_bg_active_category
            cat_name = obj.gmod_bg_categories[idx].name
            obj.gmod_bg_categories.remove(idx)
            if obj.gmod_bg_active_category >= len(obj.gmod_bg_categories):
                obj.gmod_bg_active_category = max(0, len(obj.gmod_bg_categories) - 1)
            
            # Remove from map
            import json
            if "gmod_bg_categories_map" in obj:
                try: 
                    bg_map = json.loads(obj["gmod_bg_categories_map"])
                    bg_map = {k: v for k, v in bg_map.items() if v != cat_name}
                    obj["gmod_bg_categories_map"] = json.dumps(bg_map)
                except: pass
        return {'FINISHED'}

def get_categories(self, context):
    obj = context.active_object
    items = [("Uncategorized", "Uncategorized", "")]
    if obj:
        for c in obj.gmod_bg_categories:
            items.append((c.name, c.name, ""))
    return items

class GModAssignCategoryOperator(bpy.types.Operator):
    bl_idname = "gmod.assign_category"
    bl_label = "Assign Category"
    bl_options = {'UNDO'}
    
    bg_name: bpy.props.StringProperty()
    target_cat: bpy.props.EnumProperty(items=get_categories)
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
        
    def execute(self, context):
        obj = context.active_object
        import json
        bg_map = {}
        if "gmod_bg_categories_map" in obj:
            try: bg_map = json.loads(obj["gmod_bg_categories_map"])
            except: pass
            
        if self.target_cat == "Uncategorized":
            if self.bg_name in bg_map:
                del bg_map[self.bg_name]
        else:
            bg_map[self.bg_name] = self.target_cat
            
        obj["gmod_bg_categories_map"] = json.dumps(bg_map)
        return {'FINISHED'}

def get_available_bodygroups_for_move(self, context):
    items = [("NEW", "Create New Bodygroup", "")]
    obj = context.active_object
    if obj and "source_bodygroups_json" in obj:
        import json
        try:
            bgs = json.loads(obj["source_bodygroups_json"])
            for bg in bgs.keys():
                items.append((bg, f"Existing: {bg}", ""))
        except: pass
    return items

class GModMoveToBodygroupOperator(bpy.types.Operator):
    bl_idname = "gmod.move_to_bodygroup"
    bl_label = "Add to Bodygroup"
    bl_description = "Move this attached object into a Bodygroup collection"
    bl_options = {'UNDO', 'REGISTER'}
    
    obj_name: bpy.props.StringProperty()
    target_bg: bpy.props.EnumProperty(name="Target", items=get_available_bodygroups_for_move)
    new_bg_name: bpy.props.StringProperty(name="New Name", default="Custom Accessory")
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
        
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "target_bg")
        if self.target_bg == "NEW":
            layout.prop(self, "new_bg_name")
            
    def execute(self, context):
        armature = context.active_object
        target_obj = bpy.data.objects.get(self.obj_name)
        if not target_obj or not armature: return {'CANCELLED'}
        
        bg_name = self.new_bg_name if self.target_bg == "NEW" else self.target_bg
        if not bg_name: bg_name = "Custom Accessory"
        
        import json
        bgs = {}
        if "source_bodygroups_json" in armature:
            try: bgs = json.loads(armature["source_bodygroups_json"])
            except: pass
            
        if bg_name not in bgs:
            bgs[bg_name] = ["Off"]
            
        opt_idx = len(bgs[bg_name])
        bgs[bg_name].append(self.obj_name)
        
        if target_obj.type == 'ARMATURE':
            for child in target_obj.children:
                child["bodygroup_name"] = bg_name
                child["bodygroup_index"] = opt_idx
        else:
            target_obj["bodygroup_name"] = bg_name
            target_obj["bodygroup_index"] = opt_idx
            
        armature["source_bodygroups_json"] = json.dumps(bgs)
        
        if len(armature.gmod_bg_categories) > 0 and 0 <= armature.gmod_bg_active_category < len(armature.gmod_bg_categories):
            active_cat_name = armature.gmod_bg_categories[armature.gmod_bg_active_category].name
            bg_map = {}
            if "gmod_bg_categories_map" in armature:
                try: bg_map = json.loads(armature["gmod_bg_categories_map"])
                except: pass
            bg_map[bg_name] = active_cat_name
            armature["gmod_bg_categories_map"] = json.dumps(bg_map)
            
        prop_name = f"bg_val_{bg_name}"
        armature[prop_name] = opt_idx
        
        bodygroups_data = {}
        for bg_id, name in enumerate(bgs.keys()):
            bodygroups_data[bg_id] = armature.get(f"bg_val_{name}", 0)
            
        apply_bodygroups(armature, bodygroups_data, None)
        
        self.report({'INFO'}, f"Added {self.obj_name} to Bodygroup '{bg_name}'")
        return {'FINISHED'}

class GModDeleteCustomBGOps(bpy.types.Operator):
    bl_idname = "gmod.delete_custom_bg"
    bl_label = "Delete Custom Bodygroup"
    bl_options = {'UNDO'}
    
    bg_name: bpy.props.StringProperty()
    
    def execute(self, context):
        obj = context.active_object
        import json
        
        # 1. Remove from JSON
        if "source_bodygroups_json" in obj:
            try:
                bgs = json.loads(obj["source_bodygroups_json"])
                if self.bg_name in bgs:
                    del bgs[self.bg_name]
                    obj["source_bodygroups_json"] = json.dumps(bgs)
            except: pass
            
        # 2. Delete child objects matching this bodygroup name
        objects_to_delete = []
        def find_objects(o):
            if o.get('bodygroup_name') == self.bg_name:
                objects_to_delete.append(o)
            for c in o.children:
                find_objects(c)
        find_objects(obj)
        
        for m in objects_to_delete:
            bpy.data.objects.remove(m, do_unlink=True)
            
        # 3. Clean up property
        prop_name = f"bg_val_{self.bg_name}"
        if prop_name in obj:
            del obj[prop_name]
            
        return {'FINISHED'}

class GModInitBodygroupsOperator(bpy.types.Operator):
    """Initialize bodygroups for a manually imported SourceIO model"""
    bl_idname = "gmod.init_bodygroups"
    bl_label = "Initialize Bodygroups"
    bl_options = {'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj: return {'CANCELLED'}
        
        child_objects = []
        def get_children(o):
            if o != obj:
                child_objects.append(o)
            for c in o.children:
                get_children(c)
        get_children(obj)
        
        bgs = {}
        import json
        if "source_bodygroups_json" in obj:
            try: bgs = json.loads(obj["source_bodygroups_json"])
            except: pass
            
        for child in child_objects:
            if 'bodygroup_name' in child and 'bodygroup_index' in child:
                bg_name = str(child['bodygroup_name'])
                bg_idx = int(child['bodygroup_index'])
                if bg_name not in bgs:
                    bgs[bg_name] = []
                while len(bgs[bg_name]) <= bg_idx:
                    bgs[bg_name].append(f"Option {len(bgs[bg_name])}")
                    
        import json
        obj["source_bodygroups_json"] = json.dumps(bgs)
        
        # Determine the initial values based on current visibility of meshes
        initial_vals = {}
        for child in child_objects:
            if 'bodygroup_name' in child and 'bodygroup_index' in child:
                bg_name = str(child['bodygroup_name'])
                bg_idx = int(child['bodygroup_index'])
                if not child.hide_viewport:
                    initial_vals[bg_name] = bg_idx
        
        for bg_id, name in enumerate(bgs.keys()):
            prop_name = f"bg_val_{name}"
            if prop_name not in obj:
                obj[prop_name] = initial_vals.get(name, 0)
            
        return {'FINISHED'}

class GModSetBodygroupOperator(bpy.types.Operator):
    """Set a specific bodygroup on the selected object"""
    bl_idname = "gmod.set_bodygroup"
    bl_label = "Set Bodygroup"
    bl_options = {'UNDO'}
    
    bg_name: bpy.props.StringProperty()
    bg_val: bpy.props.IntProperty()
    max_val: bpy.props.IntProperty()
    obj_name: bpy.props.StringProperty(default="")
    
    def execute(self, context):
        if self.obj_name != "":
            obj = bpy.data.objects.get(self.obj_name)
        else:
            obj = context.active_object
        if not obj: return {'CANCELLED'}
        
        val = self.bg_val
        if val < 0: val = self.max_val
        if val > self.max_val: val = 0
        
        obj[f"bg_val_{self.bg_name}"] = val
        
        import json
        bgs = json.loads(obj.get("source_bodygroups_json", "{}"))
        
        bodygroups_data = {}
        for bg_id, name in enumerate(bgs.keys()):
            bodygroups_data[bg_id] = obj.get(f"bg_val_{name}", 0)
            
        apply_bodygroups(obj, bodygroups_data, None)
        
        return {'FINISHED'}

class GModSetSkinOperator(bpy.types.Operator):
    """Set a specific skin on the selected object"""
    bl_idname = "gmod.set_skin"
    bl_label = "Set Skin"
    bl_options = {'UNDO'}
    
    skin_val: bpy.props.IntProperty()
    max_val: bpy.props.IntProperty()
    obj_name: bpy.props.StringProperty(default="")
    
    def execute(self, context):
        if self.obj_name != "":
            obj = bpy.data.objects.get(self.obj_name)
        else:
            obj = context.active_object
        if not obj: return {'CANCELLED'}
        
        val = self.skin_val
        if val < 0: val = self.max_val
        if val > self.max_val: val = 0
        
        obj["active_skin"] = str(val)
        apply_skin(obj, val)
        
        # Propagate skin change to all attached objects
        attached = []
        root = obj
        while root.parent:
            root = root.parent
            
        def collect_attached(o):
            for child in o.children:
                if child.type == 'ARMATURE' and child != obj:
                    attached.append(child)
                else:
                    collect_attached(child)
        collect_attached(root)
        
        for att in attached:
            att_skin_groups = att.get("skin_groups", None)
            if not att_skin_groups:
                for child in att.children:
                    if child.type == 'MESH' and "skin_groups" in child and child["skin_groups"]:
                        att_skin_groups = child["skin_groups"]
                        break
            if att_skin_groups:
                att_max_val = len(att_skin_groups) - 1
                att_val = val
                if att_val > att_max_val:
                    att_val = att_max_val
                if att_val < 0:
                    att_val = 0
                att["active_skin"] = str(att_val)
                apply_skin(att, att_val)
        
        return {'FINISHED'}

class GModMountResource(bpy.types.Operator):
    """Mount a specific GMod Resource (.gma or folder) manually"""
    bl_idname = "gmod.mount_resource"
    bl_label = "Mount Resource"
    bl_options = {'REGISTER'}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.gma", options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        cm = get_content_manager()
        if not cm:
            self.report({'ERROR'}, "SourceIO not initialized.")
            return {'CANCELLED'}
            
        path = self.filepath
        if not os.path.exists(path):
            self.report({'ERROR'}, "Path does not exist")
            return {'CANCELLED'}
            
        print(f"[GModImporter] Mounting: {path}")
        cm.scan_for_content(TinyPath(path))
        self.report({'INFO'}, f"Mounted: {os.path.basename(path)}")
        return {'FINISHED'}

class ImportGModScene(bpy.types.Operator):
    """Import GMod Scene from JSON"""
    bl_idname = "gmod.import_scene"
    bl_label = "Import Scene"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    gmod_root: bpy.props.StringProperty(subtype="DIR_PATH", name="GMod Root")
    clear_scene: bpy.props.BoolProperty(name="Clear Existing Scene", default=True, description="Delete old GMod objects before import")

    # Helper for recursive deletion
    def delete_hierarchy(self, obj):
        if obj is None: return
        
        # Check validity (safeguard against double-deletion)
        try:
            name = obj.name
        except ReferenceError:
            return # Object already deleted by a parent's deletion
            
        try:
            # Snapshot children (create a list, as deleting changes the iterator)
            children = [c for c in obj.children]
            for child in children:
                self.delete_hierarchy(child)
            
            # Remove from collections to be safe
            for col in obj.users_collection:
                col.objects.unlink(obj)
                
            # Remove data block if possible (Mesh/Curve/etc)
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            
            # Optional: Clean up data block to prevent orphans
            if data and data.users == 0:
                if isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.Curve):
                    bpy.data.curves.remove(data)
                    
        except ReferenceError:
            pass # Already gone
        except Exception as e:
            print(f"Failed to delete {name}: {e}")

    def clear_import_cache(self):
        """Remove cached master models so they are re-imported with current settings."""
        to_remove = [obj for obj in bpy.data.objects if obj.name.startswith("CACHE:")]
        for obj in to_remove:
            try:
                self.delete_hierarchy(obj)
            except:
                pass
        cache_col = bpy.data.collections.get("IMPORT_CACHE")
        if cache_col:
            for obj in list(cache_col.objects):
                try:
                    self.delete_hierarchy(obj)
                except:
                    pass

    def instance_hierarchy(self, obj, mapping):
        if not obj: return None
        new_obj = obj.copy()
        # Ensure instance is visible
        new_obj.hide_viewport = False
        new_obj.hide_render = False
        mapping[obj] = new_obj
        
        # Duplicate mesh data to prevent material slot / skin conflicts
        if new_obj.type == 'MESH' and new_obj.data:
            new_obj.data = new_obj.data.copy()
            # Allow direct viewport selection of all meshes
            pass
        
        for child in obj.children:
            new_child = self.instance_hierarchy(child, mapping)
            new_child.parent = new_obj
            new_child.matrix_parent_inverse = child.matrix_parent_inverse.copy()
            
        return new_obj

    def get_or_load_master(self, context, cm, model_path_str):
        if not model_path_str: return None
        
        # Sanitize name - ALWAYS strip leading slash for index consistency
        sanitized_path = model_path_str.lower().replace('\\', '/').lstrip('/')
        
        # Safe 63-char name with hash to avoid collisions
        import hashlib
        short_hash = hashlib.md5(sanitized_path.encode()).hexdigest()[:8]
        base = os.path.basename(sanitized_path)
        cache_name = f"CACHE:{short_hash}_{base}"[:63]
        
        # 1. Existing Master?
        if cache_name in bpy.data.objects:
            return bpy.data.objects[cache_name]
            
        # 2. Find File
        file_buffer = None
        model_path = TinyPath(sanitized_path)
        
        # Try Cache
        cached_abs_path = operators_cache.WorkshopCacheManager.resolve_path(sanitized_path)
        if cached_abs_path and os.path.exists(cached_abs_path):
             print(f"[GModImporter] Loading {sanitized_path} FROM CACHE: {cached_abs_path}")
             file_buffer = FileBuffer(cached_abs_path, 'rb')
             
             # JIT Mount: add root (parent of 'models/') as LooseFilesContentProvider directly
             path_parts = os.path.normpath(cached_abs_path).split(os.sep)
             addon_root = None
             for i in range(len(path_parts)-1, -1, -1):
                 if path_parts[i].lower() in ('models', 'materials', 'sound'):
                     addon_root = os.sep.join(path_parts[:i])
                     break
             if addon_root and os.path.isdir(addon_root):
                 try:
                     from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.loose_files import LooseFilesContentProvider
                     cm.add_child(LooseFilesContentProvider(TinyPath(addon_root)))
                     print(f"[GModImporter] JIT mounted (direct): {addon_root}")
                 except Exception as _jit_e:
                     print(f"[GModImporter] JIT mount failed: {_jit_e}")
                     try: cm.scan_for_content(TinyPath(addon_root))
                     except: pass
                  
        else:
             print(f"[GModImporter] Cache MISS for {sanitized_path}. Trying SourceIO Mounts...")
             file_buffer = cm.find_file(model_path)
             if file_buffer:
                 print(f"[GModImporter] Loading {sanitized_path} FROM SOURCEIO PROVIDER")
             
        if not file_buffer:
             print(f"[GModImporter] ERROR: Could not find model file: {sanitized_path}")
             return None
             
        # Import
        try:
            class MockOptions:
                bodygroup_grouping = True
                import_textures = not context.scene.gmod_skip_materials
                skin_decals = False
                import_physics = False
                write_qc = False
                load_refpose = False
                import_animations = False
                create_flex_drivers = False
                use_bvlg = (context.scene.gmod_pull_material_mode == 'SOURCEIO')
                scale = context.scene.gmod_global_scale
            
            container = import_model(model_path, file_buffer, cm, MockOptions())
        except Exception as e:
            import traceback as _get_tb
            tb_str = _get_tb.format_exc()
            print(tb_str)
            print(f"[GModImporter] import_model() FAILED: {type(e).__name__}: {e}")
            try:
                with open("Z:/gmod_balabanovo/gmod_importer_debug.log", "a", encoding="utf-8") as _log_f:
                    _log_f.write(f"\n--- import_model() FAILED for {sanitized_path} ---\n{tb_str}")
            except Exception as _log_e:
                print(f"Failed to write log file: {_log_e}")
            return None

        # ---- import_model succeeded, wire up the result ----
        if not container or not container.objects:
            msg = f"[GModImporter] import_model returned empty container for {sanitized_path}"
            print(msg)
            try:
                with open("Z:/gmod_balabanovo/gmod_importer_debug.log", "a", encoding="utf-8") as _log_f:
                    _log_f.write(f"\n--- EMPTY CONTAINER FOR {sanitized_path} ---\n{msg}\n")
            except: pass
            return None

        new_obj = container.objects[0]
        while new_obj.parent:
            new_obj = new_obj.parent

        new_obj.name = cache_name
        new_obj.location = (0, 0, 0)
        new_obj.rotation_euler = (0, 0, 0)
        new_obj.scale = (1, 1, 1)

        cache_col = utils.get_or_create_collection("IMPORT_CACHE")
        self.link_hierarchy_recursive(new_obj, cache_col)

        # ---- BODYGROUP PROCESSING (fully isolated — errors here never kill the import) ----
        try:
            if hasattr(container, "bodygroups"):
                bg_dict = {}
                for bg_name, meshes in container.bodygroups.items():
                    bg_dict[bg_name] = [m.name if m else None for m in meshes]

                # Supplement via raw MDL struct parse to catch any body_parts SourceIO missed
                try:
                    import struct as _struct
                    raw_bytes = None
                    if cached_abs_path and os.path.exists(cached_abs_path):
                        with open(cached_abs_path, 'rb') as _f:
                            raw_bytes = _f.read()
                    if raw_bytes and len(raw_bytes) > 0xF0:
                        _num_bp = _struct.unpack_from('<I', raw_bytes, 0xE8)[0]
                        _bp_idx = _struct.unpack_from('<I', raw_bytes, 0xEC)[0]
                        print(f"[GModImporter] MDL raw: numbodyparts={_num_bp} bodypartindex={_bp_idx}")
                        for _i in range(min(_num_bp, 64)):
                            _bp_start = _bp_idx + _i * 16
                            if _bp_start + 16 > len(raw_bytes):
                                break
                            _name_rel  = _struct.unpack_from('<i', raw_bytes, _bp_start)[0]
                            _name_abs  = _bp_start + _name_rel
                            _nummodels = _struct.unpack_from('<I', raw_bytes, _bp_start + 4)[0]
                            _bp_name = ''
                            if 0 < _name_abs < len(raw_bytes):
                                try:
                                    _end = raw_bytes.index(b'\x00', _name_abs)
                                    _bp_name = raw_bytes[_name_abs:_end].decode('latin-1')
                                except Exception:
                                    _bp_name = f'BodyPart_{_i}'
                            if not _bp_name:
                                _bp_name = f'BodyPart_{_i}'
                            if _bp_name not in bg_dict:
                                bg_dict[_bp_name] = [None] * max(_nummodels, 1)
                            else:
                                existing = bg_dict[_bp_name]
                                if len(existing) < _nummodels:
                                    bg_dict[_bp_name] = existing + [None] * (_nummodels - len(existing))
                except Exception as _raw_e:
                    print(f"[GModImporter] MDL raw supplement failed (non-fatal): {_raw_e}")

                new_obj["source_bodygroups_json"] = json.dumps(bg_dict)

                if bg_dict:
                    src_cat = new_obj.gmod_bg_categories.add()
                    src_cat.name = "Source Bodygroups"
                    new_obj.gmod_bg_active_category = 0 if len(new_obj.gmod_bg_categories) > 0 else -1
                    cat_map = {}
                    for bg_name in list(bg_dict.keys()):
                        cat_map[bg_name] = "Source Bodygroups"
                        # Guard: custom property key must be a safe string
                        safe_key = f"bg_val_{bg_name}"
                        try:
                            new_obj[safe_key] = 0
                        except Exception as _kv_e:
                            print(f"[GModImporter] Cannot set prop '{safe_key}': {_kv_e} (skipping)")
                    new_obj["gmod_bg_categories_map"] = json.dumps(cat_map)
        except Exception as _bg_e:
            import traceback as _bg_tb
            print(f"[GModImporter] Bodygroup processing FAILED (non-fatal): {_bg_e}")
            _bg_tb.print_exc()
            # Don't return None — model is imported, just without bodygroup metadata

        # ---- Hide master in IMPORT_CACHE ----
        def hide_recursive(o):
            o.hide_viewport = True
            o.hide_render = True
            try: o.hide_set(True)
            except: pass
            for c in o.children:
                hide_recursive(c)
        hide_recursive(new_obj)

        return new_obj

    def execute(self, context):
        if not SOURCEIO_AVAILABLE:
            self.report({'ERROR'}, "SourceIO Addon not found or not fully loaded!")
            return {'CANCELLED'}

        cm = get_content_manager(force_recreate=True)
        
        if self.clear_scene:
            print("[GModImporter] Doing Aggressive Scene Clear...")
            objects_to_destroy = set()
            def collect_tree(obj):
                objects_to_destroy.add(obj)
                for child in obj.children: collect_tree(child)
            for col_name in ["GMOD_SCENE", "PROPS", "CHARACTERS", "STATIC", "PLACEHOLDERS", "CAMERAS", "IMPORT_CACHE"]:
                col = bpy.data.collections.get(col_name)
                if col:
                    for obj in col.objects: collect_tree(obj)
            for obj in bpy.data.objects:
                if "Entity_" in obj.name or "GMOD_" in obj.name or obj.get('gmod_model'): collect_tree(obj)
            for obj in list(objects_to_destroy):
                try:
                    if obj.name: self.delete_hierarchy(obj) 
                except: pass
            for col_name in ["GMOD_SCENE", "PROPS", "CHARACTERS", "STATIC", "PLACEHOLDERS", "CAMERAS", "IMPORT_CACHE"]:
                col = bpy.data.collections.get(col_name)
                if col:
                    try: bpy.data.collections.remove(col)
                    except: pass
            print(f"[GModImporter] Scene Cleared.")

        # Always rebuild model cache so scale/import fixes apply without stale masters
        self.clear_import_cache()

        if not os.path.exists(self.filepath):
            self.report({'ERROR'}, "File not found")
            return {'CANCELLED'}

        # Load JSON
        encodings_to_try = ['utf-8', 'utf-8-sig', 'cp1252', 'cp1251', 'latin-1']
        data = None
        for enc in encodings_to_try:
            try:
                with open(self.filepath, 'r', encoding=enc) as f:
                    data = json.load(f)
                    break
            except: continue
        if data is None:
            self.report({'ERROR'}, "Failed to decode JSON.")
            return {'CANCELLED'}

        # Content Manager Setup
        operators_cache.WorkshopCacheManager.rebuild_index(context)
        
        user_path = TinyPath(self.gmod_root) # Default from UI
        
        # Auto-detect from JSON path
        import pathlib
        json_path = pathlib.Path(self.filepath)
        for p in json_path.parents:
            if p.name.lower() == "garrysmod":
                user_path = TinyPath(str(p.parent)) # The root folder containing 'garrysmod'
                print(f"[GModImporter] Auto-detected GMod root from JSON path: {user_path}")
                break

        game_root = user_path
        if (user_path / 'hl2').exists():
            game_root = user_path
        elif (user_path.parent / 'hl2').exists():
            game_root = user_path.parent

        # Save user_path so Retry/Browse can use same mounts
        context.scene['gmod_last_root'] = str(user_path)
        
        setup_gmod_mounts(context, cm, user_path)
        print("--------------------------------------\n")
        self.process_scene(data, context, cm)
        
        # --- POST-PROCESS: Kill Phong Globally ---
        self.kill_phong_globally()
        
        return {'FINISHED'}

    def kill_phong_globally(self):
        """Global post-process: Force correct node connections (BSDF -> Surface) for all materials"""
        print("[GModImporter] Running global material enforcement...")
        count = 0
        for mat in bpy.data.materials:
            if mat.node_tree:
                apply_mat_fixes(mat)
                count += 1
        print(f"[GModImporter] Global Fix: Processed {count} materials.")

    def process_scene(self, data, context, cm):
        main_col = utils.get_or_create_collection("GMOD_SCENE")
        props_col = utils.get_or_create_collection("PROPS", main_col)
        chars_col = utils.get_or_create_collection("CHARACTERS", main_col)
        static_col = utils.get_or_create_collection("STATIC", main_col)
        placeholders_col = utils.get_or_create_collection("PLACEHOLDERS", main_col)
        
        global_scale = context.scene.gmod_global_scale
        
        # Support 'objects' (AdvDupe2), 'entities' (live export), or 'props' (legacy)
        entity_list = data.get('objects', data.get('entities', data.get('props', [])))
        scene_origin = utils.compute_scene_origin(data, entity_list)
        context.scene["gmod_scene_origin"] = list(scene_origin)
        if any(abs(v) > 1e-6 for v in scene_origin):
            print(f"[GModImporter] Recentering scene (source offset): {scene_origin}")
        
        if 'cameras' in data:
            cam_col = utils.get_or_create_collection("CAMERAS", main_col)
            for cam_data in data['cameras']:
                 try:
                     self.create_camera(cam_data, cam_col, None, scene_origin, global_scale)
                 except: pass

        # Check if there is any physical camera prop in the entities
        has_camera_prop = False
        for obj_data in entity_list:
            model_path_raw = obj_data.get('model', '')
            model_path_str = model_path_raw.replace('\\', '/').lower().lstrip('/')
            if model_path_str in ["models/dav0r/camera.mdl", "models/maxofs2d/camera.mdl"]:
                has_camera_prop = True
                break

        if data.get('camera') and 'cameras' not in data:
            if not has_camera_prop or not context.scene.gmod_replace_cameras:
                cam_col = utils.get_or_create_collection("CAMERAS", main_col)
                try:
                    self.create_camera(data['camera'], cam_col, None, scene_origin, global_scale)
                except:
                    pass

        imported_objects = {} # Map ID -> Blender Object
        
        for idx, obj_data in enumerate(entity_list):
            obj_id = obj_data.get('id', idx)
            model_path_raw = obj_data.get('model', 'models/error.mdl')
            # Normalize path immediately (strip leading slash)
            model_path_str = model_path_raw.replace('\\', '/').lower().lstrip('/')

            if utils.should_skip_entity(obj_data):
                print(f"[GModImporter] Skipping prop_effect: {obj_data.get('name', model_path_str)}")
                continue
            
            # --- CAMERA REPLACEMENT LOGIC ---
            if model_path_str in ["models/dav0r/camera.mdl", "models/maxofs2d/camera.mdl"] and context.scene.gmod_replace_cameras:
                print(f"[GModImporter] Found GMod Camera Prop, replacing with Blender Camera entity...")
                cam_col = utils.get_or_create_collection("CAMERAS", main_col)
                # Create actual blender camera
                cam_data = bpy.data.cameras.new(f"GMod_Camera_{idx}")
                cam_obj = bpy.data.objects.new(f"GMod_Camera_{idx}", cam_data)
                cam_col.objects.link(cam_obj)
                
                # Position
                pos = utils.subtract_origin(
                    obj_data.get('position', obj_data.get('pos', [0, 0, 0])),
                    scene_origin,
                )
                cam_obj.location = utils.source_to_blender_location(pos, global_scale)
                
                # Field of View (FOV)
                fov = obj_data.get('fov', obj_data.get('FieldOfView', 75))
                # GMod FOV is Horizontal, Blender is usually Horizontal too by default
                cam_data.angle = math.radians(fov)
                if fov > 170: cam_data.lens = 1 # Extreme wide
                
                # Rotation (GMod angles to Blender)
                ang = obj_data.get('rotation_euler', obj_data.get('ang', [0,0,0]))
                cam_obj.rotation_mode = 'XYZ'
                
                # USER FIX: Correct GMod angles mapping to Blender Camera
                # Pitch(0), Yaw(1), Roll(2) -> X=Pitch+90, Y=Roll, Z=Yaw
                cam_obj.rotation_euler = (
                    math.radians(ang[0] + 90), 
                    math.radians(ang[2]), 
                    math.radians(ang[1])
                )
                
                # Set as active if it's the first one
                if idx == 0 and not context.scene.camera:
                    context.scene.camera = cam_obj
                
                imported_objects[obj_id] = cam_obj
                continue

            class_name = obj_data.get('class', 'prop_physics')
            
            # --- INSTANCING LOGIC ---
            # 1. Get Master (Cached or New Import)
            master_obj = self.get_or_load_master(context, cm, model_path_str)
            
            new_obj = None
            is_placeholder = False
            mapping = {}
            
            if master_obj:
                # 2. Instance
                new_obj = self.instance_hierarchy(master_obj, mapping)
                if not new_obj: # Robustness check
                    print(f"[GModImporter] Instancing failed for {model_path_str}")
                else:
                    # Build old_name -> new_name mapping for bodygroup JSON remap
                    name_remap = {old_o.name: new_o.name for old_o, new_o in mapping.items()}
                    
                    # Remap armature modifiers and constraints
                    for old_o, new_o in mapping.items():
                        if new_o.type == 'MESH':
                            for mod in new_o.modifiers:
                                if mod.type == 'ARMATURE' and mod.object in mapping:
                                    print(f"[GModImporter] Remapping armature modifier on {new_o.name}: {mod.object.name} -> {mapping[mod.object].name}")
                                    mod.object = mapping[mod.object]
                        
                        # Remap object constraints
                        for cons in new_o.constraints:
                            if hasattr(cons, "target") and cons.target in mapping:
                                cons.target = mapping[cons.target]
                        
                        # Remap bone constraints
                        if new_o.type == 'ARMATURE' and new_o.pose:
                            for bone in new_o.pose.bones:
                                for cons in bone.constraints:
                                    if hasattr(cons, "target") and cons.target in mapping:
                                        cons.target = mapping[cons.target]
                    
                    # Remap source_bodygroups_json: update mesh names from master -> instance
                    if "source_bodygroups_json" in new_obj:
                        try:
                            import json
                            bgs = json.loads(new_obj["source_bodygroups_json"])
                            new_bgs = {}
                            for bg_name, mesh_names in bgs.items():
                                new_bgs[bg_name] = [name_remap.get(n, n) if n else None for n in mesh_names]
                            new_obj["source_bodygroups_json"] = json.dumps(new_bgs)
                            # Also init bg_val_ props for UI sliders
                            for bg_name in new_bgs.keys():
                                prop_key = f"bg_val_{bg_name}"
                                if prop_key not in new_obj:
                                    new_obj[prop_key] = 0
                            
                            # Copy categories from master to instance
                            new_obj.gmod_bg_categories.clear()
                            for cat in master_obj.gmod_bg_categories:
                                new_cat = new_obj.gmod_bg_categories.add()
                                new_cat.name = cat.name
                            new_obj.gmod_bg_active_category = 0 if len(new_obj.gmod_bg_categories) > 0 else -1
                            
                            # Copy category map from master (bodygroup-name -> category-name mapping stays same)
                            if "gmod_bg_categories_map" in master_obj:
                                new_obj["gmod_bg_categories_map"] = master_obj["gmod_bg_categories_map"]
                                
                        except Exception as e:
                            print(f"[GModImporter] Bodygroup JSON remap failed: {e}")
            else:
               # 3. Placeholder
               is_placeholder = True
               print(f"[GModImporter] Model Missing: {model_path_str}")
               
               # Use cache for placeholder too!
               ph_master = self.get_placeholder_template()
               if ph_master:
                   new_obj = self.instance_hierarchy(ph_master, mapping)
               else:
                   # Fallback (Should not happen)
                   new_obj = self.duplicate_hierarchy_recursive(self.get_placeholder_template(), is_placeholder)
               
               # Store missing model path on placeholder for easy identification
               if new_obj:
                   new_obj["missing_model"] = model_path_str

            if not new_obj:
                print(f"CRITICAL: Failed to create object for {model_path_str}")
                continue

            # Force Visible (Instance logic handles it, but just in case)
            new_obj.hide_viewport = False
            new_obj.hide_render = False
            
            # Apply Transforms
            g_pos = utils.subtract_origin(utils.extract_entity_pos(obj_data), scene_origin)
            g_ang = utils.extract_entity_ang(obj_data)
            g_scl = utils.extract_entity_scale(obj_data)
            
            # Store full GMod Data for Retry (Bones, Bodygroups)
            import json
            try:
                new_obj['gmod_data'] = json.dumps(obj_data)
            except Exception as e:
                print(f"Failed to store gmod_data: {e}")

            # NAME COLLISION PREVENTION (JIT Cleanup)
            target_name = obj_data.get('name') or f"Entity_{obj_id}_{idx}"
            
            existing_obj = bpy.data.objects.get(target_name)
            if existing_obj:
                try:
                    name_check = existing_obj.name
                    print(f"[GModImporter] JIT Collision: Removing existing {target_name}...")
                    self.delete_hierarchy(existing_obj)
                except:
                    pass
                
            new_obj.name = target_name


            # 3. Collection Organization (DO THIS FIRST before setting transforms)
            target_collection = static_col
            if class_name in ['prop_physics', 'prop_dynamic']:
                target_collection = props_col
            elif class_name.startswith('npc_') or class_name in ['prop_ragdoll', 'class_c_model']:
                target_collection = chars_col
            
            if is_placeholder:
                target_collection = placeholders_col
            
            self.link_hierarchy_recursive(new_obj, target_collection)
            
            # Apply Transforms (AFTER linking so matrix_world is valid)
            bpy.context.view_layer.update()
            tf_matrix = utils.convert_source_transform(g_pos, g_ang, g_scl, global_scale)
            # Root objects have no parent -> set matrix_world directly (same as local, but guaranteed correct)
            new_obj.matrix_world = tf_matrix

            
            # Store GMod Model Path custom property
            new_obj['gmod_model'] = str(model_path_str)
            new_obj['gmod_id'] = obj_id # Store ID for visual debugging
            
            # --- MATERIAL UPDATES (Skin & Submaterials) ---
            
            submaterials = obj_data.get('submaterials')
            intrinsic_materials = obj_data.get('intrinsic_materials', [])
            if submaterials and not is_placeholder:
                # Convert list format to dict if needed
                if isinstance(submaterials, list):
                    submats_dict = {}
                    for idx, path in enumerate(submaterials):
                        if path and path.strip():
                            submats_dict[str(idx)] = path
                    submaterials = submats_dict
                    
                if isinstance(submaterials, dict) and len(submaterials) > 0:
                    print(f"[GModImporter] Applying Submaterials ({len(submaterials)} slots)")
                
                # Setup BVLG for ShaderRegistry
                try:
                    from gmod_scene_importer.SourceIO_adv.blender_bindings.material_loader.material_loader import ShaderRegistry
                    from gmod_scene_importer.SourceIO_adv.blender_bindings.material_loader.shader_base import ShaderBase
                    from gmod_scene_importer.SourceIO_adv.library.source1.vmt import VMT
                    from gmod_scene_importer.SourceIO_adv.library.utils.tiny_path import TinyPath
                    
                    ShaderBase.use_bvlg(context.scene.gmod_pull_material_mode == 'SOURCEIO')
                    
                    # 1. Load/create all submaterial objects first
                    submats_mapping = {}
                    for slot_idx_str, target_path in submaterials.items():
                        try:
                            slot_idx = int(slot_idx_str)
                        except:
                            continue
                            
                        n_name = os.path.basename(target_path).replace('.vmt', '')
                        mat = bpy.data.materials.get(n_name) or bpy.data.materials.new(name=n_name)
                        mat.use_nodes = True
                        mat["gmod_path"] = target_path
                        
                        # Load Nodes if empty
                        if SOURCEIO_AVAILABLE and (not mat.node_tree or len(mat.node_tree.nodes) < 5):
                            vmt_path = target_path.lower().replace('\\', '/').strip()
                            if not vmt_path.startswith('materials/'): vmt_path = "materials/" + vmt_path
                            if not vmt_path.endswith('.vmt'): vmt_path += ".vmt"
                            
                            vmt_f = cm.find_file(TinyPath(vmt_path))
                            if not vmt_f:
                                abs_cached_vmt = operators_cache.WorkshopCacheManager.resolve_path(vmt_path)
                                if abs_cached_vmt and os.path.exists(abs_cached_vmt):
                                    vmt_f = FileBuffer(abs_cached_vmt)

                            if vmt_f:
                                print(f"[GModImporter] Loading nodes for {n_name} from {vmt_path}")
                                try:
                                    vmt = VMT(vmt_f)
                                    ShaderRegistry.source1_create_nodes(cm, mat, vmt, {})
                                except Exception as e:
                                    print(f"[GModImporter] Material Node Error ({n_name}): {e}")
                                    
                        submats_mapping[slot_idx] = mat

                    # 2. Find skin_groups metadata
                    skin_groups = None
                    if "skin_groups" in new_obj:
                        skin_groups = new_obj["skin_groups"]
                    else:
                        for child in new_obj.children:
                            if "skin_groups" in child:
                                skin_groups = child["skin_groups"]
                                break

                    def clean_material_name(name):
                        import re
                        name = name.replace('\\', '/').split('/')[-1]
                        if name.lower().endswith('.vmt'): name = name[:-4]
                        name = re.sub(r'\.\d{3}$', '', name)
                        return name.lower().strip()

                    # 3. Apply to meshes recursively
                    def apply_submats_recursive(o):
                        if o.type == 'MESH':
                            # Make the mesh unique so modifying its materials does not affect other objects sharing the same model
                            if o.data and o.data.users > 1:
                                o.data = o.data.copy()
                            
                            applied = False
                            
                            # A. Try skin_groups name-based replacement
                            if skin_groups and len(skin_groups) > 0:
                                active_skin = new_obj.get("active_skin", o.get("active_skin", "0"))
                                if active_skin not in skin_groups:
                                    active_skin = "0"
                                current_materials = skin_groups.get(active_skin, list(skin_groups.values())[0])
                                
                                if o.data and hasattr(o.data, "materials"):
                                    for slot_idx, sub_mat in submats_mapping.items():
                                        if slot_idx < len(current_materials):
                                            orig_mat = current_materials[slot_idx]
                                            orig_mat_name = orig_mat.name if hasattr(orig_mat, "name") else str(orig_mat)
                                            clean_orig = clean_material_name(orig_mat_name)
                                            
                                            # Replace this material name in the mesh's materials list
                                            for n, mat in enumerate(o.data.materials):
                                                if mat and clean_material_name(mat.name) == clean_orig:
                                                    o.data.materials[n] = sub_mat
                                                    applied = True
                                                    print(f"[GModImporter] Replaced {orig_mat_name} (clean: {clean_orig}) in {o.name} slot {n} with submaterial {sub_mat.name}")
                            
                            # B. Try intrinsic_materials name-based replacement if skin_groups wasn't used or failed
                            if not applied and intrinsic_materials:
                                if o.data and hasattr(o.data, "materials"):
                                    for slot_idx, sub_mat in submats_mapping.items():
                                        if slot_idx < len(intrinsic_materials):
                                            orig_mat_name = intrinsic_materials[slot_idx]
                                            clean_orig = clean_material_name(orig_mat_name)
                                            
                                            # Replace this material name in the mesh's materials list
                                            for n, mat in enumerate(o.data.materials):
                                                if mat and clean_material_name(mat.name) == clean_orig:
                                                    o.data.materials[n] = sub_mat
                                                    applied = True
                                                    print(f"[GModImporter] Remapped via intrinsic_materials: {orig_mat_name} (clean: {clean_orig}) in {o.name} slot {n} with submaterial {sub_mat.name}")

                            # C. Fallback: direct index mapping
                            if not applied:
                                for slot_idx, sub_mat in submats_mapping.items():
                                    if slot_idx < len(o.material_slots):
                                        o.material_slots[slot_idx].material = sub_mat
                                        applied = True
                                        print(f"[GModImporter] Fallback: Replaced slot {slot_idx} in {o.name} with submaterial {sub_mat.name}")
                                        
                        for child in o.children:
                            apply_submats_recursive(child)
                            
                    apply_submats_recursive(new_obj)
                except Exception as e:
                    print(f"Failed to load submaterials: {e}")

            # --- Toolgun material override on initial import ---
            material_override = obj_data.get('material')
            if material_override and material_override != "null" and not is_placeholder:
                try:
                    mat_name = os.path.basename(material_override).replace('.vmt', '')
                    target_mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(name=mat_name)
                    target_mat.use_nodes = True
                    target_mat["gmod_path"] = material_override
                    
                    # Setup VMT loader to populate texture nodes
                    from gmod_scene_importer.SourceIO_adv.blender_bindings.material_loader.material_loader import ShaderRegistry
                    from gmod_scene_importer.SourceIO_adv.blender_bindings.material_loader.shader_base import ShaderBase
                    from gmod_scene_importer.SourceIO_adv.library.source1.vmt import VMT
                    from gmod_scene_importer.SourceIO_adv.library.utils.tiny_path import TinyPath
                    
                    ShaderBase.use_bvlg(context.scene.gmod_pull_material_mode == 'SOURCEIO')
                    
                    # Resolve VMT path
                    vmt_path = material_override.lower().replace('\\', '/').strip()
                    if not vmt_path.startswith('materials/'): vmt_path = "materials/" + vmt_path
                    if not vmt_path.endswith('.vmt'): vmt_path += ".vmt"
                    
                    vmt_f = cm.find_file(TinyPath(vmt_path))
                    if not vmt_f:
                        abs_cached_vmt = operators_cache.WorkshopCacheManager.resolve_path(vmt_path)
                        if abs_cached_vmt and os.path.exists(abs_cached_vmt):
                            vmt_f = FileBuffer(abs_cached_vmt)
                            
                    if vmt_f:
                        try:
                            vmt = VMT(vmt_f)
                            ShaderRegistry.source1_create_nodes(cm, target_mat, vmt, {})
                            print(f"[GModImporter] Loaded VMT textures for override: {material_override}")
                        except Exception as vmt_e:
                            print(f"[GModImporter] Error loading override VMT nodes ({material_override}): {vmt_e}")
                    
                    # Apply this material override to all slots on all child meshes
                    def apply_override_recursive(o):
                        if o.type == 'MESH':
                            if o.data and o.data.users > 1:
                                o.data = o.data.copy()
                            for i in range(len(o.data.materials)):
                                o.data.materials[i] = target_mat
                        for child in o.children:
                            apply_override_recursive(child)
                    
                    apply_override_recursive(new_obj)
                    print(f"[GModImporter] Applied material override: {material_override} to {new_obj.name}")
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print(f"Failed to apply material override: {e}")

            bg_data = obj_data.get('bodygroups')
            bg_names = obj_data.get('bodygroup_names')
            if bg_data:
                apply_bodygroups(new_obj, bg_data, bg_names)
            
            skin_idx = obj_data.get('skin')
            if skin_idx is not None:
                apply_skin(new_obj, skin_idx)

            bones_data = obj_data.get('bones')
            if bones_data and not obj_data.get('is_effect', False):
                apply_bone_poses(new_obj, bones_data, scene_origin, global_scale)
            
            # --- Store for Linking ---
            imported_objects[obj_id] = new_obj

            # --- Light Spawning for GMod Lamps and Lights ---
            if class_name in ("gmod_lamp", "gmod_softlamp", "gmod_light") and new_obj:
                try:

                    light_col = utils.get_or_create_collection("LIGHTS", main_col)
                    if class_name in ("gmod_lamp", "gmod_softlamp"):
                        light_data = bpy.data.lights.new(name=f"GMod_Lamp_Light_{idx}", type='SPOT')
                        light_data.spot_size = math.radians(obj_data.get('lamp_fov', 90))
                        light_data.spot_blend = 0.15
                        light_data.energy = obj_data.get('lamp_brightness', 1.0) * 150.0
                        col = obj_data.get('lamp_color', [255, 255, 255, 255])
                        light_data.color = (col[0]/255.0, col[1]/255.0, col[2]/255.0)
                    else:
                        light_data = bpy.data.lights.new(name=f"GMod_Light_Light_{idx}", type='POINT')
                        light_data.energy = obj_data.get('light_brightness', 1.0) * 50.0
                        col = obj_data.get('light_color', [255, 255, 255, 255])
                        light_data.color = (col[0]/255.0, col[1]/255.0, col[2]/255.0)
                        light_data.shadow_soft_size = obj_data.get('light_size', 256) * global_scale * 0.1

                    light_obj = bpy.data.objects.new(name=f"{new_obj.name}_light", object_data=light_data)
                    light_col.objects.link(light_obj)

                    # Parent the light to the prop model
                    light_obj.parent = new_obj
                    is_bone_parented = False
                    if new_obj.type == 'ARMATURE' and new_obj.data.bones:
                        bone_name = new_obj.data.bones[0].name
                        light_obj.parent_type = 'BONE'
                        light_obj.parent_bone = bone_name
                        light_obj.matrix_parent_inverse = mathutils.Matrix.Identity(4)
                        is_bone_parented = True
                        print(f"[GModImporter] Parented light {light_obj.name} to bone {bone_name} with identity parent inverse")
                    light_obj.location = (0.0, 0.0, 0.0)

                    # Do NOT hide the light/lamp itself so the props are visible in the scene.
                    # Instead, disable shadow casting on the mesh so it doesn't block the light.
                    new_obj.hide_viewport = False
                    new_obj.hide_render = False
                    
                    if hasattr(new_obj, "visible_shadow"):
                        new_obj.visible_shadow = False
                        
                    def disable_shadow_recursive(o):
                        if o != light_obj:
                            if hasattr(o, "visible_shadow"):
                                o.visible_shadow = False
                            o.hide_viewport = False
                            o.hide_render = False
                        for child in o.children:
                            disable_shadow_recursive(child)
                            
                    for child in new_obj.children:
                        disable_shadow_recursive(child)

                    if class_name in ("gmod_lamp", "gmod_softlamp"):
                        # Rotate the light locally so Spot points forward relative to the GMod model
                        # (If bone parented to flashlight, we correct for the 90-degree bone rotation offset)
                        light_obj.rotation_mode = 'XYZ'
                        if is_bone_parented and (bone_name == 'flashlight' or "torch.mdl" in model_path_str):
                            light_obj.rotation_euler = (math.radians(90), 0, math.radians(180))
                        else:
                            light_obj.rotation_euler = (math.radians(90), 0, 0)

                except Exception as _light_e:
                    print(f"[GModImporter] Failed to spawn Blender light for {class_name}: {_light_e}")

        # --- PASS 2: PARENTING (Bonemerge) ---
        print(f"[GModImporter] Linking Pass... ({len(imported_objects)} objects)")
        for idx, obj_data in enumerate(entity_list):
            child_id = obj_data.get('id', idx)
            parent_id = obj_data.get('parent_id')
            
            if child_id is not None and parent_id is not None:
                child_obj = imported_objects.get(child_id)
                parent_obj = imported_objects.get(parent_id)
                
                if child_obj and parent_obj:
                    # Check if parenting would create a dependency cycle
                    is_cycle = False
                    curr = parent_obj
                    while curr:
                        if curr == child_obj:
                            is_cycle = True
                            break
                        curr = curr.parent
                        
                    if child_obj != parent_obj and not is_cycle:
                        # Parent and Keep Transform
                        mat_world = child_obj.matrix_world.copy()
                        child_obj.parent = parent_obj
                        child_obj.matrix_parent_inverse = parent_obj.matrix_world.inverted()
                        child_obj.matrix_world = mat_world
                    print(f"  -> Linked {child_obj.name} to {parent_obj.name}")

                    # Bone Merge logic if flagged
                    is_bonemerge = obj_data.get('is_bonemerge', False)
                    if is_bonemerge:
                        def find_armature(obj):
                            if not obj:
                                return None
                            if obj.type == 'ARMATURE':
                                return obj
                            if obj.parent and obj.parent.type == 'ARMATURE':
                                return obj.parent
                            for child in obj.children:
                                if child.type == 'ARMATURE':
                                    return child
                            return None
                            
                        child_arm = find_armature(child_obj)
                        parent_arm = find_armature(parent_obj)
                        
                        if child_arm and parent_arm and child_arm != parent_arm:
                            print(f"[GModImporter] Bone Merging armature {child_arm.name} -> {parent_arm.name}")
                            parent_bone_names = set(parent_arm.data.bones.keys())
                            for pb in child_arm.pose.bones:
                                if pb.name in parent_bone_names:
                                    c_name = f"BoneMerge_{pb.name}"
                                    constraint = pb.constraints.get(c_name)
                                    if not constraint:
                                        # check if any other copy transforms constraint already exists on same target
                                        existing = [c for c in pb.constraints if c.type == 'COPY_TRANSFORMS' and c.target == parent_arm and c.subtarget == pb.name]
                                        if not existing:
                                            constraint = pb.constraints.new('COPY_TRANSFORMS')
                                            constraint.name = c_name
                                            constraint.target = parent_arm
                                            constraint.subtarget = pb.name
                                            constraint.target_space = 'WORLD'
                                            constraint.owner_space = 'WORLD'
                    
                    # Merge Bodygroups from Bonemerged Entities
                    if "source_bodygroups_json" in child_obj and "source_bodygroups_json" in parent_obj:
                        try:
                            import json
                            c_bgs = json.loads(child_obj["source_bodygroups_json"])
                            p_bgs = json.loads(parent_obj["source_bodygroups_json"])
                            merged = False
                            for bg_name, options in c_bgs.items():
                                if bg_name not in p_bgs:
                                    p_bgs[bg_name] = options
                                    merged = True
                            if merged:
                                parent_obj["source_bodygroups_json"] = json.dumps(p_bgs)
                                
                            # Transfer active values
                            for bg_name in c_bgs.keys():
                                prop = f"bg_val_{bg_name}"
                                if prop in child_obj:
                                    parent_obj[prop] = child_obj[prop]
                        except Exception as e:
                            print(f"[GModImporter] Bodygroup merge failed: {e}")

        # --- PASS 3: GLOBAL ROTATION FIX ---
        # The user has a scene rotation settings (0, -90, 90, 180)
        try:
            global_rot_deg = float(context.scene.gmod_import_rotation)
            if global_rot_deg != 0:
                print(f"[GModImporter] Applying Global Scene Rotation: {global_rot_deg} degrees")
                # Create a temporary empty at origin, child everything to it, rotate, then unparent
                world_fix = bpy.data.objects.new("GMOD_WORLD_ROTATOR", None)
                main_col.objects.link(world_fix)
                
                # Move everything into it (including sub-collections)
                bpy.context.view_layer.update()
                parented_names = []
                for obj in main_col.all_objects:
                    if obj != world_fix and obj.parent is None:
                        obj.parent = world_fix
                        parented_names.append(obj.name)
                print(f"[GModImporter] Parented to world_fix: {parented_names}")
                
                # Rotate
                world_fix.rotation_euler.rotate_axis('Z', math.radians(global_rot_deg))
                
                # Apply transformation and unparent
                bpy.context.view_layer.update()
                for obj in list(world_fix.children):
                    mw = obj.matrix_world.copy()
                    obj.parent = None
                    obj.matrix_world = mw
                
                # Clean up
                bpy.data.objects.remove(world_fix)
        except Exception as e:
            print(f"[GModImporter] Global rotation error: {e}")

        # --- PASS 4: RE-APPLY BODYGROUPS ---
        # Ensure all bodygroups (including merged ones) are correctly hidden/shown
        for obj_id, new_obj in imported_objects.items():
            if new_obj.parent is None and "source_bodygroups_json" in new_obj:
                try:
                    import json
                    bgs = json.loads(new_obj["source_bodygroups_json"])
                    bg_data = {}
                    for bg_id, bg_name in enumerate(bgs.keys()):
                        bg_data[bg_id] = new_obj.get(f"bg_val_{bg_name}", 0)
                    apply_bodygroups(new_obj, bg_data)
                except Exception as e:
                    print(f"[GModImporter] Pass 4 Bodygroup Error: {e}")

        self.report({'INFO'}, "GMod Scene Imported Successfully!")
        print("[GModImporter] Scene Import Completed.")
        return {'FINISHED'}

    def duplicate_hierarchy_recursive(self, obj, is_placeholder):
        new_obj = obj.copy()
        if obj.data:
            new_obj.data = obj.data.copy()
            
        for child in obj.children:
            new_child = self.duplicate_hierarchy_recursive(child, is_placeholder)
            new_child.parent = new_obj
            new_child.matrix_parent_inverse = child.matrix_parent_inverse
            
        return new_obj

    def link_hierarchy_recursive(self, obj, collection):
        # Link if not linked
        if obj.name not in collection.objects:
            collection.objects.link(obj)
        # Unlink from others (like cache) - cleanup
        for col in obj.users_collection:
            if col != collection:
                col.objects.unlink(obj)
        
        for child in obj.children:
            self.link_hierarchy_recursive(child, collection)

    def get_placeholder_template(self):
        # Cache check
        if "GMOD_PLACEHOLDER_CACHE" in bpy.data.objects:
            return bpy.data.objects["GMOD_PLACEHOLDER_CACHE"]

        # 1. Cube Mesh (Standard Placeholder)
        mesh = bpy.data.meshes.new("GMOD_PLACEHOLDER_MESH")
        # Simple cube vertices
        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(mesh)
        bm.free()
        
        obj = bpy.data.objects.new("GMOD_PLACEHOLDER_CACHE", mesh)
        
        # Material: Magenta (Missing Texture)
        mat = bpy.data.materials.new(name="Source_Missing_Texture")
        mat.use_nodes = True
        mat.diffuse_color = (1.0, 0.0, 1.0, 1.0) # MAGENTA FOR VIEWPORT SOLID MODE!
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        bsdf = nodes.get("Principled BSDF")
        if bsdf:
             # Magenta (1, 0, 1)
            bsdf.inputs['Base Color'].default_value = (1.0, 0.0, 1.0, 1.0)
            bsdf.inputs['Roughness'].default_value = 0.5
            
        obj.data.materials.append(mat)
        
        cache_col = utils.get_or_create_collection("IMPORT_CACHE")
        cache_col.objects.link(obj)
        obj.hide_viewport = True
        obj.hide_render = True
        
        return obj

def apply_mat_fixes(mat):
    """FORCE connect VertexLit/Shader nodes to Material Output Surface and fix alpha blend modes"""
    if not mat or not mat.node_tree: return
    
    def disable_phong_in_nodetree(node_tree):
        if not node_tree: return
        for node in node_tree.nodes:
            if node.type == 'GROUP' and node.node_tree:
                disable_phong_in_nodetree(node.node_tree)
            if hasattr(node, 'inputs'):
                for inp in node.inputs:
                    if inp.name == "$phong [bool]":
                        try: inp.default_value = 0.0
                        except: pass
    disable_phong_in_nodetree(mat.node_tree)
    
    # Fix Alpha Blend sorting issues in Eevee/viewport
    if mat.blend_method == 'BLEND':
        mat.blend_method = 'HASHED'
        print(f"[GModImporter] Fixed blend method for {mat.name} to HASHED")
        
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    
    mo = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
    if not mo: return

    # Find the main shader node (VertexLitGeneric, etc)
    main_shader = None
    for n in nodes:
        if n.type == 'GROUP' and n.node_tree:
            # Check BOTH node name and node_tree name for "vertexlit"
            n_name = n.name.lower()
            t_name = n.node_tree.name.lower()
            if any(x in n_name or x in t_name for x in ["vertexlit", "character", "eye", "lightmap", "detail"]):
                # Absolute priority to VertexLit
                if "vertexlit" in n_name or "vertexlit" in t_name:
                    main_shader = n
                    break
                main_shader = n
    
    # Fallback: look for BSDF/Shader output
    if not main_shader:
        for n in nodes:
            if any(x in n.outputs for x in ["BSDF", "Shader"]):
                main_shader = n
                break

    if main_shader:
        out_sock = main_shader.outputs.get('BSDF') or main_shader.outputs.get('Shader') or main_shader.outputs[0]
        in_sock = mo.inputs.get('Surface')
        if out_sock and in_sock:
            for l in list(in_sock.links): links.remove(l)
            links.new(out_sock, in_sock)
            
        # Reset Phong/Detail Blend messy values safely
        for inp in main_shader.inputs:
            il = inp.name.lower()
            if any(x in il for x in ["phong", "specular", "detailblendfactor", "detailblendmode"]):
                try:
                    if hasattr(inp, "default_value"):
                        # Handle different types (Color/Vector vs Float)
                        if isinstance(inp.default_value, (float, int)):
                            inp.default_value = 0
                        else:
                            # It's a sequence (Color/Vector)
                            try:
                                if len(inp.default_value) == 4: inp.default_value = (0, 0, 0, 1)
                                else: inp.default_value = [0] * len(inp.default_value)
                            except: pass
                except: pass

    def create_camera(self, data, collection, parent, scene_origin=None, global_scale=0.0254):
        if scene_origin is None:
            scene_origin = [0.0, 0.0, 0.0]
        cam_data = bpy.data.cameras.new(name="GMod_Camera")
        cam_obj = bpy.data.objects.new("GMod_Camera", cam_data)
        collection.objects.link(cam_obj)

        cam_obj.parent = parent

        pos = utils.subtract_origin(data.get('position', [0, 0, 0]), scene_origin)
        cam_obj.location = utils.source_to_blender_location(pos, global_scale)

        rot_deg = data.get('rotation_euler', [0, 0, 0])
        pitch, yaw, roll = utils._normalize_ang(rot_deg)
        cam_obj.rotation_euler = (
            math.radians(pitch + 90), 
            math.radians(roll), 
            math.radians(yaw)
        )

        fov = data.get('fov', 75)
        fov_rad = math.radians(fov)
        cam_data.sensor_width = 36.0
        cam_data.lens = (cam_data.sensor_width / 2.0) / math.tan(fov_rad / 2.0)

        bpy.context.scene.camera = cam_obj

class GModFixMaterials(bpy.types.Operator):
    """Force fix connections for ALL materials in the scene"""
    bl_idname = "gmod.fix_materials"
    bl_label = "Fix All Materials"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        count = 0
        for mat in bpy.data.materials:
            if mat.node_tree:
                apply_mat_fixes(mat)
                count += 1
        self.report({'INFO'}, f"Fixed connections for {count} materials.")
        return {'FINISHED'}

    def _fix_shader_node(self, node):
        # Deprecated: Logic moved into apply_mat_fixes for atomicity
        pass

class GModRefineFromCache(bpy.types.Operator):
    """Force re-import selected objects using files found in the Workshop Cache (e.g. for HD Replacements)"""
    bl_idname = "gmod.refine_from_cache"
    bl_label = "Refresh from Cache"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Ensure index is up to date
        operators_cache.WorkshopCacheManager.rebuild_index(context)
        
        cm = get_content_manager(force_recreate=True)
        
        gmod_root = context.scene.gmod_root_path
        cache_path_str = context.scene.gmod_cache_path
        if not cache_path_str:
            cache_path_str = os.path.join(bpy.utils.resource_path('USER'), "gmod_workshop_cache")
            
        if gmod_root and os.path.isdir(gmod_root):
            setup_gmod_mounts(context, cm, TinyPath(gmod_root), override_cache_path=cache_path_str)
        
        # Mode: Selection or All?
        selection = [o for o in context.selected_objects if o.get('gmod_model')]
        
        if selection:
            targets = selection
            self.report({'INFO'}, f"Refining {len(targets)} selected objects...")
        else:
            # Auto-select ALL Gmod objects in scene
            targets = [o for o in context.scene.objects if o.get('gmod_model')]
            self.report({'INFO'}, f"No selection. Scanning all {len(targets)} GMod objects...")
        
        if not targets:
            self.report({'WARNING'}, "No GMod objects found to refine.")
            return {'CANCELLED'}
            
        success_count = 0
        
        for old_obj in targets:
            old_name = old_obj.name # Cache name before potential deletion
            model_path_str = old_obj['gmod_model']
            
            # Search in Content Manager (VPKs, mounted games, extracted addons)
            file_buffer = cm.find_file(TinyPath(model_path_str))
            
            if not file_buffer:
                # Fallback: check Workshop Cache directly
                cached_path = operators_cache.WorkshopCacheManager.resolve_path(model_path_str)
                if cached_path and os.path.exists(cached_path):
                    # JIT Mount (Safety)
                    path_parts = os.path.normpath(cached_path).split(os.sep)
                    addon_root = None
                    for i in range(len(path_parts)-1, -1, -1):
                        if path_parts[i].lower() in ('models', 'materials', 'sound'):
                            addon_root = os.sep.join(path_parts[:i])
                            break
                    if addon_root and os.path.isdir(addon_root):
                        cm.scan_for_content(TinyPath(addon_root))
                    file_buffer = FileBuffer(cached_path, 'rb')
            
            if not file_buffer:
                print(f"[GModRefine] Cache MISS and game mount MISS for {old_name} ({model_path_str})")
                continue
                
            print(f"[GModRefine] Upgrading {old_name} -> {model_path_str}")
            
            # Import New
            try:
                class MockOptions:
                    bodygroup_grouping = True
                    import_textures = not context.scene.gmod_skip_materials
                    skin_decals = False
                    import_physics = False
                    write_qc = False
                    load_refpose = False
                    import_animations = False
                    create_flex_drivers = False
                    use_bvlg = (context.scene.gmod_pull_material_mode == 'SOURCEIO')
                    scale = utils.SCALE_FACTOR
                
                container = import_model(TinyPath(model_path_str), file_buffer, cm, MockOptions())
                
                if container.objects:
                    new_root = container.objects[0]
                    while new_root.parent: new_root = new_root.parent
                    
                    # Align Transform
                    new_root.matrix_world = old_obj.matrix_world.copy()
                    
                    # Rotation Correction (Standard +90Z for Mesh children)
                    for child in new_root.children:
                        child.rotation_euler.rotate_axis('Z', math.radians(90))
                        
                    # Transfer Properties
                    new_root.name = old_name + "_Refined"
                    new_root['gmod_model'] = model_path_str
                    if 'gmod_data' in old_obj: new_root['gmod_data'] = old_obj['gmod_data']
                    if 'gmod_id' in old_obj: new_root['gmod_id'] = old_obj['gmod_id']
                    
                    # Material Override?
                    # If old object had manual material override, we might want to keep it?
                    # But the point is to get NEW materials. So maybe not.
                    # Unless it's a Toolgun override.
                    # Let's check 'gmod_data' JSON.
                    # Material Fixes: Ensure new materials are correctly configured
                    for mat_slot in new_root.material_slots:
                        if mat_slot.material:
                            apply_mat_fixes(mat_slot.material)
                    
                    # Toolgun material override restoration
                    if 'gmod_data' in old_obj:
                         import json
                         try:
                            d = json.loads(old_obj['gmod_data'])
                            mat_override = d.get('material')
                            if mat_override:
                                # Toolgun material restoration logic
                                mat_name = os.path.basename(mat_override)
                                target_mat = bpy.data.materials.get(mat_name)
                                if target_mat:
                                    def apply_ov(o):
                                        if o.type == 'MESH':
                                            for i in range(len(o.data.materials)):
                                                o.data.materials[i] = target_mat
                                        for c in o.children: apply_ov(c)
                                    apply_ov(new_root)
                         except: pass

                    # Re-apply Bodygroups/Skins from Old Data
                    if 'gmod_data' in old_obj:
                        try:
                            d = json.loads(old_obj['gmod_data'])
                            if 'bodygroups' in d: apply_bodygroups(new_root, d['bodygroups'])
                            if 'skin' in d: apply_skin(new_root, d['skin'])
                        except Exception as e:
                            print(f"[GModRefine] Failed to re-apply bodygroups/skins: {e}")

                    # Transfer Children (Linkage)
                    # We need to move children OF old_obj to new_root.
                    # Be careful: OLD obj children include the MESHES of the old import.
                    # We only want to transfer LOGICAL children (other Import Props).
                    # How to distinguish?
                    # Import Meshes usually exist in same Collection? Or have names?
                    # Actually, if we delete Old Hierarchy, we delete its meshes.
                    # We should only reparent objects that have 'gmod_id' (other entities).
                    
                    for child in old_obj.children:
                        if 'gmod_id' in child:
                            # It's another entity linked to this one
                            mat_safe = child.matrix_world.copy()
                            child.parent = new_root
                            child.matrix_world = mat_safe
                    
                    # Ensure New Object is in Scene
                    target_col = old_obj.users_collection[0] if old_obj.users_collection else context.collection
                    if new_root.name not in target_col.objects:
                        print(f"[GModRefine] Linking {new_root.name} to {target_col.name}")
                        target_col.objects.link(new_root)
                    
                    print(f"[GModRefine] Swapping complete. Deleting old: {old_name}")

                    # Delete Old
                    # We must delete the whole hierarchy of old_obj (meshes etc)
                    # But NOT the children we just reparented.
                    # Objects are already reparented, so delete_hierarchy on old_obj is safe for them?
                    # No, Unparented children stay.
                    
                    # Delete Hierarchy Helper
                    def delete_recursive(obj):
                        children = list(obj.children)
                        for c in children:
                            delete_recursive(c)
                        bpy.data.objects.remove(obj, do_unlink=True)
                        
                    delete_recursive(old_obj)
                    
                    # Rename New
                    new_root.name = old_name # Restore original name
                    
                    success_count += 1
                    
            except Exception as e:
                import traceback as _get_tb
                tb_str = _get_tb.format_exc()
                print(f"[GModRefine] Failed to swap {old_name}: {e}")
                print(tb_str)
                try:
                    with open("Z:/gmod_balabanovo/gmod_importer_debug.log", "a", encoding="utf-8") as _log_f:
                        _log_f.write(f"\n--- ERROR REFINING {old_name} ---\n")
                        _log_f.write(tb_str)
                except:
                    pass
        
        self.report({'INFO'}, f"Refined {success_count} objects from Cache.")
        return {'FINISHED'}

class GModBrowseAndLoadMdl(bpy.types.Operator):
    """Manually browse to an MDL file to load it in place of this placeholder"""
    bl_idname = "gmod.browse_and_load_mdl"
    bl_label = "Browse MDL File"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: bpy.props.StringProperty(
        name="MDL File",
        description="Path to the .mdl file",
        subtype='FILE_PATH',
        default=""
    )
    filter_glob: bpy.props.StringProperty(default="*.mdl", options={'HIDDEN'})
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None and "missing_model" in context.active_object

    def invoke(self, context, event):
        # Pre-fill with the last used path or the missing model's folder
        obj = context.active_object
        missing = obj.get("missing_model", "")
        if missing:
            # Try to build a starting dir from cache path
            cache_path = context.scene.gmod_cache_path
            if cache_path:
                # Build expected path in cache
                guessed = os.path.join(cache_path, "merged_content", missing.replace('/', os.sep))
                if os.path.exists(guessed):
                    self.filepath = guessed
                else:
                    self.filepath = cache_path
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        obj = context.active_object
        mdl_path = self.filepath
        
        if not mdl_path or not os.path.exists(mdl_path):
            self.report({'ERROR'}, f"File not found: {mdl_path}")
            return {'CANCELLED'}
        
        if not mdl_path.lower().endswith('.mdl'):
            self.report({'ERROR'}, "Please select a .mdl file")
            return {'CANCELLED'}
        
        mdl_path_fwd = mdl_path.replace('\\', '/')
        
        # Compute virtual path (relative to models/)
        virt_path = mdl_path_fwd
        if '/models/' in virt_path.lower():
            idx = virt_path.lower().find('/models/')
            virt_path = virt_path[idx + 1:]
        virt_path = virt_path.lower()
        
        # Inject into ASSET_INDEX
        operators_cache.ASSET_INDEX[virt_path] = mdl_path_fwd
        print(f"[GModBrowse] Injected: {virt_path} -> {mdl_path_fwd}")
        
        # Set up CM exactly like GModImportScene does
        cm = get_content_manager(force_recreate=True)
        gmod_root_path = context.scene.get('gmod_last_root', '')
        if gmod_root_path and os.path.exists(gmod_root_path):
            setup_gmod_mounts(context, cm, TinyPath(gmod_root_path))
            print(f"[GModBrowse] CM mounted from gmod_last_root: {gmod_root_path}")
        else:
            # Fallback: add merged_content directly
            cache_p = getattr(context.scene, 'gmod_cache_path', '')
            if not cache_p:
                cache_p = os.path.join(bpy.utils.resource_path('USER'), "gmod_workshop_cache")
            merged = os.path.join(cache_p, "merged_content")
            if os.path.exists(merged):
                from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.loose_files import LooseFilesContentProvider
                cm.add_child(LooseFilesContentProvider(TinyPath(merged)))
                print(f"[GModBrowse] Fallback: merged_content mounted: {merged}")
        
        # Create a plain Python helper that borrows the needed import methods
        # (bpy_struct operators can't be instantiated with __new__)
        class _ImportHelper:
            pass
        _ImportHelper.get_or_load_master    = ImportGModScene.get_or_load_master
        _ImportHelper.instance_hierarchy    = ImportGModScene.instance_hierarchy
        _ImportHelper.link_hierarchy_recursive = ImportGModScene.link_hierarchy_recursive
        _ImportHelper.get_placeholder_template = ImportGModScene.get_placeholder_template
        importer = _ImportHelper()
        try:
            file_buffer = cm.find_file(TinyPath(virt_path))
            if not file_buffer:
                self.report({'ERROR'}, f"Model not found in mounts: {virt_path}")
                return {'CANCELLED'}
                
            class MockOptions:
                bodygroup_grouping = True
                import_textures = not context.scene.gmod_skip_materials
                skin_decals = False
                import_physics = False
                write_qc = False
                load_refpose = False
                import_animations = False
                create_flex_drivers = False
                use_bvlg = (context.scene.gmod_pull_material_mode == 'SOURCEIO')
                scale = utils.SCALE_FACTOR
                
            container = import_model(TinyPath(virt_path), file_buffer, cm, MockOptions())
            new_obj = container.objects[0]
            while new_obj.parent: new_obj = new_obj.parent
        except Exception as e:
            import traceback; traceback.print_exc()
            self.report({'ERROR'}, f"import_model failed: {e}")
            return {'CANCELLED'}
        
        if not new_obj:
            self.report({'ERROR'}, "Instancing returned None")
            return {'CANCELLED'}
        
        # Make visible
        new_obj.hide_viewport = False
        new_obj.hide_render = False
        
        # Remap bodygroup JSON (master names → instance names)
        # Note: In direct import, container names might differ, but we rely on SourceIO naming
        
        # Apply transforms from placeholder
        new_obj.matrix_world = obj.matrix_world.copy()
        
        # Transfer gmod_data
        for key in ('gmod_data', 'gmod_id'):
            if key in obj:
                new_obj[key] = obj[key]
        new_obj['gmod_model'] = virt_path
        
        # Apply gmod_data bodygroups / pose
        gmod_data_raw = obj.get('gmod_data')
        if gmod_data_raw:
            try:
                gmd = json.loads(gmod_data_raw)
                bg_data = gmd.get('bodygroups', {})
                if bg_data:
                    apply_bodygroups(new_obj, bg_data)
            except Exception as e:
                print(f"[GModBrowse] gmod_data apply failed: {e}")
        
        # Link to same collection as placeholder
        for col in list(obj.users_collection):
            try: col.objects.link(new_obj)
            except: pass
        
        # Remove placeholder
        old_name = obj.name
        try:
            obj.name = f"_TRASH_{old_name}"
            new_obj.name = old_name
            bpy.data.objects.remove(obj, do_unlink=True)
        except Exception as e:
            print(f"[GModBrowse] Cleanup failed: {e}")
        
        # Select new object
        bpy.ops.object.select_all(action='DESELECT')
        try:
            new_obj.select_set(True)
            context.view_layer.objects.active = new_obj
        except: pass
        
        self.report({'INFO'}, f"Loaded: {os.path.basename(mdl_path)}")
        return {'FINISHED'}


class GModRetryMissing(bpy.types.Operator):
    """Attempt to reload missing models from Cache for existing placeholders"""
    bl_idname = "gmod.retry_missing"
    bl_label = "Retry Missing Models"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cm = get_content_manager(force_recreate=True)
        operators_cache.WorkshopCacheManager.rebuild_index(context)
        
        # 1. Mount everything the same way as GModImportScene does
        # (including merged_content as LooseFilesContentProvider for VTX/VVD resolution)
        gmod_root_path = context.scene.get('gmod_last_root', '')
        if gmod_root_path and os.path.exists(gmod_root_path):
            setup_gmod_mounts(context, cm, TinyPath(gmod_root_path))
            print(f"[GModRetry] Full mount via setup_gmod_mounts: {gmod_root_path}")
        else:
            # Fallback: at least add merged_content directly
            cache_path_str = context.scene.gmod_cache_path
            if not cache_path_str:
                cache_path_str = os.path.join(bpy.utils.resource_path('USER'), "gmod_workshop_cache")
            merged = os.path.join(cache_path_str, "merged_content")
            if os.path.exists(merged):
                from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.loose_files import LooseFilesContentProvider
                cm.add_child(LooseFilesContentProvider(TinyPath(merged)))
                print(f"[GModRetry] Fallback: Mounted merged_content: {merged}")
            

        count = 0
        fixed = 0
        cache_hits = 0
        
        print(f"[GModRetry] Starting retry scan. Total Assets in Index: {len(operators_cache.ASSET_INDEX)}")
        
        scene_objects = list(bpy.context.scene.objects)
        
        for obj in scene_objects:
            model_path_str = obj.get('gmod_model')
            if not model_path_str:
                continue
                
            # Candidate Detection
            is_candidate = False
            if "PLACEHOLDER" in obj.name or "GMOD_PLACEHOLDER" in obj.name: is_candidate = True
            elif obj.type == 'EMPTY': is_candidate = True # Also check empties
            elif obj.type == 'FONT': is_candidate = True
            
            if not is_candidate:
                # Check collection
                for col in obj.users_collection:
                    if "PLACEHOLDER" in col.name: 
                        is_candidate = True
                        break
            
            if not is_candidate:
                continue
                
            count += 1
            
            # Resolve
            cached_path = operators_cache.WorkshopCacheManager.resolve_path(model_path_str)
            file_buffer = None
            
            if cached_path and os.path.exists(cached_path):
                try:
                    file_buffer = FileBuffer(cached_path, 'rb')
                except Exception as e:
                    print(f"  ! Failed to read cache file: {e}")
            else:
                 file_buffer = cm.find_file(TinyPath(model_path_str))
                
            if file_buffer:
                cache_hits += 1
                try:
                    class MockOptions:
                        bodygroup_grouping = True # ENABLED
                        import_textures = not context.scene.gmod_skip_materials
                        skin_decals = False
                        import_physics = False
                        write_qc = False
                        load_refpose = False
                        import_animations = False
                        create_flex_drivers = False
                        use_bvlg = (context.scene.gmod_pull_material_mode == 'SOURCEIO')
                        scale = utils.SCALE_FACTOR
                        
                    container = import_model(TinyPath(model_path_str), file_buffer, cm, MockOptions())
                    
                    found_objs = []
                    if container.objects:
                         found_objs = container.objects
                    
                    # RELAXED VALIDATION: Accept anything SourceIO returns (MESH, ARMATURE, EMPTY)
                    if found_objs:
                        # Success!
                        new_root = found_objs[0]
                        print(f"[GModRetry] SUCCESS for {obj.name}! Imported {len(found_objs)} objects. Root: {new_root.type}")
                        
                        while new_root.parent: new_root = new_root.parent
                        
                        # Debug Children
                        print(f"[GModRetry] Children of {new_root.name}:")
                        for c in new_root.children:
                            print(f"  -> {c.name}")
                        
                        # Swap
                        new_root.parent = obj.parent
                        new_root.matrix_world = obj.matrix_world
                        
                        # CORRECTION: Always rotate Children (Mesh Data), never the Root Object itself.
                        # This avoids double-rotating Armatures (like Cabinets/Ragdolls) which breaks Posing.
                        for child in new_root.children:
                            child.rotation_euler.rotate_axis('Z', math.radians(90))

                        desired_name = obj.name
                        obj.name = f"TRASH_{desired_name}"
                        new_root.name = desired_name 
                        new_root['gmod_model'] = model_path_str
                        
                        # Restore Data & Apply Poses
                            # Material Fixes
                        for slot in new_root.material_slots:
                            if slot.material:
                                apply_mat_fixes(slot.material)

                        # Restore Data (Bodygroups/Skins)
                        raw_json = obj.get('gmod_data')
                        if raw_json:
                            try:
                                import json
                                data = json.loads(raw_json)
                                new_root['gmod_data'] = raw_json
                                if 'bodygroups' in data: apply_bodygroups(new_root, data['bodygroups'])
                                if 'skin' in data: apply_skin(new_root, data['skin'])
                            except Exception as e:
                                print(f"[GModRetry] Failed to read gmod_data: {e}")
                        
                        # Collection Linkage
                        main_col = utils.get_or_create_collection("GMOD_SCENE")
                        props_col = utils.get_or_create_collection("PROPS", main_col)
                        self.link_hierarchy_recursive(new_root, props_col)
                        
                        # Delete Old Placeholder
                        self.delete_hierarchy(obj)
                        fixed += 1
                        
                        # RE-APPLY BONES FROM PLACEHOLDER?
                        # If the Placeholder has 'gmod_data' property?
                        # We need to update `process_scene` to save full data to placeholder.
                        
                    else:
                        msg = f"[GModRetry] Import ran for {model_path_str} but returned NO objects."
                        print(msg)
                        try:
                            with open("Z:/gmod_balabanovo/gmod_importer_debug.log", "a", encoding="utf-8") as _log_f:
                                _log_f.write(f"\n--- GModRetry EMPTY CONTAINER FOR {model_path_str} ---\n{msg}\n")
                        except:
                            pass
                        
                except Exception as e:
                    import traceback as _get_tb
                    tb_str = _get_tb.format_exc()
                    print(f"[GModRetry] Exception importing {model_path_str}: {e}")
                    print(tb_str)
                    try:
                        with open("Z:/gmod_balabanovo/gmod_importer_debug.log", "a", encoding="utf-8") as _log_f:
                            _log_f.write(f"\n--- ERROR RETRYING {model_path_str} ---\n")
                            _log_f.write(tb_str)
                    except Exception as _log_e:
                        print(f"Failed to write log file: {_log_e}")
            else:
                pass 

        self.report({'INFO'}, f"Scanned {count}. Found Files: {cache_hits}. Fixed: {fixed}.")
        return {'FINISHED'}

    def link_hierarchy_recursive(self, obj, collection):
        if obj.name not in collection.objects:
             collection.objects.link(obj)
        for col in obj.users_collection:
            if col != collection:
                col.objects.unlink(obj)
        for child in obj.children:
            self.link_hierarchy_recursive(child, collection)

    def delete_hierarchy(self, obj):
        if obj is None: return
        try:
            children = [c for c in obj.children]
            for child in children:
                self.delete_hierarchy(child)
            for col in obj.users_collection:
                col.objects.unlink(obj)
            bpy.data.objects.remove(obj, do_unlink=True)
        except: pass

def resolve_bone_name_fuzzy(base_armature, bone_name):
    if not bone_name:
        return None
    bone_name_lower = bone_name.lower().strip()
    
    # 1. Direct match (case-insensitive) and SourceIO prefixes
    for bone in base_armature.pose.bones:
        b_name_low = bone.name.lower()
        if b_name_low == bone_name_lower:
            return bone
        if b_name_low == f"attachment_{bone_name_lower}":
            return bone
        if b_name_low == f"attach_{bone_name_lower}":
            return bone

    # Helper to check if bone belongs to the player hands/biped skeleton
    # We should skip these to avoid attaching weapon attachments to player hands (e.g. Bip01_R_Grip)
    def is_player_hand_bone(name_lower):
        return any(x in name_lower for x in ["valvebiped", "bip01", "bip_", "finger", "hand", "arm"])
            
    # 2. Match with prefix removal (e.g. "mod_reciever" -> "reciever")
    clean_name = bone_name_lower
    if clean_name.startswith("mod_"):
        clean_name = clean_name[4:]
    if clean_name.startswith("weapon_"):
        clean_name = clean_name[7:]
        
    for bone in base_armature.pose.bones:
        b_name_lower = bone.name.lower()
        if is_player_hand_bone(b_name_lower):
            continue
        if clean_name in b_name_lower or b_name_lower in clean_name:
            return bone
            
    # 3. Typo/variation correction (e.g. "reciever" vs "receiver")
    norm_name = clean_name.replace("ei", "ie").replace("ie", "ei")
    for bone in base_armature.pose.bones:
        b_name_lower = bone.name.lower()
        if is_player_hand_bone(b_name_lower):
            continue
        if norm_name in b_name_lower or b_name_lower in norm_name:
            return bone
            
    # 4. Semantic mapping rules
    rules = [
        (["magazine", "mag", "clip"], ["mag", "clip"]),
        (["receiver", "reciever", "frame", "body", "gun", "receiver"], ["receiver", "reciever", "frame", "body", "gun", "receiver"]),
        (["grip", "pgrip", "handle"], ["grip", "handle"]),
        (["stock"], ["stock"]),
        (["handguard", "hg", "guard", "foregrip"], ["handguard", "hg", "guard", "foregrip"]),
        (["barrel", "muzzle", "silencer"], ["barrel", "muzzle", "silencer"])
    ]
    
    for keywords, targets in rules:
        if any(kw in bone_name_lower for kw in keywords):
            for bone in base_armature.pose.bones:
                b_name_lower = bone.name.lower()
                if is_player_hand_bone(b_name_lower):
                    continue
                if any(t in b_name_lower for t in targets):
                    if "root" not in b_name_lower and "base" not in b_name_lower:
                        return bone
            for bone in base_armature.pose.bones:
                b_name_lower = bone.name.lower()
                if is_player_hand_bone(b_name_lower):
                    continue
                if any(t in b_name_lower for t in targets):
                    return bone
                    
    return None

class GModImportARC9RuntimeOperator(bpy.types.Operator):
    """Import ARC9 Weapon with all its attachments from JSON"""
    bl_idname = "gmod.import_weapon"
    bl_label = "Import ARC9 Weapon"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    spawn_mode: bpy.props.StringProperty(default="ORIGIN")
    
    # Copy helper methods needed from scene importer context
    def link_hierarchy_recursive(self, obj, collection):
        if obj.name not in collection.objects:
             collection.objects.link(obj)
        for col in obj.users_collection:
            if col != collection:
                col.objects.unlink(obj)
        for child in obj.children:
            self.link_hierarchy_recursive(child, collection)

    def instance_hierarchy(self, obj, mapping):
        if not obj: return None
        new_obj = obj.copy()
        new_obj.hide_viewport = False
        new_obj.hide_render = False
        mapping[obj] = new_obj
        if new_obj.type == 'MESH' and new_obj.data:
            new_obj.data = new_obj.data.copy()
            # Allow direct viewport selection of all meshes
            pass
        for child in obj.children:
            new_child = self.instance_hierarchy(child, mapping)
            new_child.parent = new_obj
            new_child.matrix_parent_inverse = child.matrix_parent_inverse.copy()
        return new_obj

    def delete_hierarchy(self, obj):
        if obj is None: return
        try:
            children = [c for c in obj.children]
            for child in children:
                self.delete_hierarchy(child)
            for col in obj.users_collection:
                col.objects.unlink(obj)
            bpy.data.objects.remove(obj, do_unlink=True)
        except: pass

    def clear_import_cache(self):
        """Remove cached master models so they are re-imported with current settings."""
        to_remove = [obj for obj in bpy.data.objects if obj.name.startswith("CACHE:")]
        for obj in to_remove:
            try:
                self.delete_hierarchy(obj)
            except:
                pass
        cache_col = bpy.data.collections.get("IMPORT_CACHE")
        if cache_col:
            for obj in list(cache_col.objects):
                try:
                    self.delete_hierarchy(obj)
                except:
                    pass

    def get_or_load_master(self, context, cm, model_path_str):
        if not model_path_str: return None
        sanitized_path = model_path_str.lower().replace('\\', '/').lstrip('/')
        import hashlib
        short_hash = hashlib.md5(sanitized_path.encode()).hexdigest()[:8]
        base = os.path.basename(sanitized_path)
        cache_name = f"CACHE:{short_hash}_{base}"[:63]
        if cache_name in bpy.data.objects:
            return bpy.data.objects[cache_name]
            
        file_buffer = None
        model_path = TinyPath(sanitized_path)
        cached_abs_path = operators_cache.WorkshopCacheManager.resolve_path(sanitized_path)
        if cached_abs_path and os.path.exists(cached_abs_path):
             print(f"[GModImporter] Loading {sanitized_path} FROM CACHE: {cached_abs_path}")
             file_buffer = FileBuffer(cached_abs_path, 'rb')
             path_parts = os.path.normpath(cached_abs_path).split(os.sep)
             addon_root = None
             for i in range(len(path_parts)-1, -1, -1):
                 if path_parts[i].lower() in ('models', 'materials', 'sound'):
                     addon_root = os.sep.join(path_parts[:i])
                     break
             if addon_root and os.path.isdir(addon_root):
                 try:
                     from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.loose_files import LooseFilesContentProvider
                     cm.add_child(LooseFilesContentProvider(TinyPath(addon_root)))
                 except Exception as _jit_e:
                     print(f"[GModImporter] JIT mount failed: {_jit_e}")
                     try: cm.scan_for_content(TinyPath(addon_root))
                     except: pass
        else:
             print(f"[GModImporter] Cache MISS for {sanitized_path}. Trying SourceIO Mounts...")
             file_buffer = cm.find_file(model_path)
             
        if not file_buffer:
             print(f"[GModImporter] ERROR: Could not find model file: {sanitized_path}")
             return None
             
        try:
            class MockOptions:
                bodygroup_grouping = True
                import_textures = not context.scene.gmod_skip_materials
                skin_decals = False
                import_physics = False
                write_qc = False
                load_refpose = False
                import_animations = False
                create_flex_drivers = False
                use_bvlg = (context.scene.gmod_pull_material_mode == 'SOURCEIO')
                scale = context.scene.gmod_global_scale
            
            container = import_model(model_path, file_buffer, cm, MockOptions())
        except Exception as e:
            import traceback as _get_tb
            tb_str = _get_tb.format_exc()
            print(tb_str)
            print(f"[GModImporter] import_model() FAILED: {type(e).__name__}: {e}")
            return None

        if not container or not container.objects:
            return None

        # Link master objects to IMPORT_CACHE
        cache_col = utils.get_or_create_collection("IMPORT_CACHE")
        
        master_obj = None
        if container.armature:
            master_obj = container.armature
        else:
            for obj in container.objects:
                if obj.parent is None:
                    master_obj = obj
                    break
                    
        if not master_obj and container.objects:
            master_obj = container.objects[0]
            
        all_objs = list(container.objects)
        if container.armature:
            all_objs.append(container.armature)
        if container.attachments:
            all_objs.extend(container.attachments)
            
        for obj in all_objs:
            # Unlink from other collections to keep the viewport clean
            for col in list(obj.users_collection):
                if col != cache_col:
                    col.objects.unlink(obj)
            if obj.name not in cache_col.objects:
                cache_col.objects.link(obj)
                
            # Hide master
            obj.hide_viewport = True
            obj.hide_render = True
            
        if master_obj:
            master_obj.name = cache_name
        
        # Populate Categories in master
        if "source_bodygroups_json" in master_obj:
            try:
                import json
                bgs = json.loads(master_obj["source_bodygroups_json"])
                master_obj.gmod_bg_categories.clear()
                
                # Check for categories in cache
                cats = operators_cache.WorkshopCacheManager.get_categories(sanitized_path)
                if cats:
                    for cat_name, bg_list in cats.items():
                        cat_item = master_obj.gmod_bg_categories.add()
                        cat_item.name = cat_name
                    cat_map = {}
                    for cat_name, bg_list in cats.items():
                        for bg in bg_list:
                            cat_map[bg] = cat_name
                    master_obj["gmod_bg_categories_map"] = json.dumps(cat_map)
                else:
                    cat_item = master_obj.gmod_bg_categories.add()
                    cat_item.name = "General"
                    cat_map = {bg: "General" for bg in bgs.keys()}
                    master_obj["gmod_bg_categories_map"] = json.dumps(cat_map)
            except Exception as e:
                print(f"[GModImporter] Master bodygroups init failed: {e}")
                
        return master_obj

    def kill_phong_globally(self):
        for mat in bpy.data.materials:
            if mat.node_tree:
                apply_mat_fixes(mat)

    def execute_v2(self, context, weapon_data):
        import json
        import os
        import math
        import mathutils
        
        def find_armature(obj):
            if not obj:
                return None
            if obj.type == 'ARMATURE':
                return obj
            for child in obj.children:
                res = find_armature(child)
                if res:
                    return res
            return None
            
        def spawn_model(context, cm, collection, global_scale, model_path, body_groups=None, skin_index=0):
            master_obj = self.get_or_load_master(context, cm, model_path)
            if not master_obj:
                return None
            mapping = {}
            new_obj = self.instance_hierarchy(master_obj, mapping)
            if not new_obj:
                return None
            self.link_hierarchy_recursive(new_obj, collection)
            
            # Set gmod_model property on armature and mesh children
            new_obj["gmod_model"] = model_path
            for child in new_obj.children:
                if child.type == 'MESH':
                    child["gmod_model"] = model_path
            
            # Fix Armature modifier references on instanced meshes and strip CACHE: prefix
            for old_o, new_o in mapping.items():
                if new_o.name.startswith("CACHE:"):
                    new_o.name = new_o.name[6:]  # remove CACHE:
                if new_o.type == 'MESH':
                    for mod in new_o.modifiers:
                        if mod.type == 'ARMATURE' and mod.object in mapping:
                            mod.object = mapping[mod.object]
                            
            # Apply skin
            new_obj["active_skin"] = str(skin_index)
            apply_skin(new_obj, skin_index)
            
            # Apply bodygroups
            if body_groups and "source_bodygroups_json" in new_obj:
                try:
                    def clean_name(s):
                        return s.lower().replace("ie", "ei").replace("_", "").replace("-", "").strip()
                    bgs = json.loads(new_obj["source_bodygroups_json"])
                    bodygroups_data = {}
                    body_groups_clean = {clean_name(k): v for k, v in body_groups.items()}
                    for bg_id, name in enumerate(bgs.keys()):
                        name_clean = clean_name(name)
                        val = body_groups_clean.get(name_clean, 0)
                        bodygroups_data[bg_id] = val
                    apply_bodygroups(new_obj, bodygroups_data, None)
                except Exception as e:
                    print(f"Failed to apply bodygroups: {e}")
            return new_obj

        coord_sys = weapon_data.get("CoordinateSystem", {})
        global_scale = coord_sys.get("scale", 0.0254)
        
        # Setup Content Manager
        gmod_root = context.scene.gmod_weapon_root_path
        if not gmod_root:
            gmod_root = context.scene.gmod_root_path
            
        if not gmod_root:
            import pathlib
            json_path = pathlib.Path(self.filepath)
            for p in json_path.parents:
                if p.name.lower() == "garrysmod":
                    gmod_root = str(p.parent)
                    break
                
        if not gmod_root or not os.path.exists(gmod_root):
            self.report({'ERROR'}, "GMod Folder is not configured! Please specify your 'GMod Folder' path (e.g. steamapps/common/GarrysMod) in the importer panel first.")
            return {'CANCELLED'}
            
        # Temporarily apply weapon material settings
        old_skip = context.scene.gmod_skip_materials
        old_mode = context.scene.gmod_pull_material_mode
        context.scene.gmod_skip_materials = context.scene.gmod_weapon_skip_materials
        context.scene.gmod_pull_material_mode = context.scene.gmod_weapon_pull_material_mode

        from gmod_scene_importer.SourceIO_adv.library.shared.content_manager import ContentManager
        cm = ContentManager()
        cache_path_str = context.scene.gmod_weapon_cache_path
        if not cache_path_str:
            cache_path_str = context.scene.gmod_cache_path
            
        setup_gmod_mounts(context, cm, TinyPath(gmod_root), override_cache_path=cache_path_str)
        
        # Collections
        main_col = utils.get_or_create_collection("GMOD_SCENE")
        weapons_col = utils.get_or_create_collection("ARC9_Weapons", main_col)
        
        # Create WeaponRoot empty
        weapon_root_obj = bpy.data.objects.new("WeaponRoot", None)
        weapons_col.objects.link(weapon_root_obj)
        
        if self.spawn_mode == 'CURSOR':
            weapon_root_obj.location = context.scene.cursor.location.copy()
        else:
            weapon_root_obj.location = mathutils.Vector((0.0, 0.0, 0.0))
            
        resources = weapon_data.get("resources", {})

        # ── FRAMEDUMP PATH ─────────────────────────────────────────────────────
        # Runtime snapshot from Source Engine. Use full 4x4 matrices — no pos+ang guessing.
        framedump = weapon_data.get("framedump", {})
        framedump_objects_raw = framedump.get("objects", [])
        
        # Topological sort based on parent_guid to ensure parents spawn before children
        framedump_objects = []
        if framedump_objects_raw:
            visited = set()
            guid_to_obj = {obj.get("guid"): obj for obj in framedump_objects_raw if obj.get("guid")}
            
            def visit(obj):
                guid = obj.get("guid")
                if not guid or guid in visited:
                    return
                visited.add(guid)
                parent_guid = obj.get("parent_guid")
                if parent_guid and parent_guid in guid_to_obj:
                    visit(guid_to_obj[parent_guid])
                framedump_objects.append(obj)
                
            for obj in framedump_objects_raw:
                visit(obj)

        if framedump_objects:
            print(f"[GModImporter] FRAMEDUMP: {len(framedump_objects)} objects (sorted)")

            s = global_scale  # 0.0254 — inches to meters

            # ── Source→Blender axis change ──────────────────────────────────
            # Source: X=forward, Y=left, Z=up
            # Blender: X=right,  Y=forward, Z=up
            # C rotates the coordinate system: Blender_vec = C @ Source_vec
            C = mathutils.Matrix([
                [0.0, -1.0, 0.0, 0.0],
                [1.0,  0.0, 0.0, 0.0],
                [0.0,  0.0, 1.0, 0.0],
                [0.0,  0.0, 0.0, 1.0],
            ])
            C_inv = C.inverted()

            def src_mat_to_blender(mat_raw, scale_val):
                """Convert a 16-element Source row-major world matrix to Blender world matrix with custom translation scale."""
                if not mat_raw or len(mat_raw) != 16:
                    return None
                M_src = mathutils.Matrix([
                    mat_raw[0:4],
                    mat_raw[4:8],
                    mat_raw[8:12],
                    mat_raw[12:16],
                ])
                # Change basis: rotation = C @ R_src @ C_inv
                M_bl = C @ M_src @ C_inv
                # Scale translation: Blender_T = C @ Source_T * scale
                M_bl[0][3] = -M_src[1][3] * scale_val   # Blender X = -Source Y
                M_bl[1][3] =  M_src[0][3] * scale_val   # Blender Y =  Source X
                M_bl[2][3] =  M_src[2][3] * scale_val   # Blender Z =  Source Z
                return M_bl

            # ── Convert ViewModel world matrix to Blender ───────────────────
            # We need VM_blender so we can compute:  relative = VM_bl_inv @ Obj_bl
            vm_mat_raw = framedump.get("viewmodel", {}).get("world_matrix")
            VM_bl = src_mat_to_blender(vm_mat_raw, global_scale)
            VM_bl_inches = src_mat_to_blender(vm_mat_raw, 1.0)
            
            if VM_bl is None:
                # Fallback: weapon root is at origin
                VM_bl = weapon_root_obj.matrix_world.copy()
                VM_bl_inches = mathutils.Matrix.Identity(4)
                print("[GModImporter] FD: no VM world_matrix, using Identity")
            else:
                print(f"[GModImporter] FD: VM world_matrix OK  T=({VM_bl[0][3]:.2f},{VM_bl[1][3]:.2f},{VM_bl[2][3]:.2f})")
                
            try:
                VM_bl_inv = VM_bl.inverted()
            except Exception as e:
                print(f"[GModImporter] FD: VM_bl singular ({e}), using Identity")
                VM_bl_inv = mathutils.Matrix.Identity(4)
                
            try:
                VM_bl_inches_inv = VM_bl_inches.inverted()
            except Exception as e:
                VM_bl_inches_inv = mathutils.Matrix.Identity(4)

            # ── Spawn ViewModel ─────────────────────────────────────────────
            vm_arm = None
            vm_model = framedump.get("viewmodel", {}).get("model", "")
            if vm_model:
                try:
                    vm_arm = spawn_model(context, cm, weapons_col, global_scale,
                                         vm_model, body_groups={}, skin_index=0)
                    if vm_arm:
                        vm_arm.parent = weapon_root_obj
                        vm_arm.matrix_parent_inverse = mathutils.Matrix.Identity(4)
                        vm_arm.matrix_world = weapon_root_obj.matrix_world
                        
                        # Fix armature modifier targets for viewmodel meshes
                        for child in vm_arm.children:
                            if child.type == 'MESH':
                                for mod in child.modifiers:
                                    if mod.type == 'ARMATURE':
                                        mod.object = vm_arm
                        
                        # Apply viewmodel bodygroups
                        vm_bgs = framedump.get("viewmodel", {}).get("bodygroups", {})
                        if vm_bgs and "source_bodygroups_json" in vm_arm:
                            try:
                                def clean_bg_name(s):
                                    return s.lower().replace("ie", "ei").replace("_", "").replace("-", "").strip()
                                bgs = json.loads(vm_arm["source_bodygroups_json"])
                                bodygroups_data = {}
                                vm_bgs_clean = {clean_bg_name(k): v for k, v in vm_bgs.items()}
                                for bg_id, name in enumerate(bgs.keys()):
                                    name_clean = clean_bg_name(name)
                                    val = vm_bgs_clean.get(name_clean, 0)
                                    bodygroups_data[bg_id] = val
                                apply_bodygroups(vm_arm, bodygroups_data, None)
                            except Exception as e:
                                print(f"[GModImporter] Failed to apply viewmodel bodygroups: {e}")

                        vm_bones_data = framedump.get("vm_bones", [])
                        if vm_bones_data:
                            apply_skeleton_pose(vm_arm, vm_bones_data,
                                                global_scale, weapon_root_obj,
                                                entity_class="viewmodel")
                        hide_arm_bones(vm_arm)
                        print(f"[GModImporter] FD ViewModel: {vm_model}")
                except Exception as e:
                    print(f"[GModImporter] FD VM error: {e}")

            spawned_attachments = {}
            
            # Pass 1: Spawn all models first so their armatures exist
            for obj_data in framedump_objects:
                model = obj_data.get("model", "")
                guid = obj_data.get("guid") or obj_data.get("id") or "?"
                if not model:
                    continue

                # Avoid spawning duplicate viewmodel weapon object, map its GUID to vm_arm
                obj_class = obj_data.get("class", "").lower()
                if "viewmodel" in obj_class or model.lower() == vm_model.lower():
                    if vm_arm:
                        spawned_attachments[guid] = vm_arm
                        print(f"[GModImporter] Mapping duplicate viewmodel GUID {guid} to vm_arm")
                    continue
                try:
                    bgs = obj_data.get("bodygroups", {})
                    arm = spawn_model(context, cm, weapons_col, global_scale,
                                      model, body_groups=bgs, skin_index=obj_data.get("skin", 0))
                    if arm:
                        spawned_attachments[guid] = arm
                        # Fix armature modifier targets for attachment meshes
                        for child in arm.children:
                            if child.type == 'MESH':
                                for mod in child.modifiers:
                                    if mod.type == 'ARMATURE':
                                        mod.object = arm
                except Exception as e:
                    print(f"[GModImporter] FD Spawn ERR {model[-40:]}: {e}")

            # Force Blender to update bone matrices after posing viewmodel/hands
            context.view_layer.update()

            # Pass 2: Parent and pose models now that all armatures are available
            for obj_data in framedump_objects:
                model = obj_data.get("model", "")
                guid = obj_data.get("guid") or obj_data.get("id") or "?"
                arm = spawned_attachments.get(guid)
                if not arm or arm == vm_arm:
                    continue

                # Path A: raw 16-element world_matrix (best — no angle extraction loss)
                M_obj_bl = src_mat_to_blender(obj_data.get("world_matrix"), global_scale)

                if M_obj_bl is not None:
                    # Relative to ViewModel in Blender space
                    M_rel = VM_bl_inv @ M_obj_bl
                else:
                    # Path B: local pos+ang from WorldToLocal (fallback)
                    pos = obj_data.get("pos")
                    ang = obj_data.get("ang", [0, 0, 0])
                    if not pos:
                        continue
                    M_rel = utils.convert_source_transform(pos, ang, [1, 1, 1], global_scale)

                try:
                    # Find parent object
                    parent_guid = obj_data.get("parent_guid")
                    parent_obj = spawned_attachments.get(parent_guid) if parent_guid else vm_arm
                    
                    # Find the actual Armature in the parent hierarchy
                    parent_arm = find_armature(parent_obj) if parent_obj else None
                    if not parent_arm:
                        parent_arm = find_armature(vm_arm) if vm_arm else None
                        
                    # Find parent bone name from GMod or use heuristics
                    parent_bone_name = obj_data.get("parent_bone")
                    if not parent_bone_name:
                        model_lower = model.lower()
                        if "reciever" in model_lower or "receiver" in model_lower:
                            parent_bone_name = "mod_reciever"
                        elif "bolt" in model_lower:
                            parent_bone_name = "weapon_bolt"
                        elif "trigger" in model_lower:
                            parent_bone_name = "weapon_trigger"
                        elif "charging" in model_lower or "charge" in model_lower:
                            parent_bone_name = "mod_charge"
                        elif "pistolgrip" in model_lower or "grip" in model_lower:
                            parent_bone_name = "mod_pistol_grip"
                        elif "stock" in model_lower:
                            parent_bone_name = "mod_stock"
                        elif "mag" in model_lower:
                            parent_bone_name = "mod_magazine"
                        elif "bullet" in model_lower or "cartridge" in model_lower or "patron" in model_lower:
                            parent_bone_name = "patron_in_weapon"
                            
                    # Find the child armature's root bone name
                    child_root_bone_name = obj_data.get("root_bone", "root")
                    if child_root_bone_name == "root" or not child_root_bone_name:
                        arm_real = find_armature(arm)
                        if arm_real:
                            bones_data = obj_data.get("bones", [])
                            if bones_data:
                                for b in bones_data:
                                    if b.get("parent") is None or b.get("parent") < 0:
                                        child_root_bone_name = b.get("name", "root")
                                        break
                                        
                    if not parent_bone_name:
                        # 1. Try to find the root bone name on parent_arm
                        if parent_arm and (child_root_bone_name in parent_arm.pose.bones or find_matching_bone(parent_arm, child_root_bone_name)):
                            parent_bone_name = child_root_bone_name
                        else:
                            # 2. Search ALL spawned armatures for this bone name!
                            found_parent_arm = None
                            for temp_guid, temp_arm in spawned_attachments.items():
                                if temp_arm and temp_arm != arm:
                                    temp_arm_real = find_armature(temp_arm)
                                    if temp_arm_real and (child_root_bone_name in temp_arm_real.pose.bones or find_matching_bone(temp_arm_real, child_root_bone_name)):
                                        found_parent_arm = temp_arm_real
                                        break
                                        
                            if not found_parent_arm and vm_arm:
                                temp_arm_real = find_armature(vm_arm)
                                if temp_arm_real and (child_root_bone_name in temp_arm_real.pose.bones or find_matching_bone(temp_arm_real, child_root_bone_name)):
                                    found_parent_arm = temp_arm_real
                                    
                            if found_parent_arm:
                                parent_arm = found_parent_arm
                                parent_bone_name = child_root_bone_name
                                
                    # Parent direct weapon parts to vm_arm bones, and nested attachments to bones
                    is_root_part = (parent_guid == "23" or not parent_guid)
                    
                    parent_arm_to_use = parent_arm
                    parent_bone_to_use = parent_bone_name
                    
                    if is_root_part:
                        parent_arm_to_use = find_armature(vm_arm) if vm_arm else None
                        parent_bone_to_use = None
                        if parent_arm_to_use:
                            for bname in [parent_bone_name, "weapon", "weapon_bone", "valvebiped.weapon_bone", "base", "root"]:
                                if bname and (bname in parent_arm_to_use.pose.bones or find_matching_bone(parent_arm_to_use, bname)):
                                    matched = parent_arm_to_use.pose.bones.get(bname) or find_matching_bone(parent_arm_to_use, bname)
                                    parent_bone_to_use = matched.name
                                    break
                            if not parent_bone_to_use and len(parent_arm_to_use.pose.bones) > 0:
                                parent_bone_to_use = parent_arm_to_use.pose.bones[0].name
                                
                    if parent_arm_to_use and parent_bone_to_use:
                        # Resolve parent bone name
                        actual_bone = parent_arm_to_use.pose.bones.get(parent_bone_to_use) or find_matching_bone(parent_arm_to_use, parent_bone_to_use)
                        if actual_bone:
                            parent_bone_to_use = actual_bone.name
                            
                        # Apply Native Blender Bone-Parenting!
                        arm.parent = parent_arm_to_use
                        arm.parent_type = 'BONE'
                        arm.parent_bone = parent_bone_to_use
                        arm.matrix_parent_inverse = mathutils.Matrix.Identity(4)
                        
                        # Calculate matrix relative to the parent bone to preserve relative offsets for ALL attachments
                        bone_world_matrix = parent_arm_to_use.matrix_world @ actual_bone.matrix
                        arm.matrix_basis = bone_world_matrix.inverted() @ parent_arm_to_use.matrix_world @ M_rel
                    else:
                        # Fallback / Root flat parenting to vm_arm as an OBJECT
                        arm.parent = vm_arm if vm_arm else weapon_root_obj
                        arm.parent_type = 'OBJECT'
                        arm.matrix_parent_inverse = mathutils.Matrix.Identity(4)
                        arm.matrix_basis = M_rel
                        
                    # Pose bones inside the attachment armature
                    bones_data = obj_data.get("bones", [])
                    if bones_data:
                        apply_skeleton_pose(arm, bones_data, global_scale, weapon_root_obj, entity_class="attachment")
                        
                    T = M_rel.translation
                    print(f"[GModImporter] FD OK  {model[-40:]}  => ({T.x:.2f},{T.y:.2f},{T.z:.2f})")
                except Exception as e:
                    print(f"[GModImporter] FD ERR {model[-40:]}: {e}")

            # ── Spawn Hands ─────────────────────────────────────────────────
            hands_data  = framedump.get("hands", {})
            hands_model = hands_data.get("model", "")
            if hands_model and context.scene.gmod_weapon_import_hands:
                try:
                    hands_arm = spawn_model(context, cm, weapons_col, global_scale,
                                             hands_model, body_groups={}, skin_index=0)
                    if hands_arm:
                        # Fix armature modifier targets for hands meshes
                        for child in hands_arm.children:
                            if child.type == 'MESH':
                                for mod in child.modifiers:
                                    if mod.type == 'ARMATURE':
                                        mod.object = hands_arm
                        
                        hands_arm.parent = weapon_root_obj
                        hands_arm.matrix_parent_inverse = mathutils.Matrix.Identity(4)
                        hands_arm.matrix_basis = mathutils.Matrix.Identity(4)
                        hand_bones = hands_data.get("bones", [])
                        if hand_bones:
                            apply_skeleton_pose(hands_arm, hand_bones,
                                                global_scale, weapon_root_obj,
                                                entity_class="gmod_hands")
                        print(f"[GModImporter] FD Hands: {hands_model}")
                except Exception as e:
                    print(f"[GModImporter] FD hands error: {e}")

            # Keep skeletons and modifiers interactive for user inspection
            print("[GModImporter] Skeletons preserved for user inspection")

            context.scene.gmod_skip_materials = old_skip
            context.scene.gmod_pull_material_mode = old_mode
            return {'FINISHED'}
        # ── END FRAMEDUMP PATH ─────────────────────────────────────────────────


        nodes = weapon_data.get("scene", {}).get("nodes", [])
        
        # Map from node_id to spawned Blender object
        spawned_nodes = {"node_weapon_root": weapon_root_obj}
        all_mappings = {}
        
        pending_nodes = [node for node in nodes if node.get("id") != "node_weapon_root"]
        
        # Similarity transformation matrices for GMod -> Blender
        C = mathutils.Matrix([
            [ 0.0, -1.0,  0.0,  0.0],
            [ 1.0,  0.0,  0.0,  0.0],
            [ 0.0,  0.0,  1.0,  0.0],
            [ 0.0,  0.0,  0.0,  1.0]
        ])
        C_inv = C.inverted()
        
        attempts = 0
        max_attempts = len(pending_nodes) * 5
        while pending_nodes and attempts < max_attempts:
            attempts += 1
            node = pending_nodes.pop(0)
            parent_id = node.get("parent")
            
            # Check if parent is created
            if parent_id and parent_id not in spawned_nodes:
                # Push back to end of queue and try later
                pending_nodes.append(node)
                continue
                
            # Load resource
            res_name = node.get("resource_id") or node.get("resource")
            res = resources.get(res_name) if res_name else None
            
            node_obj = None
            if res:
                model_path = res.get("model") or res.get("mdl")
                master_obj = self.get_or_load_master(context, cm, model_path)
                if master_obj:
                    node_mapping = {}
                    node_obj = self.instance_hierarchy(master_obj, node_mapping)
                    all_mappings.update(node_mapping)
                    
                    # Link to collection
                    self.link_hierarchy_recursive(node_obj, weapons_col)
                    
                    # Apply skin
                    skin_idx = res.get("skin", 0)
                    node_obj["active_skin"] = str(skin_idx)
                    apply_skin(node_obj, skin_idx)
                    
                    # Apply bodygroups
                    res_bgs = res.get("bodygroups", [])
                    if "source_bodygroups_json" in node_obj:
                        try:
                            # Remap source_bodygroups_json: update mesh names from master -> instance
                            name_remap = {old_o.name: new_o.name for old_o, new_o in node_mapping.items()}
                            bgs_json = json.loads(node_obj["source_bodygroups_json"])
                            remapped_bgs = {}
                            for bg_name, mesh_names in bgs_json.items():
                                remapped_bgs[bg_name] = [name_remap.get(n, n) if n else None for n in mesh_names]
                            node_obj["source_bodygroups_json"] = json.dumps(remapped_bgs)
                            
                            bodygroups_data = {}
                            # Build clean mapping
                            res_bgs_map = {bg.get("name", "").lower().replace("_","").replace("-","").strip(): bg.get("value", 0) for bg in res_bgs}
                            for bg_id, name in enumerate(remapped_bgs.keys()):
                                name_clean = name.lower().replace("_","").replace("-","").strip()
                                val = res_bgs_map.get(name_clean, 0)
                                node_obj[f"bg_val_{name}"] = val
                                bodygroups_data[bg_id] = val
                            apply_bodygroups(node_obj, bodygroups_data, None)
                        except Exception as e:
                            print(f"Failed to apply bodygroups for node {node.get('name')}: {e}")
                            
                    # Apply submaterials overrides
                    res_mats = res.get("materials", {})
                    res_submats = res_mats.get("submaterials", {})
                    if res_submats:
                        if isinstance(res_submats, list):
                            for idx, mat_path in enumerate(res_submats):
                                if mat_path:
                                    node_obj[f"gmod_submaterial_{idx}"] = mat_path
                        elif isinstance(res_submats, dict):
                            for idx_str, mat_path in res_submats.items():
                                try:
                                    idx = int(idx_str)
                                    node_obj[f"gmod_submaterial_{idx}"] = mat_path
                                except:
                                    pass
                            
                    node_obj['gmod_model'] = str(model_path)
            else:
                # Node has no resource (e.g. Empty helper)
                node_obj = bpy.data.objects.new(node.get("name", "Node"), None)
                weapons_col.objects.link(node_obj)
            if node_obj:
                pos = node.get("pos")
                ang = node.get("ang")
                if pos and ang:
                    M_local_blender = utils.convert_source_transform(pos, ang, [1, 1, 1], global_scale)
                else:
                    M_local_blender = mathutils.Matrix.Identity(4)
                    
                M_world = weapon_root_obj.matrix_world @ M_local_blender
                node_obj.matrix_world = M_world
                
                parent_obj = spawned_nodes.get(parent_id)
                # Resolve parenting
                if parent_obj:
                    json_parent_type = node.get("parent_type", "OBJECT")
                    parent_bone = node.get("parent_bone")
                    parent_attachment = node.get("parent_attachment")
                    
                    pose_bone = None
                    if parent_obj.type == 'ARMATURE':
                        if json_parent_type == "BONE" and parent_bone:
                            pose_bone = find_matching_bone(parent_obj, parent_bone)
                        elif json_parent_type == "ATTACHMENT" and parent_attachment:
                            pose_bone = find_matching_bone(parent_obj, parent_attachment)
                            
                    node_obj.parent = parent_obj
                    if pose_bone:
                        node_obj.parent_type = 'BONE'
                        node_obj.parent_bone = pose_bone.name
                    else:
                        node_obj.parent_type = 'OBJECT'
                        
                    node_obj.matrix_parent_inverse = mathutils.Matrix.Identity(4)
                    node_obj.matrix_world = M_world
                    print(f"[GModImporter] Parented node {node_obj.name} to {parent_obj.name} (BONE: {pose_bone.name if pose_bone else 'None'})")
                    
                spawned_nodes[node.get("id")] = node_obj
                
        # Remap armature modifiers, constraints and categories for all nodes
        name_remap = {old_o.name: new_o.name for old_o, new_o in all_mappings.items()}
        for old_o, new_o in all_mappings.items():
            if new_o.type == 'MESH':
                for mod in new_o.modifiers:
                    if mod.type == 'ARMATURE' and mod.object in all_mappings:
                        mod.object = all_mappings[mod.object]
            for cons in new_o.constraints:
                if hasattr(cons, "target") and cons.target in all_mappings:
                    cons.target = all_mappings[cons.target]
            if new_o.type == 'ARMATURE' and new_o.pose:
                for bone in new_o.pose.bones:
                    for cons in bone.constraints:
                        if hasattr(cons, "target") and cons.target in all_mappings:
                            cons.target = all_mappings[cons.target]
                            
        # Update view layer first to register parenting
        bpy.context.view_layer.update()
        
        # Apply skeleton poses from GMod raw matrices in top-down order.
        # IMPORTANT: only apply for viewmodel and gmod_hands.
        # C_BaseFlex attachments are already correctly placed by scene node transforms.
        # Applying skeleton to them causes double-offset (root bone world pos ≠ node pos).
        skeletons_data = weapon_data.get("skeletons", {})
        entities_data  = weapon_data.get("entities", {})
        SKELETON_CLASSES = {"viewmodel", "class C_BaseFlex"}  # gmod_hands uses node transform only
        
        if skeletons_data:
            node_depth = {}
            node_parents = {node.get("id"): node.get("parent") for node in nodes}
            
            def get_depth(nid):
                if nid not in node_depth:
                    parent = node_parents.get(nid)
                    if not parent or parent == "node_weapon_root":
                        node_depth[nid] = 0
                    else:
                        node_depth[nid] = 1 + get_depth(parent)
                return node_depth[nid]

            for nid in spawned_nodes:
                get_depth(nid)
                
            sorted_spawned_ids = sorted(spawned_nodes.keys(), key=lambda nid: node_depth.get(nid, 0))
            
            for node_id in sorted_spawned_ids:
                node_obj = spawned_nodes[node_id]
                if not (node_obj and node_obj.type == 'ARMATURE' and node_id in skeletons_data):
                    continue
                
                ent_class = entities_data.get(str(node_id), {}).get("class", "")
                if ent_class not in SKELETON_CLASSES:
                    continue
                    
                try:
                    apply_skeleton_pose(node_obj, skeletons_data[node_id], global_scale, weapon_root_obj, entity_class=ent_class)
                    # After applying pose, hide viewmodel armature bones from viewport
                    # (only gmod_hands skeleton should be visible to the artist)
                    if ent_class == "viewmodel":
                        for bone in node_obj.data.bones:
                            bone.hide = True
                        node_obj.show_in_front = False
                except Exception as e:
                    print(f"Failed to apply skeleton pose to {node_obj.name}: {e}")
                            
        self.kill_phong_globally()
        
        if not context.scene.gmod_skip_materials:
            bpy.ops.gmod.pull_materials_all()
            
        # Restore original settings
        context.scene.gmod_skip_materials = old_skip
        context.scene.gmod_pull_material_mode = old_mode
            
        self.report({'INFO'}, "ARC9 Weapon successfully imported (SSS v2.0)!")
        return {'FINISHED'}

    def execute(self, context):
        import json
        import os
        import math
        import mathutils
        
        if not self.filepath or not os.path.exists(self.filepath):
            self.report({'ERROR'}, f"JSON file path is invalid: {self.filepath}")
            return {'CANCELLED'}
            
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                weapon_data = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to read JSON: {e}")
            return {'CANCELLED'}
            
        # Always rebuild model cache to clear out legacy master models without armatures
        self.clear_import_cache()
        
        # SSS v2.0 format check
        is_v2 = (weapon_data.get("version") == 2 or "resources" in weapon_data)
        if is_v2:
            res = self.execute_v2(context, weapon_data)
            try:
                with open("Z:/gmod_balabanovo/inspect.log", "w", encoding="utf-8") as f:
                    f.write("=== BLENDER SCENE INSPECTION ===\n")
                    for obj in bpy.data.objects:
                        f.write(f"Name: {obj.name}\n")
                        f.write(f"  Type: {obj.type}\n")
                        f.write(f"  Parent: {obj.parent.name if obj.parent else 'None'}\n")
                        f.write(f"  Parent Type: {obj.parent.type if obj.parent else 'None'}\n")
                        f.write(f"  Parent Bone: {obj.parent_bone}\n")
                        f.write(f"  Matrix World Translation: {obj.matrix_world.translation}\n")
                        if obj.type == 'ARMATURE':
                            f.write(f"  Bones in pose: {[b.name for b in obj.pose.bones][:20]}\n")
                        f.write("\n")
                with open("Z:/gmod_balabanovo/inspect_mesh.log", "w", encoding="utf-8") as f:
                    f.write("=== BLENDER MESH INSPECTION ===\n")
                    for obj in bpy.data.objects:
                        if "reciever" in obj.name.lower() and obj.type == 'MESH':
                            f.write(f"Mesh Name: {obj.name}\n")
                            f.write(f"  Parent: {obj.parent.name if obj.parent else 'None'}\n")
                            f.write(f"  Modifiers:\n")
                            for mod in obj.modifiers:
                                f.write(f"    Name: {mod.name}, Type: {mod.type}\n")
                                if mod.type == 'ARMATURE':
                                    f.write(f"      Object: {mod.object.name if mod.object else 'None'}\n")
                            f.write(f"  Vertex Groups: {[vg.name for vg in obj.vertex_groups]}\n")
                            f.write("\n")
            except Exception as e:
                print(f"Inspection failed: {e}")
            return res
            
        base_model_path = weapon_data.get("model")
        if not base_model_path:
            self.report({'ERROR'}, "JSON does not contain a 'model' key for the base weapon!")
            return {'CANCELLED'}
            
        global_scale = context.scene.gmod_global_scale
        
        # Setup Content Manager
        gmod_root = context.scene.gmod_weapon_root_path
        if not gmod_root:
            gmod_root = context.scene.gmod_root_path
            
        if not gmod_root:
            import pathlib
            json_path = pathlib.Path(self.filepath)
            for p in json_path.parents:
                if p.name.lower() == "garrysmod":
                    gmod_root = str(p.parent)
                    break
                
        if not gmod_root or not os.path.exists(gmod_root):
            self.report({'ERROR'}, "GMod Folder is not configured! Please specify your 'GMod Folder' path (e.g. steamapps/common/GarrysMod) in the importer panel first.")
            return {'CANCELLED'}
                
        # Temporarily apply weapon material settings
        old_skip = context.scene.gmod_skip_materials
        old_mode = context.scene.gmod_pull_material_mode
        context.scene.gmod_skip_materials = context.scene.gmod_weapon_skip_materials
        context.scene.gmod_pull_material_mode = context.scene.gmod_weapon_pull_material_mode

        from gmod_scene_importer.SourceIO_adv.library.shared.content_manager import ContentManager
        cm = ContentManager()
        cache_path_str = context.scene.gmod_weapon_cache_path
        if not cache_path_str:
            cache_path_str = context.scene.gmod_cache_path
            
        setup_gmod_mounts(context, cm, TinyPath(gmod_root), override_cache_path=cache_path_str)
        
        # Collections
        main_col = utils.get_or_create_collection("GMOD_SCENE")
        weapons_col = utils.get_or_create_collection("ARC9_Weapons", main_col)
        
        # Load base weapon
        master_obj = self.get_or_load_master(context, cm, base_model_path)
        if not master_obj:
            self.report({'ERROR'}, f"Failed to load base weapon model: {base_model_path}")
            return {'CANCELLED'}
            
        mapping = {}
        new_obj = self.instance_hierarchy(master_obj, mapping)
        if not new_obj:
            self.report({'ERROR'}, "Failed to instance base weapon model")
            return {'CANCELLED'}
            
        # Remap armature modifiers, constraints and categories
        name_remap = {old_o.name: new_o.name for old_o, new_o in mapping.items()}
        for old_o, new_o in mapping.items():
            if new_o.type == 'MESH':
                for mod in new_o.modifiers:
                    if mod.type == 'ARMATURE' and mod.object in mapping:
                        mod.object = mapping[mod.object]
            for cons in new_o.constraints:
                if hasattr(cons, "target") and cons.target in mapping:
                    cons.target = mapping[cons.target]
            if new_o.type == 'ARMATURE' and new_o.pose:
                for bone in new_o.pose.bones:
                    for cons in bone.constraints:
                        if hasattr(cons, "target") and cons.target in mapping:
                            cons.target = mapping[cons.target]
                            
        if "source_bodygroups_json" in new_obj:
            try:
                bgs = json.loads(new_obj["source_bodygroups_json"])
                new_bgs = {}
                for bg_name, mesh_names in bgs.items():
                    new_bgs[bg_name] = [name_remap.get(n, n) if n else None for n in mesh_names]
                new_obj["source_bodygroups_json"] = json.dumps(new_bgs)
                for bg_name in new_bgs.keys():
                    prop_key = f"bg_val_{bg_name}"
                    if prop_key not in new_obj:
                        new_obj[prop_key] = 0
                new_obj.gmod_bg_categories.clear()
                for cat in master_obj.gmod_bg_categories:
                    new_cat = new_obj.gmod_bg_categories.add()
                    new_cat.name = cat.name
                new_obj.gmod_bg_active_category = 0 if len(new_obj.gmod_bg_categories) > 0 else -1
                if "gmod_bg_categories_map" in master_obj:
                    new_obj["gmod_bg_categories_map"] = master_obj["gmod_bg_categories_map"]
            except Exception as e:
                print(f"[GModImporter] Weapon bodygroups remap failed: {e}")
                
        # Link to weapons collection
        self.link_hierarchy_recursive(new_obj, weapons_col)
        
        # Apply positioning to base weapon
        bpy.context.view_layer.update()
        
        tf_matrix = mathutils.Matrix.Identity(4)
        if self.spawn_mode == 'CURSOR':
            tf_matrix.translation = context.scene.cursor.location.copy()
        else:
            tf_matrix.translation = mathutils.Vector((0.0, 0.0, 0.0))
            
        new_obj.matrix_world = tf_matrix
        new_obj['gmod_model'] = str(base_model_path)
        
        # Apply base skin
        base_skin = weapon_data.get("active_skin", 0)
        new_obj["active_skin"] = str(base_skin)
        apply_skin(new_obj, base_skin)
        
        # Apply base bodygroups
        base_bgs = weapon_data.get("bodygroups", {})
        if "source_bodygroups_json" in new_obj:
            try:
                def clean_bg_name(s):
                    return s.lower().replace("ie", "ei").replace("_", "").replace("-", "").strip()
                    
                bgs = json.loads(new_obj["source_bodygroups_json"])
                bodygroups_data = {}
                base_bgs_clean = {clean_bg_name(k): v for k, v in base_bgs.items()}
                for bg_id, name in enumerate(bgs.keys()):
                    name_low = name.lower()
                    name_clean = clean_bg_name(name)
                    
                    val = base_bgs_clean.get(name_clean, 0)
                    
                    # Auto-hide viewport arms/hands helper heuristic
                    if name_low in ["hands", "arms", "valve_arms", "valve_arms_l", "valve_arms_r", "left_arm", "right_arm", "l_hand", "r_hand", "c_hands"] and name_clean not in base_bgs_clean:
                        val = 1
                        
                    new_obj[f"bg_val_{name}"] = val
                    bodygroups_data[bg_id] = val
                apply_bodygroups(new_obj, bodygroups_data, None)
            except Exception as e:
                print(f"Failed to apply base weapon bodygroups: {e}")
                
        # Skip applying GMod bone poses to the weapon armature to prevent skeletal distortion.
        # The weapon armature must remain in its rest pose to keep meshes aligned.
        pass
                
        # Force a view layer update so the posed bones have their matrix properties evaluated
        bpy.context.view_layer.update()
        
        # Calculate bounding box of the base weapon meshes to find the front of the receiver
        front_y = 0.0
        if new_obj:
            objs_to_check = [new_obj] + list(new_obj.children)
            for o in objs_to_check:
                if o.type == 'MESH':
                    for corner in o.bound_box:
                        front_y = max(front_y, corner[1])
        print(f"[GModImporter] Calculated weapon receiver front_y offset: {front_y}")
        
        hands_armatures = []
        
        # Load attachments and bones data
        attachments = weapon_data.get("attachments", [])
        bones_data = weapon_data.get("bones")
        
        def find_armature(o):
            if not o: return None
            if o.type == 'ARMATURE': return o
            if o.parent and o.parent.type == 'ARMATURE': return o.parent
            for child in o.children:
                if child.type == 'ARMATURE': return child
            return None
            
        for att_idx, att in enumerate(attachments):
            att_model_path = att.get("model")
            pos = att.get("pos", [0.0, 0.0, 0.0])
            ang = att.get("ang", [0.0, 0.0, 0.0])
            att_scale = att.get("scale", 1.0)
            att_skin = att.get("active_skin", 0)
            att_bgs = att.get("bodygroups", {})
            
            if not att_model_path: continue
            
            att_master = self.get_or_load_master(context, cm, att_model_path)
            if not att_master:
                print(f"[GModImporter] Failed to load attachment master: {att_model_path}")
                continue
                
            att_mapping = {}
            att_obj = self.instance_hierarchy(att_master, att_mapping)
            if not att_obj: continue
            
            # Remap names and properties
            att_name_remap = {old_o.name: new_o.name for old_o, new_o in att_mapping.items()}
            for old_o, new_o in att_mapping.items():
                if new_o.type == 'MESH':
                    for mod in new_o.modifiers:
                        if mod.type == 'ARMATURE' and mod.object in att_mapping:
                            mod.object = att_mapping[mod.object]
                for cons in new_o.constraints:
                    if hasattr(cons, "target") and cons.target in att_mapping:
                        cons.target = att_mapping[cons.target]
                if new_o.type == 'ARMATURE' and new_o.pose:
                    for bone in new_o.pose.bones:
                        for cons in bone.constraints:
                            if hasattr(cons, "target") and cons.target in att_mapping:
                                cons.target = att_mapping[cons.target]
                                
            # Link to weapons collection
            self.link_hierarchy_recursive(att_obj, weapons_col)
            
            bpy.context.view_layer.update()
            
            # === ARC9: Bone-relative or receiver-relative placement ===
            world_pos = att.get("world_pos")
            world_ang = att.get("world_ang")
            bone_name = att.get("bone")
            
            # Find if parent bone exists in the base weapon armature
            pose_bone = None
            if bone_name and new_obj.type == 'ARMATURE':
                pose_bone = resolve_bone_name_fuzzy(new_obj, bone_name)
                
            if world_pos and world_ang:
                # Convert Source→Blender coordinates (animated world pose of the attachment)
                M_attach_animated = utils.convert_source_transform(world_pos, world_ang, [1.0, 1.0, 1.0], global_scale)
                
                parented_to_bone = False
                if pose_bone:
                    # Calculate relative matrix using the bone's REST matrix in Blender
                    # and the shifted attachment rest matrix to align in Blender rest pose
                    M_attach_rest = M_attach_animated.copy()
                    M_attach_rest.translation.y += front_y
                    
                    M_bone_rest = pose_bone.bone.matrix_local
                    M_local_to_bone = M_bone_rest.inverted() @ M_attach_rest
                    
                    # Parent to bone
                    att_obj.parent = new_obj
                    att_obj.parent_type = 'BONE'
                    att_obj.parent_bone = pose_bone.name
                    att_obj.matrix_parent_inverse = mathutils.Matrix.Identity(4)
                    att_obj.matrix_basis = M_local_to_bone
                    parented_to_bone = True
                    print(f"[GModImporter] Bone-parented attachment {att_obj.name} to bone {pose_bone.name} using rest matrix")
                            
                if not parented_to_bone:
                    # Parent to receiver object directly
                    att_obj.parent = new_obj
                    att_obj.parent_type = 'OBJECT'
                    att_obj.matrix_parent_inverse = mathutils.Matrix.Identity(4)
                    
                    # Apply front_y shift along the Y-axis (forward)
                    M_basis = M_attach_animated.copy()
                    M_basis.translation.y += front_y
                    att_obj.matrix_basis = M_basis
                    print(f"[GModImporter] Object-parented attachment {att_obj.name} directly to receiver with front_y shift: {front_y}")
            else:
                # Fallback: relative to bone using local pos/ang (no world_pos)
                M_local = utils.convert_source_transform(pos, ang, [1.0, 1.0, 1.0], global_scale)
                if pose_bone:
                    att_obj.parent = new_obj
                    att_obj.parent_type = 'BONE'
                    att_obj.parent_bone = pose_bone.name
                    att_obj.matrix_parent_inverse = mathutils.Matrix.Identity(4)
                    att_obj.matrix_basis = M_local
                else:
                    att_obj.parent = new_obj
                    att_obj.parent_type = 'OBJECT'
                    att_obj.matrix_parent_inverse = mathutils.Matrix.Identity(4)
                    att_obj.matrix_basis = M_local
                
            att_obj.scale = mathutils.Vector((att_scale, att_scale, att_scale))
            
            is_hands = "hand" in att_model_path.lower() or "arm" in att_model_path.lower()
            att_armature = find_armature(att_obj)
            if is_hands and att_armature:
                hands_armatures.append(att_armature)
                    
            # Apply skin
            att_obj["active_skin"] = str(att_skin)
            apply_skin(att_obj, att_skin)
            
            # Apply bodygroups
            if "source_bodygroups_json" in att_obj:
                try:
                    def clean_bg_name(s):
                        return s.lower().replace("ie", "ei").replace("_", "").replace("-", "").strip()
                        
                    bgs = json.loads(att_obj["source_bodygroups_json"])
                    bodygroups_data = {}
                    att_bgs_clean = {clean_bg_name(k): v for k, v in (att_bgs or {}).items()}
                    for bg_id, name in enumerate(bgs.keys()):
                        name_low = name.lower()
                        name_clean = clean_bg_name(name)
                        
                        val = att_bgs_clean.get(name_clean, 0)
                        
                        # Auto-hide viewport arms/hands helper heuristic (skip if this attachment is the player arms model itself)
                        is_actual_arms = any(x in att_model_path.lower() for x in ["c_arms", "c_hands", "cl_arms", "hands_"])
                        if name_low in ["hands", "arms", "valve_arms", "valve_arms_l", "valve_arms_r", "left_arm", "right_arm", "l_hand", "r_hand", "c_hands"] and name_clean not in att_bgs_clean and not is_actual_arms:
                            val = 1
                            
                        att_obj[f"bg_val_{name}"] = val
                        bodygroups_data[bg_id] = val
                    apply_bodygroups(att_obj, bodygroups_data, None)
                except Exception as e:
                    print(f"Failed to apply attachment bodygroups: {e}")
                    
            att_obj['gmod_model'] = str(att_model_path)
            
        # Update view layer first to register parenting and parent-inverse matrices
        bpy.context.view_layer.update()
        
        # Now apply bone poses to hands to move them into posed space
        bones_data = weapon_data.get("bones")
        if bones_data:
            # The bone coordinates are already relative to the weapon base origin [0,0,0], so scene_origin must be [0,0,0]
            for hands_arm in hands_armatures:
                try:
                    apply_bone_poses(hands_arm, bones_data, scene_origin=[0.0, 0.0, 0.0], global_scale=0.0254, is_weapon=False)
                except Exception as e:
                    print(f"Failed to apply hands bone poses: {e}")
                    
        self.kill_phong_globally()
        
        if not context.scene.gmod_skip_materials:
            bpy.ops.gmod.pull_materials_all()
            
        # Restore original settings
        context.scene.gmod_skip_materials = old_skip
        context.scene.gmod_pull_material_mode = old_mode
            
        self.report({'INFO'}, "ARC9 Weapon successfully imported!")
        return {'FINISHED'}
