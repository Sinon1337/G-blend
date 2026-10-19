import bpy
import os

class GMOD_PT_ImportPanel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "GMod Scene Importer"
    bl_idname = "GMOD_PT_import"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "GMod Tools"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        layout.prop(scene, "gmod_json_path", text="Scene JSON")
        layout.prop(scene, "gmod_root_path", text="GMod Folder")
        layout.prop(scene, "gmod_mount_css_hl2") # Toggle Standard Games
        
        layout.separator()
        
        box = layout.box()
        box.label(text="Workshop Cache (HD / Missing)")
        box.prop(context.scene, "gmod_workshop_path", text="Workshop Content")
        box.prop(context.scene, "gmod_cache_path", text="Cache Storage")
        from . import operators_cache
        active_cache = operators_cache.WorkshopCacheManager.get_cache_path(context)
        box.label(text=f"Active: {active_cache}", icon='FILE_FOLDER')
        box.prop(context.scene, "gmod_cache_workers")
        
        row = box.row()
        row.operator("gmod.scan_workshop", icon='FILE_REFRESH', text="Scan GMAs")
        row.operator("gmod.open_cache", icon='FOLDER_REDIRECT', text="Open Cache")
        row.operator("gmod.clear_cache", icon='TRASH', text="Clear")
        
        
        layout.separator()
        layout.label(text="Options:")
        layout.prop(scene, "gmod_replace_cameras")
        row_skip = layout.row(align=True)
        row_skip.prop(scene, "gmod_skip_materials")
        row_skip.operator("gmod.pull_materials_all", text="ALL", icon='MATERIAL')
        row_skip.operator("gmod.pull_materials_selected", text="1", icon='MATERIAL')
        
        row_mode = layout.row()
        row_mode.prop(scene, "gmod_pull_material_mode", text="")
        layout.prop(scene, "gmod_ignore_empty_bodygroups")
        layout.prop(scene, "gmod_import_rotation")
        layout.prop(scene, "gmod_global_scale")
        
        layout.separator()

        layout.separator()
        op = layout.operator("gmod.import_scene", text="Import Scene", icon='IMPORT')
        op.filepath = scene.gmod_json_path
        op.gmod_root = scene.gmod_root_path
        op.clear_scene = scene.gmod_clear_scene
        
class GMOD_PT_ARC9WeaponPanel(bpy.types.Panel):
    """Creates a Panel in the Object properties window for weapons"""
    bl_label = "ARC9 Weapon Importer"
    bl_idname = "GMOD_PT_arc9_weapon"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "GMod Tools"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        layout.prop(scene, "gmod_weapon_root_path", text="GMod Folder")
        layout.prop(scene, "gmod_weapon_json_path", text="Weapon JSON")
        layout.prop(scene, "gmod_weapon_spawn_mode", text="Spawn Mode")
        
        layout.separator()
        
        box = layout.box()
        box.label(text="Workshop Cache (HD / Missing)")
        box.prop(scene, "gmod_weapon_cache_path", text="Cache Storage")
        from . import operators_cache
        active_w_cache = operators_cache.WorkshopCacheManager.get_cache_path(context, is_weapon=True)
        box.label(text=f"Active: {active_w_cache}", icon='FILE_FOLDER')
        
        row = box.row()
        op_scan = row.operator("gmod.scan_workshop", icon='FILE_REFRESH', text="Scan GMAs")
        op_scan.is_weapon = True
        op_open = row.operator("gmod.open_cache", icon='FOLDER_REDIRECT', text="Open Cache")
        op_open.is_weapon = True
        op_clear = row.operator("gmod.clear_cache", icon='TRASH', text="Clear")
        op_clear.is_weapon = True
        
        layout.separator()
        layout.label(text="Options:")
        
        row_skip = layout.row(align=True)
        row_skip.prop(scene, "gmod_weapon_skip_materials", text="Skip Materials")
        op_pull_all = row_skip.operator("gmod.pull_materials_all", text="ALL", icon='MATERIAL')
        op_pull_all.is_weapon = True
        op_pull_sel = row_skip.operator("gmod.pull_materials_selected", text="1", icon='MATERIAL')
        op_pull_sel.is_weapon = True
        
        row_mode = layout.row()
        row_mode.prop(scene, "gmod_weapon_pull_material_mode", text="")
        
        row_hands = layout.row()
        row_hands.prop(scene, "gmod_weapon_import_hands", text="Import Hands Model")
        
        layout.separator()
        
        op_w = layout.operator("gmod.import_weapon", text="Import ARC9 Weapon", icon='IMPORT')
        op_w.filepath = scene.gmod_weapon_json_path
        op_w.spawn_mode = scene.gmod_weapon_spawn_mode

