bl_info = {
    "name": "GMod Scene Importer",
    "author": "Prosvet 3-2",
    "version": (1, 194),
    "blender": (4, 1, 0),
    "location": "View3D > Sidebar > GMod",
    "description": "Imports JSON scenes from GMod with Workshop Cache support",
    "warning": "",
    "wiki_url": "",
    "category": "Import-Export",
}

import sys
import os
import bpy
import importlib

# Add the addon directory to sys.path so SourceIO_adv absolute imports work
# addon_dir = os.path.dirname(os.path.realpath(__file__))
# if addon_dir not in sys.path:
#     sys.path.insert(0, addon_dir)

# Submodules
from . import utils
from . import gma_reader
from . import operators_cache
from . import operators_pull_materials
from . import operators_livelink
from . import operators
from . import ui

# Force reload of all submodules during development
importlib.reload(utils)
importlib.reload(gma_reader)
importlib.reload(operators_cache)
importlib.reload(operators_pull_materials)
importlib.reload(operators_livelink)
importlib.reload(operators)
importlib.reload(ui)

class GModBGCategoryItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name", default="Category")

classes = (
    GModBGCategoryItem,
    operators.ImportGModScene,
    operators.GModImportARC9RuntimeOperator,
    operators.GModMountResource,
    operators.GModBoneMergeOperator,
    operators.GModCreateCustomBodygroupOperator,
    operators.GModInitBodygroupsOperator,
    operators.GModSetBodygroupOperator,
    operators.GModSetSkinOperator,
    operators.GModToggleVisibilityOperator,
    operators.GModToggleRenderVisibilityOperator,
    operators_pull_materials.GModPullMaterialsAllOperator,
    operators_pull_materials.GModPullMaterialsSelectedOperator,
    operators.GModAddCategoryOperator,
    operators.GModRemoveCategoryOperator,
    operators.GModAssignCategoryOperator,
    operators.GModMoveToBodygroupOperator,
    operators.GModSelectUncategorized,
    operators.GModDeleteCustomBGOps,
    operators.GModFixMaterials,
    operators.GModRefineFromCache,
    operators.GModRetryMissing,
    operators.GModBrowseAndLoadMdl,
    operators_cache.GModScanWorkshop,
    operators_cache.GModClearCache,
    operators_cache.GModDumpIndex,
    ui.GMOD_PT_ImportPanel,
    ui.GMOD_PT_ARC9WeaponPanel,
    ui.GMOD_PT_LiveLinkPanel,
    ui.GMOD_UL_BodygroupCategories,
    ui.GMOD_PT_BodygroupsPanel,
    ui.GMOD_PT_BoneMergePanel,
    ui.GMOD_PT_AttachedObjectsPanel,
    operators_livelink.GModStartLiveLinkServer,
    operators_livelink.GModStopLiveLinkServer,
    operators_livelink.GModLaunchDedicatedServer,
    operators_livelink.GModSpawnOperator,
    operators_livelink.GModAlignOriginWithMap,
)

@bpy.app.handlers.persistent
def gmod_selection_change_handler(scene, depsgraph=None):
    import bpy
    import os
    
    obj = bpy.context.active_object
    if not obj or obj.type != 'ARMATURE':
        return
        
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
    
    target = ["Source Bodygroups"]
    existing = [item.name for item in obj.gmod_bg_categories]
    
    attached_names = set()
    for att in attached:
        disp_name = att.name
        if 'gmod_model' in att:
            disp_name = os.path.basename(att['gmod_model']).replace('.mdl', '')
        attached_names.add(disp_name)
        
    for name in existing:
        if name != "Source Bodygroups" and name not in attached_names:
            target.append(name)
            
    for att in attached:
        disp_name = att.name
        if 'gmod_model' in att:
            disp_name = os.path.basename(att['gmod_model']).replace('.mdl', '')
        target.append(disp_name)
        
    if existing != target:
        active_name = None
        if 0 <= obj.gmod_bg_active_category < len(obj.gmod_bg_categories):
            active_name = obj.gmod_bg_categories[obj.gmod_bg_active_category].name
            
        obj.gmod_bg_categories.clear()
        for name in target:
            item = obj.gmod_bg_categories.add()
            item.name = name
            
        if active_name:
            for idx, item in enumerate(obj.gmod_bg_categories):
                if item.name == active_name:
                    obj.gmod_bg_active_category = idx
                    break