class GMOD_PT_LiveLinkPanel(bpy.types.Panel):
    """Creates a Panel in the GMod Tools tab for Live Link"""
    bl_label = "GMod Live Link"
    bl_idname = "GMOD_PT_livelink"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "GMod Tools"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        layout.prop(scene, "gmod_livelink_port", text="Server Port")
        
        # Auto-detect local IP address dynamically
        local_ip = "127.0.0.1"
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            pass
            
        box_ip = layout.box()
        box_ip.label(text="Local Network IP:")
        box_ip.label(text=local_ip, icon='NETWORK_DRIVE')
        
        layout.separator()
        
        active = getattr(scene, "gmod_livelink_active", False)
        if active:
            row = layout.row()
            row.label(text="Status: ACTIVE", icon='RADIOBUT_ON')
            layout.operator("gmod.stop_livelink_server", text="Stop Live Link", icon='CANCEL')
            
            row_rec = layout.row()
            row_rec.prop(scene, "gmod_livelink_record", text="Record Motion Capture", icon='REC')
            
            layout.separator()
            box_gmod = layout.box()
            box_gmod.label(text=f"Packets Recv: {getattr(scene, 'gmod_livelink_packets_recv', 0)}", icon='INFO')
            box_gmod.label(text="Run in GMod Console:", icon='CONSOLE')
            box_gmod.label(text=f"gmod_livelink_host {local_ip}")
            box_gmod.label(text=f"gmod_livelink_port {scene.gmod_livelink_port}")
            
            box_gmod.label(text="--- Dedicated Server ---")
            box_gmod.label(text="gmod_livelink_server_start")
            
            box_gmod.label(text="--- Client / Singleplayer ---")
            box_gmod.label(text="gmod_livelink_start")
            
            # Live logs view
            from gmod_scene_importer.operators_livelink import LIVELINK_LOGS
            if LIVELINK_LOGS:
                box_logs = layout.box()
                box_logs.label(text="Live Logs:", icon='TEXT')
                for log in LIVELINK_LOGS[-5:]:
                    box_logs.label(text=log)
        else:
            row = layout.row()
            row.label(text="Status: OFF", icon='RADIOBUT_OFF')
            layout.operator("gmod.start_livelink_server", text="Start Live Link", icon='PLAY')
            
        layout.separator()
        
        # Dedicated Server Launcher Section
        box_srv = layout.box()
        box_srv.label(text="Dedicated Server Launcher", icon='CONSOLE')
        
        # Show GMod folder specifically for Live Link server
        if hasattr(scene, "gmod_livelink_root_path"):
            box_srv.prop(scene, "gmod_livelink_root_path", text="Folder (with srcds.exe)")
            
        if hasattr(scene, "gmod_livelink_server_map"):
            box_srv.prop(scene, "gmod_livelink_server_map", text="Server Map")
        else:
            box_srv.label(text="Re-enable addon to show inputs", icon='ERROR')
            
        box_srv.operator("gmod.launch_srcds", text="Launch Server", icon='PLAY')
        
        row_spawn = box_srv.row()
        row_spawn.enabled = scene.gmod_livelink_active
        row_spawn.operator("gmod.spawn_operator", text="Spawn Operator Entity", icon='OUTLINER_OB_CAMERA')

        layout.separator()
        
        # Live Link Map Import Settings
        box_map = layout.box()
        box_map.label(text="Map Settings", icon='WORLD')
        box_map.prop(scene, "gmod_livelink_load_map")
        box_map.prop(scene, "gmod_livelink_auto_refine")
        box_map.prop(scene, "gmod_livelink_hide_player_meshes")
        box_map.prop(scene, "gmod_livelink_hide_hitboxes")
        box_map.prop(scene, "gmod_livelink_sync_viewport")
        
        if scene.gmod_livelink_map_loaded:
            box_map.label(text=f"Loaded Map: {scene.gmod_livelink_map_loaded}", icon='CHECKMARK')
            box_map.prop(scene, "gmod_livelink_map_hide")
        box_map.prop(scene, "gmod_cache_path", text="Cache Storage")
        row_clear = box_map.row()
        row_clear.operator("gmod.clear_cache", icon='TRASH', text="Clear Cache")
        
        # Borrowed material options
        row_skip = box_map.row(align=True)
        row_skip.prop(scene, "gmod_skip_materials", text="Skip Materials")
        row_skip.operator("gmod.pull_materials_all", text="ALL", icon='MATERIAL')
        row_skip.operator("gmod.pull_materials_selected", text="1", icon='MATERIAL')
        
        row_mode = box_map.row()
        row_mode.prop(scene, "gmod_pull_material_mode", text="")
        
        # Refinement & Alignment buttons
        row_refine = box_map.row(align=True)
        row_refine.operator("gmod.refine_from_cache", text="Replace Cube with Model", icon='FILE_REFRESH')
        row_refine.operator("gmod.align_origin_with_map", text="Align Origin with Map", icon='CENTER_ONLY')
        
        # Active selected prop settings
        obj = context.active_object
        if obj and obj.get("gmod_id") is not None:
            box_prop = layout.box()
            box_prop.label(text=f"Selected Prop (ID {obj['gmod_id']})", icon='OBJECT_DATA')
            box_prop.prop(obj, "gmod_physics_frozen", text="Freeze Physics (GMod)", icon='FREEZE')

class GMOD_UL_BodygroupCategories(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "name", text="", emboss=False, icon='GROUP')
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='GROUP')

class GMOD_PT_BodygroupsPanel(bpy.types.Panel):
    bl_label = "Bodygroup Manager"
    bl_idname = "GMOD_PT_bodygroups"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Bodygroups"
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        # 0. Find attached objects (bonemerged entities)
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

        # 1. Determine active category name and target object
        active_cat_name = None
        if (len(obj.gmod_bg_categories) > 0
                and 0 <= obj.gmod_bg_active_category < len(obj.gmod_bg_categories)):
            active_cat_name = obj.gmod_bg_categories[obj.gmod_bg_active_category].name
            
        target_obj = obj
        is_attached_target = False
        import os
        
        if active_cat_name:
            for att in attached:
                disp_name = att.name
                if 'gmod_model' in att:
                    disp_name = os.path.basename(att['gmod_model']).replace('.mdl', '')
                if active_cat_name == disp_name or active_cat_name == att.name:
                    target_obj = att
                    is_attached_target = True
                    break

        # 2. Draw Categories list at the top (always on the active character object)
        row = layout.row()
        row.template_list("GMOD_UL_BodygroupCategories", "", obj, "gmod_bg_categories", obj, "gmod_bg_active_category", rows=3)
        col = row.column(align=True)
        col.operator("gmod.add_category", icon='ADD', text="")
        col.operator("gmod.remove_category", icon='REMOVE', text="")
        
        layout.separator()

        # --- Skin Selection UI ---
        skin_groups = target_obj.get("skin_groups", None)
        if not skin_groups:
            for child in target_obj.children:
                if child.type == 'MESH' and "skin_groups" in child and child["skin_groups"]:
                    skin_groups = child["skin_groups"]
                    break
                    
        if skin_groups and len(skin_groups) > 1:
            active_skin_str = target_obj.get("active_skin", "0")
            try:
                active_skin_idx = int(active_skin_str)
            except:
                active_skin_idx = 0
            max_skin = len(skin_groups) - 1
            
            box_s = layout.box()
            box_s.label(text="Skin Family", icon='MATERIAL')
            row_skin = box_s.row(align=True)
            
            op_prev = row_skin.operator("gmod.set_skin", text="<")
            op_prev.skin_val = active_skin_idx - 1
            op_prev.max_val = max_skin
            op_prev.obj_name = target_obj.name
            
            row_skin.label(text=f"       {active_skin_idx} / {max_skin}")
            
            op_next = row_skin.operator("gmod.set_skin", text=">")
            op_next.skin_val = active_skin_idx + 1
            op_next.max_val = max_skin
            op_next.obj_name = target_obj.name
            
        # Show origin/model source if available
        loaded_origin = target_obj.get("gmod_loaded_from") or (obj.get("gmod_loaded_from") if obj != target_obj else None)
        model_name = target_obj.get("gmod_model") or (obj.get("gmod_model") if obj != target_obj else None)
        if loaded_origin or model_name:
            box_info = layout.box()
            if model_name:
                box_info.label(text=f"Model: {model_name.split('/')[-1]}", icon='OBJECT_DATA')
            if loaded_origin:
                box_info.label(text=f"Source: {loaded_origin}", icon='INFO')

        # 3. Load bodygroups for the target object
        if "source_bodygroups_json" not in target_obj:
            # Check if this is a placeholder with a missing model
            if "missing_model" in target_obj:
                box = layout.box()
                box.alert = True
                box.label(text="⚠ Missing Model:", icon='ERROR')
                missing = target_obj["missing_model"]
                parts = missing.split('/')
                model_name = parts[-1] if parts else missing
                box.label(text=model_name)
                box.label(text=f"Path: .../{'/'.join(parts[-3:-1])}/")
                box.operator("gmod.retry_missing", text="Retry Load", icon='FILE_REFRESH')
                box.operator("gmod.browse_and_load_mdl", text="Browse MDL...", icon='FILE_FOLDER')
            else:
                layout.label(text="Not initialized for bodygroups")
                layout.operator("gmod.init_bodygroups", text="Initialize Bodygroup System", icon="FILE_REFRESH")
            return
            
        import json
        try:
            bgs = json.loads(target_obj["source_bodygroups_json"])
        except:
            layout.label(text="Error parsing bodygroups")
            return

        if is_attached_target:
            # For attached objects, show all bodygroups in a flat list
            layout.label(text=f"--- {active_cat_name} Bodygroups ---")
            for bg_id, (bg_name, options) in enumerate(bgs.items()):
                if not options: options = ["None"]
                box = layout.box()
                split = box.split(factor=0.4)
                
                prop_name = f"bg_val_{bg_name}"
                try: current_val = int(target_obj.get(prop_name, 0))
                except: current_val = 0
                
                if current_val < 0: current_val = 0
                if current_val >= len(options): current_val = len(options) - 1
                opt_name = options[current_val] if options else "None"
                if opt_name is None: opt_name = "Blank"
                
                short_bg = bg_name[:12] + ".." if len(bg_name) > 14 else bg_name
                short_opt = opt_name[:12] + ".." if len(opt_name) > 14 else opt_name
                split.label(text=f"{short_bg}: {short_opt}")
                
                row_ctrl = split.row(align=True)
                op_prev = row_ctrl.operator("gmod.set_bodygroup", text="<")
                op_prev.bg_name = bg_name
                op_prev.bg_val = current_val - 1
                op_prev.max_val = len(options) - 1
                op_prev.obj_name = target_obj.name
                
                row_ctrl.label(text=str(current_val))
                
                op_next = row_ctrl.operator("gmod.set_bodygroup", text=">")
                op_next.bg_name = bg_name
                op_next.bg_val = current_val + 1
                op_next.max_val = len(options) - 1
                op_next.obj_name = target_obj.name
        else:
            # Draw standard UI for character bodygroups (with categories and uncategorized navigation)
            bg_cat_map = {}
            if "gmod_bg_categories_map" in obj:
                try: bg_cat_map = json.loads(obj["gmod_bg_categories_map"])
                except: pass
                
            nav_row = layout.row(align=True)
            is_uncat = (len(obj.gmod_bg_categories) == 0 or obj.gmod_bg_active_category < 0
                        or obj.gmod_bg_active_category >= len(obj.gmod_bg_categories))
            uncat_op = nav_row.operator("gmod.select_uncategorized", text="Uncategorized",
                                        depress=is_uncat, icon='QUESTION')
            
            if active_cat_name:
                layout.label(text=f"--- {active_cat_name} ---")
            else:
                layout.label(text="--- Uncategorized ---")
                
            for bg_id, (bg_name, options) in enumerate(bgs.items()):
                cat_assigned = bg_cat_map.get(bg_name)
                if active_cat_name:
                    if cat_assigned != active_cat_name: continue
                else:
                    existing_cat_names = [c.name for c in obj.gmod_bg_categories]
                    if cat_assigned in existing_cat_names: continue
                    
                if not options: options = ["None"]
                
                box = layout.box()
                split = box.split(factor=0.4)
                
                prop_name = f"bg_val_{bg_name}"
                try: current_val = int(obj.get(prop_name, 0))
                except: current_val = 0
                
                if current_val < 0: current_val = 0
                if current_val >= len(options): current_val = len(options) - 1
                opt_name = options[current_val] if options else "None"
                if opt_name is None: opt_name = "Blank"
                
                short_bg = bg_name[:12] + ".." if len(bg_name) > 14 else bg_name
                short_opt = opt_name[:12] + ".." if len(opt_name) > 14 else opt_name
                split.label(text=f"{short_bg}: {short_opt}")
                
                row_ctrl = split.row(align=True)
                op_prev = row_ctrl.operator("gmod.set_bodygroup", text="<")
                op_prev.bg_name = bg_name
                op_prev.bg_val = current_val - 1
                op_prev.max_val = len(options) - 1
                op_prev.obj_name = obj.name
                
                row_ctrl.label(text=str(current_val))
                
                op_next = row_ctrl.operator("gmod.set_bodygroup", text=">")
                op_next.bg_name = bg_name
                op_next.bg_val = current_val + 1
                op_next.max_val = len(options) - 1
                op_next.obj_name = obj.name
                
                op_assign = row_ctrl.operator("gmod.assign_category", icon='MODIFIER', text="")
                op_assign.bg_name = bg_name
                
                if "Custom" in bg_name or bg_name == context.scene.gmod_custom_bg_name or (options[0] and "Custom" in str(options[0])):
                    op_del = row_ctrl.operator("gmod.delete_custom_bg", icon='X', text="")
                    op_del.bg_name = bg_name
                    
            layout.separator()
            box = layout.box()
            box.label(text="Create Custom Bodygroup:")
            row_create = box.row(align=True)
            row_create.prop(context.scene, "gmod_custom_bg_name", text="")
            row_create.operator("gmod.create_custom_bodygroup", text="Add Selected", icon='PLUS')
        
        # --- ATTACHED OBJECTS (Bonemerged Clothing) ---
        # Find armature children (bonemerged entities)
        attached = []
        
        # The obj might be an armature, or we need to find the armature root
        root = obj
        while root.parent:
            root = root.parent
        
        def collect_attached(o, depth=0):
            for child in o.children:
                if child.type == 'ARMATURE' and child != obj:
                    attached.append(child)
                else:
                    collect_attached(child, depth + 1)
        
        collect_attached(root)
        
        if attached:
            layout.separator()
            att_box = layout.box()
            att_header = att_box.row()
            att_header.label(text="--- Attached Objects ---", icon='LINKED')
            for att_obj in attached:
                row_att = att_box.row(align=True)
                
                # Check if it has bodygroups, to render collapse/expand toggle
                has_bgs = "source_bodygroups_json" in att_obj
                if has_bgs:
                    icon_toggle = 'TRIA_DOWN' if att_obj.show_bg_ui else 'TRIA_RIGHT'
                    row_att.prop(att_obj, "show_bg_ui", text="", icon=icon_toggle, emboss=False)
                else:
                    row_att.label(text="", icon='BLANK1')
                
                # Eye toggle (Visibility)
                icon = 'HIDE_ON' if att_obj.hide_viewport else 'HIDE_OFF'
                op_vis = row_att.operator("gmod.toggle_visibility", text="", icon=icon, emboss=False)
                op_vis.obj_name = att_obj.name
                
                # Name (shortened)
                disp_name = att_obj.name
                # Strip prefixes like "CACHE:hash_" for readability
                if 'gmod_model' in att_obj:
                    mdl = att_obj['gmod_model']
                    disp_name = os.path.basename(mdl).replace('.mdl', '')
                short_name = disp_name[:18] + ".." if len(disp_name) > 20 else disp_name
                row_att.label(text=short_name)
                
                # Render toggle
                icon_ren = 'RESTRICT_RENDER_ON' if att_obj.hide_render else 'RESTRICT_RENDER_OFF'
                op_ren = row_att.operator("gmod.toggle_render_visibility", text="", icon=icon_ren, emboss=False)
                op_ren.obj_name = att_obj.name
                
                if has_bgs and att_obj.show_bg_ui:
                    try:
                        import json
                        att_bgs = json.loads(att_obj["source_bodygroups_json"])
                        bg_box = att_box.box()
                        for bg_name, options in att_bgs.items():
                            if not options: options = ["None"]
                            prop_name = f"bg_val_{bg_name}"
                            try: current_val = int(att_obj.get(prop_name, 0))
                            except: current_val = 0
                            
                            if current_val < 0: current_val = 0
                            if current_val >= len(options): current_val = len(options) - 1
                            opt_name = options[current_val] if options else "None"
                            if opt_name is None: opt_name = "Blank"
                            
                            bg_row = bg_box.row()
                            split_bg = bg_row.split(factor=0.5)
                            short_bg_name = bg_name[:12] + ".." if len(bg_name) > 14 else bg_name
                            short_opt_name = opt_name[:12] + ".." if len(opt_name) > 14 else opt_name
                            split_bg.label(text=f"{short_bg_name}: {short_opt_name}")
                            
                            ctrl_bg = split_bg.row(align=True)
                            op_prev = ctrl_bg.operator("gmod.set_bodygroup", text="<")
                            op_prev.bg_name = bg_name
                            op_prev.bg_val = current_val - 1
                            op_prev.max_val = len(options) - 1
                            op_prev.obj_name = att_obj.name
                            
                            ctrl_bg.label(text=str(current_val))
                            
                            op_next = ctrl_bg.operator("gmod.set_bodygroup", text=">")
                            op_next.bg_name = bg_name
                            op_next.bg_val = current_val + 1
                            op_next.max_val = len(options) - 1
                            op_next.obj_name = att_obj.name
                    except Exception as e:
                        att_box.label(text=f"Error drawing BGs: {e}")