def register():
    bpy.app.handlers.depsgraph_update_post.append(gmod_selection_change_handler)
    for cls in classes:
        bpy.utils.register_class(cls)
        
    bpy.types.Scene.gmod_custom_bg_name = bpy.props.StringProperty(
        name="Name",
        description="Name of the custom bodygroup (e.g. 'Custom_Hat')",
        default="Custom_Hat"
    )
    
    bpy.types.Object.gmod_bg_categories = bpy.props.CollectionProperty(type=GModBGCategoryItem)
    bpy.types.Object.gmod_bg_active_category = bpy.props.IntProperty(name="Active Category Index", default=-1, min=-1)
    bpy.types.Object.show_bg_ui = bpy.props.BoolProperty(name="Show Bodygroup UI", default=False)
        
    # Check if the user has a global SourceIO enabled
    global_sourceio_installed = False
    try:
        import SourceIO
        global_sourceio_installed = True
        print("[GModImporter] User has a global SourceIO enabled. Skipping SourceIO_adv UI registration.")
    except ImportError:
        pass
        
    # Only register SourceIO_adv UI if the user does NOT have SourceIO enabled
    if not global_sourceio_installed:
        try:
            from gmod_scene_importer.SourceIO_adv.blender_bindings.bindings import register as sio_register
            sio_register()
            print("[GModImporter] Registered SourceIO_adv UI.")
        except Exception as e:
            print(f"[GModImporter] Failed to register SourceIO_adv UI: {e}")
            
    # Always register properties for SourceIO_adv so the backend works
    try:
        from gmod_scene_importer.SourceIO_adv.blender_bindings.attributes import register_props
        register_props()
    except Exception as e:
        print(f"[GModImporter] Failed to register SourceIO_adv props: {e}")
        
    bpy.types.Scene.gmod_json_path = bpy.props.StringProperty(
        name="Scene JSON",
        description="Path to the JSON file exported from GMod",
        subtype='FILE_PATH'
    )
    
    bpy.types.Scene.gmod_root_path = bpy.props.StringProperty(
        name="GMod Root",
        description="Path to GarrysMod directory (e.g. steamapps/common/GarrysMod)",
        subtype='DIR_PATH'
    )
    
    bpy.types.Scene.gmod_workshop_path = bpy.props.StringProperty(
        name="Workshop Content",
        description="Path to steamapps/workshop/content/4000",
        subtype='DIR_PATH'
    )
    
    bpy.types.Scene.gmod_cache_path = bpy.props.StringProperty(
        name="Workshop Cache",
        description="Folder to extract and store Workshop assets",
        subtype='DIR_PATH'
    )
    
    bpy.types.Scene.gmod_cache_workers = bpy.props.IntProperty(
        name="Extraction Threads",
        description="Number of threads for GMA extraction (Multithreading)",
        default=8,
        min=1,
        max=32
    )
    
    bpy.types.Scene.gmod_clear_scene = bpy.props.BoolProperty(
        name="Clear Existing Scene",
        description="Remove all objects in GMOD_SCENE collection before importing",
        default=True
    )
    
    bpy.types.Scene.gmod_mount_css_hl2 = bpy.props.BoolProperty(
        name="Mount Standard Games (HL2/CSS)",
        description="If disabled, import will ONLY use Workshop Cache. Use this to force HD replacements or debug missing cache files.",
        default=True
    )
    
    bpy.types.Scene.gmod_skip_materials = bpy.props.BoolProperty(
        name="Skip Materials",
        description="Only import geometry, do not load materials or textures (Fast)",
        default=False
    )
    
    bpy.types.Scene.gmod_ignore_empty_bodygroups = bpy.props.BoolProperty(
        name="Ignore Empty Bodygroups",
        description="If GMod exports no bodygroups for an entity, do not hide any meshes (fixes overlapping, but restores 1.8 behavior)",
        default=True
    )
    
    bpy.types.Scene.gmod_replace_cameras = bpy.props.BoolProperty(
        name="Replace GMod Cameras",
        description="Replace camera props with actual Blender cameras",
        default=True
    )
    
    bpy.types.Scene.gmod_import_rotation = bpy.props.EnumProperty(
        name="Global Rotation",
        description="Rotates the entire imported scene around Z",
        items=[
            ('0', "0° (As Is)", "No additional rotation"),
            ('-90', "-90° (Standard)", "Rotate -90° Z (Fixes typical sideways import)"),
            ('90', "90°", "Rotate +90° Z"),
            ('180', "180°", "Rotate 180° Z"),
        ],
        default='-90'
    )
    
    bpy.types.Scene.gmod_pull_material_mode = bpy.props.EnumProperty(
        name="Pull Material Mode",
        description="Type of shader to use when pulling materials",
        items=[
            ("PRINCIPLED", "Blender Principled (Simple)", "Use basic Blender Principled BSDF shader"),
            ("SOURCEIO", "SourceIO Node (Advanced)", "Use custom SourceIO complex shader nodes"),
        ],
        default="PRINCIPLED"
    )
    
    bpy.types.Scene.gmod_global_scale = bpy.props.FloatProperty(
        name="Global Scale",
        description="Scale factor for the imported scene and models (default 0.0254 matches Garry's Mod source units to meters)",
        default=0.0254,
        min=0.0001,
        max=1000.0,
        precision=4
    )

    bpy.types.Scene.gmod_weapon_json_path = bpy.props.StringProperty(
        name="Weapon JSON",
        description="Path to the exported ARC9 weapon JSON file",
        subtype='FILE_PATH'
    )

    bpy.types.Scene.gmod_weapon_spawn_mode = bpy.props.EnumProperty(
        name="Spawn Position",
        description="Where to spawn the imported weapon in the Blender scene",
        items=[
            ('ORIGIN', "World Origin (0,0,0)", "Place the weapon at the world center"),
            ('CURSOR', "3D Cursor", "Place the weapon at the 3D cursor position"),
        ],
        default='ORIGIN'
    )
    
    bpy.types.Scene.gmod_weapon_root_path = bpy.props.StringProperty(
        name="GMod Folder (ARC9)",
        description="Path to Garry's Mod directory containing addons/cache specifically for ARC9 weapon imports (optional, falls back to main GMod Folder)",
        subtype='DIR_PATH'
    )
    
    bpy.types.Scene.gmod_weapon_cache_path = bpy.props.StringProperty(
        name="Workshop Cache (ARC9)",
        description="Folder to extract and store Workshop assets specifically for ARC9 weapon imports (optional, falls back to main Workshop Cache)",
        subtype='DIR_PATH'
    )
    
    bpy.types.Scene.gmod_weapon_skip_materials = bpy.props.BoolProperty(
        name="Skip Materials (ARC9)",
        description="Only import weapon geometry, do not load materials or textures (Fast)",
        default=False
    )
    
    bpy.types.Scene.gmod_weapon_pull_material_mode = bpy.props.EnumProperty(
        name="Pull Material Mode (ARC9)",
        description="Type of shader to use when pulling materials for weapon",
        items=[
            ("PRINCIPLED", "Blender Principled (Simple)", "Use basic Blender Principled BSDF shader"),
            ("SOURCEIO", "SourceIO Node (Advanced)", "Use custom SourceIO complex shader nodes"),
        ],
        default="PRINCIPLED"
    )

    bpy.types.Scene.gmod_weapon_import_hands = bpy.props.BoolProperty(
        name="Import Hands (ARC9)",
        description="Import player hands/sleeves model and anim rig",
        default=True
    )
    
    bpy.types.Scene.gmod_livelink_port = bpy.props.IntProperty(
        name="Live Link Port",
        description="Port for the local HTTP Live Link server",
        default=8000,
        min=1024,
        max=65535
    )
    
    bpy.types.Scene.gmod_livelink_active = bpy.props.BoolProperty(
        name="Live Link Active",
        description="Is the GMod Live Link server running",
        default=False
    )
    
    bpy.types.Scene.gmod_livelink_packets_recv = bpy.props.IntProperty(
        name="Live Link Packets Received",
        default=0
    )
    
    bpy.types.Scene.gmod_livelink_server_map = bpy.props.StringProperty(
        name="GMod Server Map",
        description="Map to load on the GMod Dedicated Server",
        default="gm_construct"
    )
    
    bpy.types.Scene.gmod_livelink_root_path = bpy.props.StringProperty(
        name="GMod Game Folder",
        description="Path to Garry's Mod root directory (contains srcds.exe)",
        subtype='DIR_PATH',
        default=""
    )

    def update_map_visibility(self, context):
        hide = self.gmod_livelink_map_hide
        
        def set_exclude(layer_col, col_name, state):
            if layer_col.collection.name == col_name:
                layer_col.exclude = state
                return True
            for child in layer_col.children:
                if set_exclude(child, col_name, state):
                    return True
            return False
            
        # Exclude from View Layer (the checkbox in outliner)
        view_layer_root = context.view_layer.layer_collection
        set_exclude(view_layer_root, "GMOD_MAP", hide)
        
        map_name = self.gmod_livelink_map_loaded
        if map_name:
            col_name = f"{map_name}.bsp"
            set_exclude(view_layer_root, col_name, hide)
            
        # Also apply standard viewport/render hide as fallback
        col = bpy.data.collections.get("GMOD_MAP")
        if col:
            col.hide_viewport = hide
            col.hide_render = hide
        if map_name:
            col_bsp = bpy.data.collections.get(f"{map_name}.bsp")
            if col_bsp:
                col_bsp.hide_viewport = hide
                col_bsp.hide_render = hide

    bpy.types.Scene.gmod_livelink_load_map = bpy.props.BoolProperty(
        name="Auto-load Map Geometry",
        description="Automatically import GMod map geometry when Live Link starts",
        default=False
    )
    bpy.types.Scene.gmod_livelink_auto_refine = bpy.props.BoolProperty(
        name="Spawn Models Directly",
        description="Automatically parse and spawn high-quality Source models instead of cubes during Live Link updates",
        default=False
    )
    
    def update_player_mesh_visibility(self, context):
        hide = self.gmod_livelink_hide_player_meshes
        for obj in bpy.data.objects:
            if obj.name.startswith("GMod_Player_") and obj.type == 'ARMATURE':
                for child in obj.children:
                    if child.type == 'MESH':
                        child.hide_viewport = hide
                        child.hide_render = hide

    bpy.types.Scene.gmod_livelink_hide_player_meshes = bpy.props.BoolProperty(
        name="Hide Player Models",
        description="Hide player meshes in viewport so they do not obstruct camera view",
        default=False,
        update=update_player_mesh_visibility
    )
    
    def update_hitbox_visibility(self, context):
        hide = self.gmod_livelink_hide_hitboxes
        for obj in bpy.data.objects:
            if obj.name.startswith("GMod_Prop_") and obj.type == 'MESH':
                obj.hide_viewport = hide
                obj.hide_render = hide

    bpy.types.Scene.gmod_livelink_hide_hitboxes = bpy.props.BoolProperty(
        name="Hide Hitbox Cubes",
        description="Hide placeholder hitbox cubes when models are loaded",
        default=False,
        update=update_hitbox_visibility
    )
    
    bpy.types.Scene.gmod_livelink_sync_viewport = bpy.props.EnumProperty(
        name="Sync Viewport",
        description="Sync active Blender 3D Viewport camera navigation in real-time to Garry's Mod",
        items=[
            ('NONE', 'Disabled', 'Do not sync viewport camera'),
            ('PLAYER', 'Sync to Player', 'Sync viewport camera to local player in GMod'),
            ('OPERATOR', 'Sync to Operator Cam', 'Sync viewport camera to green operator camera in GMod'),
        ],
        default='NONE'
    )
    
    bpy.types.Scene.gmod_livelink_record = bpy.props.BoolProperty(
        name="Record Motion Capture",
        description="Enable real-time motion capture recording into keyframes",
        default=False
    )
    bpy.types.Scene.gmod_livelink_map_loaded = bpy.props.StringProperty(
        name="Loaded Map Name",
        default=""
    )
    bpy.types.Scene.gmod_livelink_map_hide = bpy.props.BoolProperty(
        name="Hide Map Geometry",
        description="Hide or show the loaded map collection in the viewport",
        default=False,
        update=update_map_visibility
    )
    
    from gmod_scene_importer.operators_livelink import gmod_freeze_update_callback
    bpy.types.Object.gmod_physics_frozen = bpy.props.BoolProperty(
        name="Freeze Physics",
        description="Freeze physics of this entity in Garry's Mod",
        default=False,
        update=gmod_freeze_update_callback
    )
    bpy.types.Object.gmod_user_control_timeout = bpy.props.FloatProperty(
        name="User Control Timeout",
        description="How long (seconds) Blender should maintain control after user moves this object before resuming GMod sync",
        default=10.0,
        min=0.0,
        max=300.0
    )
    
def unregister():
    if gmod_selection_change_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(gmod_selection_change_handler)
    del bpy.types.Object.gmod_bg_categories
    del bpy.types.Object.gmod_bg_active_category
    del bpy.types.Object.show_bg_ui
    del bpy.types.Object.gmod_physics_frozen
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
        
    try:
        from gmod_scene_importer.SourceIO_adv.blender_bindings.bindings import unregister as sio_unregister
        sio_unregister()
    except:
        pass
        
    try:
        from gmod_scene_importer.SourceIO_adv.blender_bindings.attributes import unregister_props
        unregister_props()
    except:
        pass
        
    del bpy.types.Scene.gmod_json_path
    del bpy.types.Scene.gmod_root_path
    del bpy.types.Scene.gmod_workshop_path
    del bpy.types.Scene.gmod_cache_path
    del bpy.types.Scene.gmod_cache_workers
    del bpy.types.Scene.gmod_clear_scene
    del bpy.types.Scene.gmod_mount_css_hl2
    del bpy.types.Scene.gmod_replace_cameras
    del bpy.types.Scene.gmod_import_rotation
    del bpy.types.Scene.gmod_global_scale
    del bpy.types.Scene.gmod_weapon_json_path
    del bpy.types.Scene.gmod_weapon_spawn_mode
    del bpy.types.Scene.gmod_weapon_root_path
    del bpy.types.Scene.gmod_weapon_cache_path
    del bpy.types.Scene.gmod_weapon_skip_materials
    del bpy.types.Scene.gmod_weapon_pull_material_mode
    del bpy.types.Scene.gmod_weapon_import_hands
    del bpy.types.Scene.gmod_livelink_port
    del bpy.types.Scene.gmod_livelink_active
    del bpy.types.Scene.gmod_livelink_packets_recv
    del bpy.types.Scene.gmod_livelink_server_map
    del bpy.types.Scene.gmod_livelink_root_path
    del bpy.types.Scene.gmod_livelink_load_map
    del bpy.types.Scene.gmod_livelink_auto_refine
    del bpy.types.Scene.gmod_livelink_hide_player_meshes
    del bpy.types.Scene.gmod_livelink_hide_hitboxes
    del bpy.types.Scene.gmod_livelink_sync_viewport
    del bpy.types.Scene.gmod_livelink_record
    del bpy.types.Scene.gmod_livelink_map_loaded
    del bpy.types.Scene.gmod_livelink_map_hide

if __name__ == "__main__":
    register()