class GMOD_PT_BoneMergePanel(bpy.types.Panel):
    bl_label = "Bone Merge Tool"
    bl_idname = "GMOD_PT_bonemerge"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Bodygroups"
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def draw(self, context):
        layout = self.layout
        layout.label(text="1. Select clothing/weapons")
        layout.label(text="2. Shift-Select Character (Armature)")
        layout.operator("gmod.bone_merge", icon='LINKED')

class GMOD_PT_AttachedObjectsPanel(bpy.types.Panel):
    bl_label = "Attached Objects (Visibility)"
    bl_idname = "GMOD_PT_attached_objects"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Bodygroups"
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        child_objs = [c for c in obj.children if c.type in {'MESH', 'ARMATURE', 'EMPTY', 'LIGHT', 'CAMERA'}]
        
        if not child_objs:
            layout.label(text="No attached objects found.")
            return
            
        box = layout.box()
        for child in child_objs:
            row = box.row()
            icon = 'OUTLINER_OB_MESH'
            if child.type == 'ARMATURE': icon = 'OUTLINER_OB_ARMATURE'
            elif child.type == 'EMPTY': icon = 'OUTLINER_OB_EMPTY'
            elif child.type == 'LIGHT': icon = 'OUTLINER_OB_LIGHT'
            elif child.type == 'CAMERA': icon = 'OUTLINER_OB_CAMERA'
            
            row_op = row.row(align=True)
            op_add = row_op.operator("gmod.move_to_bodygroup", text="", icon='ADD', emboss=False)
            op_add.obj_name = child.name
            
            row.label(text=child.name, icon=icon)
            
            # Viewport Toggle
            is_hidden = child.hide_viewport or child.hide_get()
            icon_view = 'RESTRICT_VIEW_ON' if is_hidden else 'RESTRICT_VIEW_OFF'
            op_view = row.operator("gmod.toggle_visibility", text="", icon=icon_view, emboss=False)
            op_view.obj_name = child.name
            
            # Render Toggle
            icon_render = 'RESTRICT_RENDER_ON' if child.hide_render else 'RESTRICT_RENDER_OFF'
            op_render = row.operator("gmod.toggle_render_visibility", text="", icon=icon_render, emboss=False)
            op_render.obj_name = child.name
        
