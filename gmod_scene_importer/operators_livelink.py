import bpy
import threading
import queue
import json
import mathutils
try:
    from http.server import ThreadingHTTPServer as HTTPServerClass
except ImportError:
    from http.server import HTTPServer as HTTPServerClass
from http.server import BaseHTTPRequestHandler

# Thread-safe queues for communication
INCOMING_QUEUE = queue.Queue()
OUTGOING_QUEUE = queue.Queue()
SCRIPT_UPDATED_OBJECTS = set()

# Global server reference
LIVELINK_SERVER = None
LIVELINK_DEPSGRAPH_HANDLER = None

LIVELINK_LOGS = []
KNOWN_GMOD_IDS = set()
LAST_WORLD_STATE_TIME = 0.0
FAILED_REFINE_IDS = set()
BONE_UPDATE_THROTTLE = {}   # obj_name -> last bone update timestamp
BONE_UPDATE_INTERVAL = 0.03  # 33Hz for active ragdolls/NPCs/players, overridden to 0.3 for frozen ones
LAST_BONE_STATES = {}  # obj_name -> {bone_name: {pos, ang, scale}} for differential updates

def add_log(message):
    print(f"[GModLiveLink] {message}")
    if message.startswith("Recv:"):
        return
    LIVELINK_LOGS.append(message)
    if len(LIVELINK_LOGS) > 10:
        LIVELINK_LOGS.pop(0)

def get_target_collection(category_name):
    scene = bpy.context.scene
    parent_col = scene.collection
    if category_name not in bpy.data.collections:
        new_col = bpy.data.collections.new(category_name)
        parent_col.children.link(new_col)
    return bpy.data.collections[category_name]

def apply_live_state(obj, skin, bodygroups, bones=None, scene_origin=None, scale=1.0, is_bsp_mode=False):
    if not obj:
        return
    # Only apply to refined models
    if obj.type == 'MESH' and len(obj.data.vertices) == 8:
        return # It's a placeholder cube, skip
        
    from gmod_scene_importer.operators import apply_bodygroups, apply_skin, apply_bone_poses
    try:
        apply_bodygroups(obj, bodygroups)
        apply_skin(obj, skin)
        
        if obj.type == 'ARMATURE' and bones and scene_origin is not None:
            SCRIPT_UPDATED_OBJECTS.add(obj.name)
            
            import time as _t
            now = _t.time()
            last_bone_update = BONE_UPDATE_THROTTLE.get(obj.name, 0.0)
            is_frozen = obj.get("gmod_physics_frozen", False)
            bone_interval = 0.3 if is_frozen else BONE_UPDATE_INTERVAL
            
            if now - last_bone_update >= bone_interval:
                BONE_UPDATE_THROTTLE[obj.name] = now
                # Re-use our robust offline skeleton posing logic
                apply_bone_poses(obj, bones, scene_origin=scene_origin, global_scale=scale, is_weapon=False, is_bsp_mode=is_bsp_mode)
            
            # If it's a playermodel armature, ensure it has a camera parented to its head bone!
            if obj.name.startswith("GMod_Player_") or obj.name == "GMod_Player_Camera":
                head_bone_name = None
                from gmod_scene_importer.operators import find_matching_bone
                for bname in ["valvebiped.bip01_head1", "bip01_head1", "valvebiped.bip01_head", "bip01_head", "head"]:
                    matched = obj.pose.bones.get(bname) or find_matching_bone(obj, bname)
                    if matched:
                        head_bone_name = matched.name
                        break
                        
                if head_bone_name:
                    cam_child_name = obj.name + "_View"
                    cam_child = bpy.data.objects.get(cam_child_name)
                    if not cam_child:
                        import math
                        camera_data = bpy.data.cameras.new(name=cam_child_name)
                        cam_child = bpy.data.objects.new(name=cam_child_name, object_data=camera_data)
                        get_target_collection("GMOD_PLAYERS").objects.link(cam_child)
                        
                        # Parent to the head bone
                        cam_child.parent = obj
                        cam_child.parent_type = 'BONE'
                        cam_child.parent_bone = head_bone_name
                        
                        # Reset transforms to match head eyes looking forward
                        cam_child.location = (0, 0, 0)
                        cam_child.rotation_mode = 'XYZ'
                        cam_child.rotation_euler = (math.radians(90), 0, math.radians(180))
                        print(f"[GModLiveLink] Parented camera {cam_child_name} to head bone {head_bone_name}")
    except Exception as e:
        print(f"[GModLiveLink] Failed to apply live state to {obj.name}: {e}")

def refine_single_object(obj):
    import os
    import math
    import json
    import bpy
    from gmod_scene_importer.operators import get_content_manager, setup_gmod_mounts, import_model
    from gmod_scene_importer import utils, operators_cache
    from gmod_scene_importer.source_model.source_shared.content_provider import FileBuffer
    from gmod_scene_importer.tiny_path import TinyPath
    
    model_path_str = obj.get("gmod_model")
    if not model_path_str:
        add_log(f"JIT Refine SKIP: No gmod_model on {obj.name}")
        return None
        
    add_log(f"JIT Refine ATTEMPT: {model_path_str}")
    
    cm = get_content_manager(force_recreate=False)
    
    gmod_root = bpy.context.scene.gmod_root_path
    if not gmod_root or not os.path.isdir(gmod_root):
        gmod_root = getattr(bpy.context.scene, "gmod_livelink_root_path", None)
        add_log(f"JIT Refine: Using livelink root: {gmod_root}")
    else:
        add_log(f"JIT Refine: Using main root: {gmod_root}")
        
    cache_path_str = bpy.context.scene.gmod_cache_path
    if not cache_path_str:
        cache_path_str = os.path.join(bpy.utils.resource_path('USER'), "gmod_workshop_cache")
        add_log(f"JIT Refine: Using default cache: {cache_path_str}")
    
    # Rebuild cache index to ensure ASSET_INDEX is populated
    operators_cache.WorkshopCacheManager.rebuild_index(bpy.context, force=False)
    add_log(f"JIT Refine: Cache index rebuilt, {len(operators_cache.ASSET_INDEX)} assets indexed")
        
    if gmod_root and os.path.isdir(gmod_root):
        setup_gmod_mounts(bpy.context, cm, TinyPath(gmod_root), override_cache_path=cache_path_str)
        add_log(f"JIT Refine: Mounts setup complete")
    else:
        add_log(f"JIT Refine ERROR: Invalid gmod_root: {gmod_root}")
        
    file_buffer = cm.find_file(TinyPath(model_path_str))
    if not file_buffer:
        add_log(f"JIT Refine: File not found in CM, checking cache...")
        cached_path = operators_cache.WorkshopCacheManager.resolve_path(model_path_str)
        add_log(f"JIT Refine: Cache path: {cached_path}, exists: {cached_path and os.path.exists(cached_path)}")
        
        # Fallback: search directly in workshop/content if cache is empty
        if not cached_path:
            workshop_path = bpy.context.scene.gmod_workshop_path
            add_log(f"JIT Refine: Workshop path: {workshop_path}, exists: {workshop_path and os.path.isdir(workshop_path)}")
            if workshop_path and os.path.isdir(workshop_path):
                import os
                model_filename = model_path_str.split('/')[-1]
                add_log(f"JIT Refine: Searching for {model_filename} in workshop...")
                for root, dirs, files in os.walk(workshop_path):
                    if model_filename in files:
                        cached_path = os.path.join(root, model_filename)
                        add_log(f"JIT Refine: Found in workshop walk: {cached_path}")
                        break
                if not cached_path:
                    add_log(f"JIT Refine: Model {model_filename} not found in workshop walk")
        
        if cached_path and os.path.exists(cached_path):
            path_parts = os.path.normpath(cached_path).split(os.sep)
            addon_root = None
            for i in range(len(path_parts)-1, -1, -1):
                if path_parts[i].lower() in ('models', 'materials', 'sound'):
                    addon_root = os.sep.join(path_parts[:i])
                    break
            add_log(f"JIT Refine: Detected addon_root: {addon_root}")
            if addon_root and os.path.isdir(addon_root):
                cm.scan_for_content(TinyPath(addon_root))
                add_log(f"JIT Refine: Scanned addon_root")
            file_buffer = FileBuffer(cached_path, 'rb')
            
    if not file_buffer:
        add_log(f"JIT Refine MISS: {model_path_str.split('/')[-1]}")
        return None
        
    try:
        class MockOptions:
            bodygroup_grouping = True
            import_textures = not bpy.context.scene.gmod_skip_materials
            skin_decals = False
            import_physics = True
            write_qc = False
            load_refpose = False
            import_animations = False
            create_flex_drivers = False
            use_bvlg = (bpy.context.scene.gmod_pull_material_mode == 'SOURCEIO')
            scale = utils.SCALE_FACTOR
            
        container = import_model(TinyPath(model_path_str), file_buffer, cm, MockOptions())
        if container.objects:
            new_root = container.objects[0]
            while new_root.parent: new_root = new_root.parent
            
            new_root.matrix_world = obj.matrix_world.copy()
            if new_root.type != 'ARMATURE':
                for child in new_root.children:
                    child.rotation_euler.rotate_axis('Z', math.radians(90))
                
            old_name = obj.name
            gmod_id = obj.get("gmod_id", 0)
            steamid = obj.get("steamid", "")
            
            target_col = obj.users_collection[0] if obj.users_collection else bpy.context.collection
            bpy.data.objects.remove(obj, do_unlink=True)
            
            new_root.name = old_name
            new_root['gmod_model'] = model_path_str
            if gmod_id:
                new_root['gmod_id'] = gmod_id
            if steamid:
                new_root['steamid'] = steamid
            new_root.gmod_physics_frozen = False
            
            def link_recursive(o, col):
                if o.name not in col.objects:
                    col.objects.link(o)
                for child in o.children:
                    link_recursive(child, col)
            
            link_recursive(new_root, target_col)
                
            add_log(f"JIT Refined: {model_path_str.split('/')[-1]} (ID {gmod_id})")
            return new_root
    except Exception as e:
        add_log(f"JIT Refine Error for ID {obj.get('gmod_id', '?')}: {e}")
        
    return None

class GModLiveLinkHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Disable logging to console to prevent performance overhead
        pass

    def do_POST(self):
        if self.path == "/update":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    raw_data = self.rfile.read(content_length)
                    data = json.loads(raw_data.decode('utf-8'))
                    INCOMING_QUEUE.put(data)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())

    def do_GET(self):
        if self.path == "/":
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                
                html = """<!DOCTYPE html>
<html>
<head>
<script>
    function sendUpdate(x, y, z, p, yaw, r) {
        fetch("/update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                type: "player_transform",
                pos: [x, y, z],
                ang: [p, yaw, r]
            })
        }).catch(e => {});
    }
</script>
</head>
<body>Live Link Bridge Active</body>
</html>"""
                self.wfile.write(html.encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        elif self.path == "/poll":
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                
                updates = []
                while not OUTGOING_QUEUE.empty():
                    updates.append(OUTGOING_QUEUE.get())
                
                self.wfile.write(json.dumps(updates).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())


def run_server(port):
    global LIVELINK_SERVER
    try:
        LIVELINK_SERVER = HTTPServerClass(('127.0.0.1', port), GModLiveLinkHandler)
        print(f"[GModLiveLink] Server listening on http://127.0.0.1:{port}")
        LIVELINK_SERVER.serve_forever()
    except Exception as e:
        print(f"[GModLiveLink] Server thread error: {e}")


def find_and_load_map(map_name):
    import os
    # Search for BSP file
    roots = []
    ll_root = bpy.context.scene.gmod_livelink_root_path
    if ll_root and os.path.isdir(ll_root):
        roots.append(ll_root)
        roots.append(os.path.join(ll_root, "garrysmod"))
        
    main_root = bpy.context.scene.gmod_root_path
    if main_root and os.path.isdir(main_root):
        roots.append(main_root)
        roots.append(os.path.join(main_root, "garrysmod"))
        
    bsp_path = None
    for r in roots:
        candidates = [
            os.path.join(r, "maps", f"{map_name}.bsp"),
            os.path.join(r, "garrysmod", "maps", f"{map_name}.bsp"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                bsp_path = path
                break
        if bsp_path:
            break
            
    if not bsp_path:
        print(f"[GModLiveLink] BSP file for map '{map_name}' not found in paths: {roots}")
        return
        
    print(f"[GModLiveLink] Auto-loading map geometry from: {bsp_path}")
    try:
        from .sourceio_bridge import import_bsp, ContentManager, FileBuffer, TinyPath
        
        class DummyBSPSettings:
            scale = bpy.context.scene.gmod_global_scale
            light_scale = 1.0
            load_props = False # Don't load entity props (synced in real-time)
            load_lights = True
            load_decals = True
            load_static_props = True # Load static world props
            load_triggers = False
            load_info = False
            load_logic = False
            load_ropes = False
            import_textures = not bpy.context.scene.gmod_skip_materials
            import_cubemaps = False
            use_bvlg = (bpy.context.scene.gmod_pull_material_mode == 'BVLG')
            
        filepath = TinyPath(bsp_path)
        content_manager = ContentManager()
        content_manager.first_import = filepath
        content_manager.scan_for_content(filepath)
        
        # Ensure collection exists and make it active
        map_col = bpy.data.collections.get("GMOD_MAP")
        if not map_col:
            map_col = bpy.data.collections.new("GMOD_MAP")
            bpy.context.scene.collection.children.link(map_col)
            
        orig_collection = bpy.context.view_layer.active_layer_collection
        
        def find_layer_collection(layer_col, name):
            if layer_col.name == name:
                return layer_col
            for child in layer_col.children:
                r = find_layer_collection(child, name)
                if r: return r
            return None
            
        map_layer_col = find_layer_collection(bpy.context.view_layer.layer_collection, "GMOD_MAP")
        if map_layer_col:
            bpy.context.view_layer.active_layer_collection = map_layer_col
            
        try:
            with FileBuffer(filepath) as f:
                import_bsp(filepath, f, content_manager, DummyBSPSettings(), None)
            print(f"[GModLiveLink] Map loaded successfully: {map_name}")
            bpy.context.scene.gmod_livelink_map_loaded = map_name
            bpy.context.scene["gmod_scene_origin"] = [0.0, 0.0, 0.0]
            if "gmod_scene_origin_rotation" in bpy.context.scene:
                bpy.context.scene["gmod_scene_origin_rotation"] = 0.0
        finally:
            bpy.context.view_layer.active_layer_collection = orig_collection
            
    except Exception as e:
        print(f"[GModLiveLink] Error auto-importing map BSP: {e}")


def get_viewport_camera_transform():
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            space = area.spaces.active
            r3d = space.region_3d
            if r3d:
                view_matrix_inv = r3d.view_matrix.inverted()
                loc = view_matrix_inv.to_translation()
                rot = view_matrix_inv.to_euler('XYZ')
                return loc, rot
    return None, None

# Timer callback running inside Blender's main thread (safe to call bpy.data/context)
def livelink_timer_callback():
    if not bpy.context.scene.gmod_livelink_active:
        if hasattr(livelink_timer_callback, "initialized_known_ids"):
            del livelink_timer_callback.initialized_known_ids
        return None  # Stop the timer
        
    # Viewport camera sync to GMod
    sync_mode = bpy.context.scene.gmod_livelink_sync_viewport
    if sync_mode != 'NONE':
        loc, rot = get_viewport_camera_transform()
        if loc and rot:
            last_loc = bpy.context.scene.get("gmod_last_vp_loc")
            last_rot = bpy.context.scene.get("gmod_last_vp_rot")
            
            moved = True
            if last_loc and last_rot:
                dist = (loc - mathutils.Vector(last_loc)).length
                ang_diff = abs(rot.x - last_rot[0]) + abs(rot.y - last_rot[1]) + abs(rot.z - last_rot[2])
                if dist < 0.005 and ang_diff < 0.005:
                    moved = False
                    
            if moved:
                bpy.context.scene["gmod_last_vp_loc"] = list(loc)
                bpy.context.scene["gmod_last_vp_rot"] = list(rot)
                
                scale = bpy.context.scene.gmod_global_scale
                scene_origin = bpy.context.scene.get("gmod_scene_origin", [0.0, 0.0, 0.0])
                is_bsp_mode = bool(bpy.context.scene.gmod_livelink_map_loaded)
                
                import math
                if is_bsp_mode:
                    gmod_pos = [
                        (loc.x / scale) + scene_origin[0],
                        (loc.y / scale) + scene_origin[1],
                        (loc.z / scale) + scene_origin[2]
                    ]
                    gmod_ang = [
                        90 - math.degrees(rot.x),
                        math.degrees(rot.z) + 90,
                        math.degrees(rot.y)
                    ]
                else:
                    gmod_pos = [
                        (loc.y / scale) + scene_origin[0],
                        (-loc.x / scale) + scene_origin[1],
                        (loc.z / scale) + scene_origin[2]
                    ]
                    gmod_ang = [
                        90 - math.degrees(rot.x),
                        math.degrees(rot.z),
                        math.degrees(rot.y)
                    ]
                
                if sync_mode == 'PLAYER':
                    packet = {
                        "type": "player_teleport",
                        "pos": gmod_pos,
                        "ang": gmod_ang
                    }
                    OUTGOING_QUEUE.put(packet)
                elif sync_mode == 'OPERATOR':
                    packet = {
                        "type": "spawn_operator",
                        "pos": gmod_pos,
                        "ang": gmod_ang
                    }
                    OUTGOING_QUEUE.put(packet)
        
    # Track deleted objects in Blender and sync to GMod
    global KNOWN_GMOD_IDS
    current_gmod_ids = set()
    for obj in bpy.context.scene.objects:
        gmod_id = obj.get("gmod_id")
        if gmod_id is not None:
            try:
                current_gmod_ids.add(int(gmod_id))
            except:
                pass
                
    if not hasattr(livelink_timer_callback, "initialized_known_ids"):
        livelink_timer_callback.initialized_known_ids = True
        KNOWN_GMOD_IDS = current_gmod_ids
    else:
        deleted_ids = KNOWN_GMOD_IDS - current_gmod_ids
        for gmod_id in deleted_ids:
            packet = {
                "type": "delete_entity",
                "gmod_id": gmod_id
            }
            OUTGOING_QUEUE.put(packet)
            add_log(f"Blender Deleted -> GMod ID {gmod_id}")
            
        KNOWN_GMOD_IDS = current_gmod_ids
    
    # Process incoming queue
    while not INCOMING_QUEUE.empty():
        try:
            packet = INCOMING_QUEUE.get_nowait()
            packet_type = packet.get("type")
            
            if packet_type == "world_state":
                import math, time
                global LAST_WORLD_STATE_TIME
                LAST_WORLD_STATE_TIME = time.time()
                map_name = packet.get("map", "")
                players_data = packet.get("players", [])
                props_data = packet.get("props", [])
                
                bpy.context.scene.gmod_livelink_packets_recv += 1
                add_log(f"Recv: {len(players_data)} plys, {len(props_data)} props")
                
                if bpy.context.scene.gmod_livelink_load_map and map_name:
                    if bpy.context.scene.gmod_livelink_map_loaded != map_name:
                        bpy.context.scene.gmod_livelink_map_loaded = map_name
                        find_and_load_map(map_name)

                scene_origin = bpy.context.scene.get("gmod_scene_origin", [0.0, 0.0, 0.0])
                scale = bpy.context.scene.gmod_global_scale
                
                # --- Players ---
                seen_names = set()
                
                for ply_data in players_data:
                    name = ply_data.get("name", "Unknown")
                    steamid = ply_data.get("steamid", "")
                    pos = ply_data.get("pos", [0, 0, 0])
                    ang = ply_data.get("ang", [0, 0, 0])
                    
                    # First player keeps legacy name for backward compat
                    if not seen_names:
                        obj_name = "GMod_Player_Camera"
                    else:
                        safe_name = "".join(c for c in name if c.isalnum() or c in "_- ")[:24]
                        obj_name = f"GMod_Player_{safe_name}"
                    seen_names.add(obj_name)
                    
                    cam_obj = bpy.data.objects.get(obj_name)
                    p_model = ply_data.get("model", "")
                    if cam_obj and cam_obj.get("gmod_model") != p_model:
                        try:
                            # Delete old refined model hierarchy if it exists
                            if cam_obj.type == 'ARMATURE':
                                for child in list(cam_obj.children):
                                    bpy.data.objects.remove(child, do_unlink=True)
                            bpy.data.objects.remove(cam_obj, do_unlink=True)
                        except Exception as e:
                            print(f"[GModLiveLink] Failed to delete player model: {e}")
                        cam_obj = None
                        
                    if not cam_obj:
                        camera_data = bpy.data.cameras.new(name=obj_name)
                        cam_obj = bpy.data.objects.new(name=obj_name, object_data=camera_data)
                        bpy.context.scene.collection.objects.link(cam_obj)
                        cam_obj.rotation_mode = 'XYZ'
                        print(f"[GModLiveLink] Created player camera: {obj_name}")
                    
                    fov = ply_data.get("fov", 75.0)
                    p_scale = ply_data.get("model_scale", 1.0)
                    hp = ply_data.get("hp", 100)
                    hp_max = ply_data.get("hp_max", 100)
                    armor = ply_data.get("armor", 0)
                    alive = ply_data.get("alive", True)
                    team = ply_data.get("team", "Unassigned")
                    ping = ply_data.get("ping", 0)
                    nick = ply_data.get("nick", name)
                    
                    cam_obj["steamid"] = steamid
                    cam_obj["gmod_model"] = p_model
                    cam_obj["player_name"] = name
                    cam_obj["nick"] = nick
                    cam_obj["fov"] = round(fov, 1)
                    cam_obj["model_scale"] = round(p_scale, 3)
                    cam_obj["hp"] = hp
                    cam_obj["hp_max"] = hp_max
                    cam_obj["armor"] = armor
                    cam_obj["alive"] = alive
                    cam_obj["team"] = team
                    cam_obj["ping"] = ping
                    
                    # Apply GMod FOV to Blender camera lens
                    if cam_obj.type == 'CAMERA':
                        cam_obj.data.angle = math.radians(fov)
                    elif cam_obj.type == 'ARMATURE':
                        cam_child_name = cam_obj.name + "_View"
                        cam_child = bpy.data.objects.get(cam_child_name)
                        if cam_child and cam_child.type == 'CAMERA':
                            cam_child.data.angle = math.radians(fov)
                    
                    if bpy.context.scene.gmod_livelink_auto_refine and p_model:
                        add_log(f"Player Refine ATTEMPT: {p_model}")
                        cam_obj["last_gmod_sync_time"] = time.time()
                        # Pre-position the camera so the refined model spawns in correct location
                        rel_pos = [pos[0] - scene_origin[0], pos[1] - scene_origin[1], pos[2] - scene_origin[2]]
                        is_bsp_mode = bool(bpy.context.scene.gmod_livelink_map_loaded)
                        if is_bsp_mode:
                            cam_obj.location = mathutils.Vector((rel_pos[0] * scale, rel_pos[1] * scale, rel_pos[2] * scale))
                            cam_obj.rotation_euler = [math.radians(ang[2]), math.radians(ang[0]), math.radians(ang[1])]
                        else:
                            cam_obj.location = mathutils.Vector((-rel_pos[1] * scale, rel_pos[0] * scale, rel_pos[2] * scale))
                            cam_obj.rotation_euler = [math.radians(ang[0]), math.radians(ang[1]), math.radians(ang[2])]
                        
                        # Create a placeholder mesh for the player model (like props)
                        placeholder_name = f"GMod_Player_Mesh_{steamid}"
                        placeholder = bpy.data.objects.get(placeholder_name)
                        if not placeholder:
                            mesh = bpy.data.meshes.new(name=placeholder_name + "_Mesh")
                            placeholder = bpy.data.objects.new(name=placeholder_name, object_data=mesh)
                            bpy.context.scene.collection.objects.link(placeholder)
                            placeholder.rotation_mode = 'XYZ'
                            placeholder["gmod_model"] = p_model
                            placeholder["steamid"] = steamid
                            placeholder["player_name"] = name
                            placeholder.location = cam_obj.location.copy()
                            placeholder.rotation_euler = cam_obj.rotation_euler.copy()
                            add_log(f"Created player placeholder: {placeholder_name}")
                        
                        # Parent placeholder to camera so it moves with player
                        if placeholder.parent != cam_obj:
                            placeholder.parent = cam_obj
                            placeholder.matrix_parent_inverse = cam_obj.matrix_world.inverted()
                        
                        refined = refine_single_object(placeholder)
                        if refined:
                            placeholder = refined
                            add_log(f"Player Refine SUCCESS: {p_model}")
                            if getattr(bpy.context.scene, "gmod_livelink_hide_player_meshes", False):
                                for child in placeholder.children:
                                    if child.type == 'MESH':
                                        child.hide_viewport = True
                                        child.hide_render = True
                        else:
                            add_log(f"Player Refine FAILED: {p_model}")
                    
                    # Skip GMod position updates if user is controlling this object
                    user_control_timeout = cam_obj.get("user_control_timeout", cam_obj.gmod_user_control_timeout if hasattr(cam_obj, 'gmod_user_control_timeout') else 10.0)
                    if time.time() - cam_obj.get("last_user_move_time", 0.0) < user_control_timeout:
                        add_log(f"User control active for {cam_obj.name}, skipping GMod sync")
                        continue
                    
                    if time.time() - cam_obj.get("last_user_move_time", 0.0) >= user_control_timeout:
                        rel_pos = [pos[0] - scene_origin[0], pos[1] - scene_origin[1], pos[2] - scene_origin[2]]
                        
                        is_bsp_mode = bool(bpy.context.scene.gmod_livelink_map_loaded)
                        if is_bsp_mode:
                            bl_pos = mathutils.Vector((rel_pos[0] * scale, rel_pos[1] * scale, rel_pos[2] * scale))
                            p = math.radians(90 - ang[0])
                            y = math.radians(ang[1] - 90)
                            r = math.radians(ang[2])
                        else:
                            bl_pos = mathutils.Vector((-rel_pos[1] * scale, rel_pos[0] * scale, rel_pos[2] * scale))
                            p = math.radians(90 - ang[0])
                            y = math.radians(ang[1])
                            r = math.radians(ang[2])
                            
                        cam_obj["last_gmod_sync_time"] = time.time()
                        
                        if cam_obj.type == 'ARMATURE':
                            SCRIPT_UPDATED_OBJECTS.add(cam_obj.name)
                            cam_obj.location = bl_pos
                            if is_bsp_mode:
                                cam_obj.rotation_euler = [0.0, 0.0, math.radians(ang[1])]
                            else:
                                cam_obj.rotation_euler = [0.0, 0.0, math.radians(ang[1] + 90)]
                            cam_obj.scale = (p_scale, p_scale, p_scale)
                        else:
                            cam_obj.scale = (p_scale, p_scale, p_scale)
                            
                        cam_obj["target_loc"] = list(bl_pos)
                        cam_obj["target_rot"] = [p, r, y]
                        
                        # Apply live bones if player is refined into an armature
                        p_bones = ply_data.get("bones")
                        apply_live_state(cam_obj, skin=0, bodygroups={}, bones=p_bones, scene_origin=scene_origin, scale=scale, is_bsp_mode=is_bsp_mode)
                        
                        # --- Player Weapon Sync ---
                        weapon = ply_data.get("weapon")
                        w_obj = None
                        if weapon and cam_obj.type == 'ARMATURE':
                            w_model = weapon.get("model")
                            w_id = weapon.get("id")
                            w_obj_name = f"GMod_Weapon_{w_id}"
                            w_obj = bpy.data.objects.get(w_obj_name)
                            
                            if w_obj and w_obj.get("gmod_model") != w_model:
                                bpy.data.objects.remove(w_obj, do_unlink=True)
                                w_obj = None
                                
                            if not w_obj:
                                w_mesh = bpy.data.meshes.new(name=w_obj_name)
                                w_obj = bpy.data.objects.new(name=w_obj_name, object_data=w_mesh)
                                get_target_collection("GMOD_WEAPONS").objects.link(w_obj)
                                w_obj["gmod_id"] = w_id
                                w_obj["gmod_model"] = w_model
                                
                                import bmesh
                                bm = bmesh.new()
                                bmesh.ops.create_cube(bm, size=5.0 * scale)
                                bm.to_mesh(w_mesh)
                                bm.free()
                                
                                if bpy.context.scene.gmod_livelink_auto_refine and w_model:
                                    add_log(f"Weapon Refine ATTEMPT: {w_model}")
                                    refined_w = refine_single_object(w_obj)
                                    if refined_w:
                                        w_obj = refined_w
                                        add_log(f"Weapon Refine SUCCESS: {w_model}")
                                    else:
                                        add_log(f"Weapon Refine FAILED: {w_model}")
                                        
                            if w_obj and w_obj.parent != cam_obj:
                                hand_bone = None
                                from gmod_scene_importer.operators import find_matching_bone
                                for bname in ["valvebiped.anim_attachment_rh", "anim_attachment_RH", "valvebiped.anim_attachment_rh1", "anim_attachment_rh", "valvebiped.bip01_r_hand", "bip01_r_hand"]:
                                    matched = cam_obj.pose.bones.get(bname) or find_matching_bone(cam_obj, bname)
                                    if matched:
                                        hand_bone = matched.name
                                        break
                                        
                                if hand_bone:
                                    w_obj.parent = cam_obj
                                    w_obj.parent_type = 'BONE'
                                    w_obj.parent_bone = hand_bone
                                    w_obj.location = (0, 0, 0)
                                    w_obj.rotation_mode = 'XYZ'
                                    w_obj.rotation_euler = (0, 0, 0)
                                    
                        # --- Physgun Beam Sync ---
                        holding_id = ply_data.get("holding_entity_id")
                        beam_name = f"GMod_Beam_{steamid}"
                        beam_obj = bpy.data.objects.get(beam_name)
                        
                        if holding_id:
                            target_prop = bpy.data.objects.get(f"GMod_Prop_{holding_id}")
                            if target_prop:
                                if not beam_obj:
                                    curve_data = bpy.data.curves.new(name=beam_name, type='CURVE')
                                    curve_data.dimensions = '3D'
                                    beam_obj = bpy.data.objects.new(beam_name, curve_data)
                                    get_target_collection("GMOD_EFFECTS").objects.link(beam_obj)
                                    
                                    mat_name = f"Physgun_Beam_Mat_{steamid}"
                                    mat = bpy.data.materials.get(mat_name)
                                    if not mat:
                                        mat = bpy.data.materials.new(name=mat_name)
                                        mat.use_nodes = True
                                        nodes = mat.node_tree.nodes
                                        nodes.clear()
                                        node_emission = nodes.new(type='ShaderNodeEmission')
                                        node_output = nodes.new(type='ShaderNodeOutputMaterial')
                                        mat.node_tree.links.new(node_emission.outputs['Emission'], node_output.inputs['Surface'])
                                    beam_obj.data.materials.append(mat)
                                    
                                rgb = ply_data.get("physgun_color", [0, 255, 255])
                                mat = beam_obj.data.materials[0]
                                emission_node = mat.node_tree.nodes.get("Emission")
                                if emission_node:
                                    emission_node.inputs['Color'].default_value = (rgb[0]/255, rgb[1]/255, rgb[2]/255, 1.0)
                                    emission_node.inputs['Strength'].default_value = 5.0
                                    
                                start_pos = cam_obj.matrix_world.translation.copy()
                                if w_obj:
                                    start_pos = w_obj.matrix_world.translation.copy()
                                    
                                end_pos = target_prop.matrix_world.translation.copy()
                                
                                curve_data = beam_obj.data
                                curve_data.splines.clear()
                                spline = curve_data.splines.new(type='BEZIER')
                                spline.bezier_points.add(1)
                                
                                start_local = beam_obj.matrix_world.inverted() @ start_pos
                                end_local = beam_obj.matrix_world.inverted() @ end_pos
                                
                                spline.bezier_points[0].co = start_local
                                spline.bezier_points[0].handle_left = start_local
                                spline.bezier_points[0].handle_right = start_local
                                
                                spline.bezier_points[1].co = end_local
                                spline.bezier_points[1].handle_left = end_local
                                spline.bezier_points[1].handle_right = end_local
                                
                                curve_data.bevel_depth = 0.05 * scale
                                curve_data.bevel_resolution = 4
                        else:
                            if beam_obj:
                                bpy.data.objects.remove(beam_obj, do_unlink=True)
                
                # --- Props ---
                props_data = packet.get("props", [])
                for prop_data in props_data:
                    gmod_id = prop_data.get("gmod_id")
                    model = prop_data.get("model", "")
                    p_pos = prop_data.get("pos", [0, 0, 0])
                    p_ang = prop_data.get("ang", [0, 0, 0])
                    obj_name = f"GMod_Prop_{gmod_id}"
                    obj = bpy.data.objects.get(obj_name)
                    if obj and obj.get("gmod_model") != model:
                        try:
                            # If it's a refined armature, delete its children meshes too
                            if obj.type == 'ARMATURE':
                                for child in list(obj.children):
                                    bpy.data.objects.remove(child, do_unlink=True)
                            bpy.data.objects.remove(obj, do_unlink=True)
                        except Exception as delete_err:
                            print(f"[GModLiveLink] Failed to delete old object during ID reuse: {delete_err}")
                        obj = None
                        
                    if obj and time.time() - obj.get("last_user_move_time", 0.0) < 1.5:
                        continue
                    if not obj:
                        mesh = bpy.data.meshes.new(name=obj_name)
                        obj = bpy.data.objects.new(name=obj_name, object_data=mesh)
                        import bmesh as bm_mod
                        bm = bm_mod.new()
                        
                        obb_min = prop_data.get("obb_mins")
                        obb_max = prop_data.get("obb_maxs")
                        
                        if obb_min and obb_max:
                            if is_bsp_mode:
                                min_x, min_y, min_z = obb_min[0] * scale, obb_min[1] * scale, obb_min[2] * scale
                                max_x, max_y, max_z = obb_max[0] * scale, obb_max[1] * scale, obb_max[2] * scale
                            else:
                                min_x, min_y, min_z = -obb_max[1] * scale, obb_min[0] * scale, obb_min[2] * scale
                                max_x, max_y, max_z = -obb_min[1] * scale, obb_max[0] * scale, obb_max[2] * scale
                            
                            # Create proper bounding box with 8 vertices
                            verts = [
                                (min_x, min_y, min_z), (max_x, min_y, min_z),
                                (min_x, max_y, min_z), (max_x, max_y, min_z),
                                (min_x, min_y, max_z), (max_x, min_y, max_z),
                                (min_x, max_y, max_z), (max_x, max_y, max_z)
                            ]
                            for v_co in verts:
                                bm.verts.new(v_co)
                            
                            # Create faces for the cube
                            bm.verts.ensure_lookup_table()
                            bm.faces.new((
                                bm.verts[0], bm.verts[1], bm.verts[3], bm.verts[2]  # bottom
                            ))
                            bm.faces.new((
                                bm.verts[4], bm.verts[5], bm.verts[7], bm.verts[6]  # top
                            ))
                            bm.faces.new((
                                bm.verts[0], bm.verts[1], bm.verts[5], bm.verts[4]  # front
                            ))
                            bm.faces.new((
                                bm.verts[2], bm.verts[3], bm.verts[7], bm.verts[6]  # back
                            ))
                            bm.faces.new((
                                bm.verts[0], bm.verts[2], bm.verts[6], bm.verts[4]  # left
                            ))
                            bm.faces.new((
                                bm.verts[1], bm.verts[3], bm.verts[7], bm.verts[5]  # right
                            ))
                        else:
                            cube_size = 20.0 * scale
                            bm_mod.ops.create_cube(bm, size=cube_size)
                        
                        bm.to_mesh(mesh)
                        bm.free()
                        
                        cls = prop_data.get("class", "")
                        if cls == "prop_ragdoll":
                            col_name = "GMOD_RAGDOLLS"
                        elif "vehicle" in cls:
                            col_name = "GMOD_VEHICLES"
                        elif cls == "prop_physics":
                            col_name = "GMOD_PROPS"
                        else:
                            col_name = "GMOD_ENTITIES"
                        
                        get_target_collection(col_name).objects.link(obj)
                        obj.rotation_mode = 'XYZ'
                        obj["gmod_id"] = gmod_id
                        obj["model_path"] = model
                        obj["gmod_model"] = model
                        print(f"[GModLiveLink] Spawned placeholder cube for GMod ID {gmod_id}")
                    obj["last_gmod_sync_time"] = time.time()
                    rel_pos = [p_pos[0] - scene_origin[0], p_pos[1] - scene_origin[1], p_pos[2] - scene_origin[2]]
                    is_bsp_mode = bool(bpy.context.scene.gmod_livelink_map_loaded)
                    is_frozen = prop_data.get("frozen", False)
                    skin = prop_data.get("skin", 0)
                    bodygroups = prop_data.get("bodygroups", {})
                    
                    bones = prop_data.get("bones", None)
                    m_scale = prop_data.get("model_scale", 1.0)
                    
                    gmod_data_dict = {
                        "skin": skin,
                        "bodygroups": bodygroups,
                        "frozen": is_frozen,
                        "bones": bones,
                        "model_scale": m_scale
                    }
                    obj["gmod_data"] = json.dumps(gmod_data_dict)
                    
                    if is_bsp_mode:
                        bl_pos = mathutils.Vector((rel_pos[0] * scale, rel_pos[1] * scale, rel_pos[2] * scale))
                        SCRIPT_UPDATED_OBJECTS.add(obj.name)
                        obj.location = bl_pos
                        obj.rotation_euler = [math.radians(p_ang[2]), math.radians(p_ang[0]), math.radians(p_ang[1])]
                        obj.scale = (m_scale, m_scale, m_scale)
                        SCRIPT_UPDATED_OBJECTS.add(obj.name)
                        obj.gmod_physics_frozen = is_frozen
                    else:
                        bl_pos = mathutils.Vector((-rel_pos[1] * scale, rel_pos[0] * scale, rel_pos[2] * scale))
                        SCRIPT_UPDATED_OBJECTS.add(obj.name)
                        obj.location = bl_pos
                        obj.rotation_euler = [math.radians(p_ang[0]), math.radians(p_ang[2]), math.radians(p_ang[1])]
                        obj.scale = (m_scale, m_scale, m_scale)
                        SCRIPT_UPDATED_OBJECTS.add(obj.name)
                        obj.gmod_physics_frozen = is_frozen
                        
                    apply_live_state(obj, skin, bodygroups, bones=bones, scene_origin=scene_origin, scale=scale, is_bsp_mode=is_bsp_mode)
                
                bpy.context.scene.gmod_livelink_packets_recv += 1
                
            elif packet_type == "player_transform":
                import time
                if time.time() - LAST_WORLD_STATE_TIME < 2.0:
                    continue # Skip client-side camera positioning if server is active to prevent jitter
                # Position & Angle of GMod player
                pos = packet.get("pos", [0, 0, 0])
                ang = packet.get("ang", [0, 0, 0]) # Pitch, Yaw, Roll
                
                # Find or create Player placeholder camera/empty
                obj_name = "GMod_Player_Camera"
                camera_obj = bpy.data.objects.get(obj_name)
                
                if not camera_obj:
                    # Create a camera
                    camera_data = bpy.data.cameras.new(name=obj_name)
                    camera_obj = bpy.data.objects.new(name=obj_name, object_data=camera_data)
                    get_target_collection("GMOD_PLAYERS").objects.link(camera_obj)
                    camera_obj.rotation_mode = 'XYZ'
                    print(f"[GModLiveLink] Created camera placeholder: {obj_name}")
                
                # Read scene origin from scene custom properties if it exists
                scene_origin = bpy.context.scene.get("gmod_scene_origin", [0.0, 0.0, 0.0])
                
                # Subtract origin to match recentered imported scene
                rel_pos = [
                    pos[0] - scene_origin[0],
                    pos[1] - scene_origin[1],
                    pos[2] - scene_origin[2]
                ]
                
                # Convert GMod world position and angles to Blender space
                scale = bpy.context.scene.gmod_global_scale
                is_bsp_mode = bool(bpy.context.scene.gmod_livelink_map_loaded)
                
                if is_bsp_mode:
                    bl_pos = mathutils.Vector((rel_pos[0] * scale, rel_pos[1] * scale, rel_pos[2] * scale))
                    p = math.radians(90 - ang[0])
                    y = math.radians(ang[1] - 90)
                    r = math.radians(ang[2])
                else:
                    bl_pos = mathutils.Vector((-rel_pos[1] * scale, rel_pos[0] * scale, rel_pos[2] * scale))
                    p = math.radians(90 - ang[0])
                    y = math.radians(ang[1])
                    r = math.radians(ang[2])
                
                # Store target position and rotation on the object
                camera_obj["target_loc"] = list(bl_pos)
                camera_obj["target_rot"] = [p, r, y]
                
                # Increment packet counter
                bpy.context.scene.gmod_livelink_packets_recv += 1
                
                # Process active props sent from GMod
                props_data = packet.get("props", [])
                for prop_data in props_data:
                    gmod_id = prop_data.get("gmod_id")
                    model = prop_data.get("model", "")
                    p_pos = prop_data.get("pos", [0, 0, 0])
                    p_ang = prop_data.get("ang", [0, 0, 0])
                    
                    is_operator = (model == "models/maxofs2d/camera.mdl")
                    obj_name = "GMod_Operator_Camera" if is_operator else f"GMod_Prop_{gmod_id}"
                    obj = bpy.data.objects.get(obj_name)
                    
                    import time
                    if obj and time.time() - obj.get("last_user_move_time", 0.0) < 1.5:
                        continue
                        
                    if not obj:
                        if is_operator:
                            camera_data = bpy.data.cameras.new(name=obj_name)
                            obj = bpy.data.objects.new(name=obj_name, object_data=camera_data)
                            bpy.context.scene.collection.objects.link(obj)
                            obj.rotation_mode = 'XYZ'
                            obj["gmod_id"] = gmod_id
                            obj["model_path"] = model
                            obj["gmod_model"] = model
                            print("[GModLiveLink] Created Operator Camera object in Blender.")
                        else:
                            mesh = bpy.data.meshes.new(name=obj_name)
                            obj = bpy.data.objects.new(name=obj_name, object_data=mesh)
                            
                            import bmesh
                            bm = bmesh.new()
                            scale = bpy.context.scene.gmod_global_scale
                            is_bsp_mode = bool(bpy.context.scene.gmod_livelink_map_loaded)
                            
                            obb_min = prop_data.get("obb_mins")
                            obb_max = prop_data.get("obb_maxs")
                            
                            if obb_min and obb_max:
                                if is_bsp_mode:
                                    min_x, min_y, min_z = obb_min[0] * scale, obb_min[1] * scale, obb_min[2] * scale
                                    max_x, max_y, max_z = obb_max[0] * scale, obb_max[1] * scale, obb_max[2] * scale
                                else:
                                    min_x, min_y, min_z = -obb_max[1] * scale, obb_min[0] * scale, obb_min[2] * scale
                                    max_x, max_y, max_z = -obb_min[1] * scale, obb_max[0] * scale, obb_max[2] * scale
                                
                                # Create proper bounding box with 8 vertices
                                verts = [
                                    (min_x, min_y, min_z), (max_x, min_y, min_z),
                                    (min_x, max_y, min_z), (max_x, max_y, min_z),
                                    (min_x, min_y, max_z), (max_x, min_y, max_z),
                                    (min_x, max_y, max_z), (max_x, max_y, max_z)
                                ]
                                for v_co in verts:
                                    bm.verts.new(v_co)
                                
                                # Create faces for the cube
                                bm.verts.ensure_lookup_table()
                                bm.faces.new((
                                    bm.verts[0], bm.verts[1], bm.verts[3], bm.verts[2]  # bottom
                                ))
                                bm.faces.new((
                                    bm.verts[4], bm.verts[5], bm.verts[7], bm.verts[6]  # top
                                ))
                                bm.faces.new((
                                    bm.verts[0], bm.verts[1], bm.verts[5], bm.verts[4]  # front
                                ))
                                bm.faces.new((
                                    bm.verts[2], bm.verts[3], bm.verts[7], bm.verts[6]  # back
                                ))
                                bm.faces.new((
                                    bm.verts[0], bm.verts[2], bm.verts[6], bm.verts[4]  # left
                                ))
                                bm.faces.new((
                                    bm.verts[1], bm.verts[3], bm.verts[7], bm.verts[5]  # right
                                ))
                            else:
                                cube_size = 20.0 * scale
                                bmesh.ops.create_cube(bm, size=cube_size)
                                    
                            bm.to_mesh(mesh)
                            bm.free()
                            
                            bpy.context.scene.collection.objects.link(obj)
                            obj.rotation_mode = 'XYZ'
                            obj["gmod_id"] = gmod_id
                            obj["model_path"] = model
                            obj["gmod_model"] = model
                            obj["gmod_class"] = prop_data.get("class", "prop_physics")
                            print(f"[GModLiveLink] Spawned placeholder cube for GMod ID {gmod_id}")
                        
                    import time
                    obj["last_gmod_sync_time"] = time.time()
                    
                    if bpy.context.scene.gmod_livelink_auto_refine and obj.type == 'MESH' and len(obj.data.vertices) == 8 and model:
                        add_log(f"Prop Refine ATTEMPT: {model} (ID {gmod_id})")
                        scene_origin = bpy.context.scene.get("gmod_scene_origin", [0.0, 0.0, 0.0])
                        rel_pos = [p_pos[0] - scene_origin[0], p_pos[1] - scene_origin[1], p_pos[2] - scene_origin[2]]
                        scale = bpy.context.scene.gmod_global_scale
                        is_bsp_mode = bool(bpy.context.scene.gmod_livelink_map_loaded)
                        if is_bsp_mode:
                            obj.location = mathutils.Vector((rel_pos[0] * scale, rel_pos[1] * scale, rel_pos[2] * scale))
                            obj.rotation_euler = [math.radians(p_ang[2]), math.radians(p_ang[0]), math.radians(p_ang[1])]
                        else:
                            obj.location = mathutils.Vector((-rel_pos[1] * scale, rel_pos[0] * scale, rel_pos[2] * scale))
                            obj.rotation_euler = [math.radians(p_ang[0]), math.radians(p_ang[1]), math.radians(p_ang[2])]
                        
                        refined = refine_single_object(obj)
                        if refined:
                            obj = refined
                            add_log(f"Prop Refine SUCCESS: {model} (ID {gmod_id})")
                        else:
                            add_log(f"Prop Refine FAILED: {model} (ID {gmod_id})")
                    
                    # Skip GMod position updates if user is controlling this object
                    user_control_timeout = obj.get("user_control_timeout", obj.gmod_user_control_timeout if hasattr(obj, 'gmod_user_control_timeout') else 10.0)
                    if time.time() - obj.get("last_user_move_time", 0.0) < user_control_timeout:
                        add_log(f"User control active for {obj.name}, skipping GMod sync")
                        continue
                    
                    scene_origin = bpy.context.scene.get("gmod_scene_origin", [0.0, 0.0, 0.0])
                    rel_pos = [p_pos[0] - scene_origin[0], p_pos[1] - scene_origin[1], p_pos[2] - scene_origin[2]]
                    scale = bpy.context.scene.gmod_global_scale
                    
                    is_bsp_mode = bool(bpy.context.scene.gmod_livelink_map_loaded)
                    is_frozen = prop_data.get("frozen", False)
                    skin = prop_data.get("skin", 0)
                    bodygroups = prop_data.get("bodygroups", {})
                    p_bones = prop_data.get("bones")
                    ent_class = prop_data.get("class", "prop_physics")
                    obj["gmod_class"] = ent_class
                    
                    gmod_data_dict = {
                        "skin": skin,
                        "bodygroups": bodygroups,
                        "frozen": is_frozen
                    }
                    obj["gmod_data"] = json.dumps(gmod_data_dict)
                    
                    if is_bsp_mode:
                        bl_pos = mathutils.Vector((rel_pos[0] * scale, rel_pos[1] * scale, rel_pos[2] * scale))
                        SCRIPT_UPDATED_OBJECTS.add(obj.name)
                        obj.location = bl_pos
                        if is_operator:
                            obj.rotation_euler = [math.radians(90 - p_ang[0]), math.radians(p_ang[2]), math.radians(p_ang[1] - 90)]
                        else:
                            obj.rotation_euler = [math.radians(p_ang[2]), math.radians(p_ang[0]), math.radians(p_ang[1])]
                        SCRIPT_UPDATED_OBJECTS.add(obj.name)
                        obj.gmod_physics_frozen = is_frozen
                    else:
                        bl_pos = mathutils.Vector((-rel_pos[1] * scale, rel_pos[0] * scale, rel_pos[2] * scale))
                        SCRIPT_UPDATED_OBJECTS.add(obj.name)
                        obj.location = bl_pos
                        if is_operator:
                            obj.rotation_euler = [math.radians(90 - p_ang[0]), math.radians(p_ang[2]), math.radians(p_ang[1])]
                        else:
                            obj.rotation_euler = [math.radians(p_ang[0]), math.radians(p_ang[2]), math.radians(p_ang[1])]
                        SCRIPT_UPDATED_OBJECTS.add(obj.name)
                        obj.gmod_physics_frozen = is_frozen
                        
                    apply_live_state(obj, skin, bodygroups, bones=p_bones, scene_origin=scene_origin, scale=scale, is_bsp_mode=is_bsp_mode)
                
            elif packet_type == "entity_spawn":
                gmod_id = packet.get("gmod_id")
                model = packet.get("model", "")
                pos = packet.get("pos", [0, 0, 0])
                ang = packet.get("ang", [0, 0, 0])
                
                obj_name = f"GMod_Prop_{gmod_id}"
                obj = bpy.data.objects.get(obj_name)
                
                if not obj:
                    mesh = bpy.data.meshes.new(name=obj_name)
                    obj = bpy.data.objects.new(name=obj_name, object_data=mesh)
                    
                    import bmesh
                    bm = bmesh.new()
                    scale = bpy.context.scene.gmod_global_scale
                    is_bsp_mode = bool(bpy.context.scene.gmod_livelink_map_loaded)
                    
                    obb_min = packet.get("obb_mins")
                    obb_max = packet.get("obb_maxs")
                    
                    if obb_min and obb_max:
                        if is_bsp_mode:
                            min_x, min_y, min_z = obb_min[0] * scale, obb_min[1] * scale, obb_min[2] * scale
                            max_x, max_y, max_z = obb_max[0] * scale, obb_max[1] * scale, obb_max[2] * scale
                        else:
                            min_x, min_y, min_z = -obb_max[1] * scale, obb_min[0] * scale, obb_min[2] * scale
                            max_x, max_y, max_z = -obb_min[1] * scale, obb_max[0] * scale, obb_max[2] * scale
                        
                        # Create proper bounding box with 8 vertices
                        verts = [
                            (min_x, min_y, min_z), (max_x, min_y, min_z),
                            (min_x, max_y, min_z), (max_x, max_y, min_z),
                            (min_x, min_y, max_z), (max_x, min_y, max_z),
                            (min_x, max_y, max_z), (max_x, max_y, max_z)
                        ]
                        for v_co in verts:
                            bm.verts.new(v_co)
                        
                        # Create faces for the cube
                        bm.verts.ensure_lookup_table()
                        bm.faces.new((
                            bm.verts[0], bm.verts[1], bm.verts[3], bm.verts[2]  # bottom
                        ))
                        bm.faces.new((
                            bm.verts[4], bm.verts[5], bm.verts[7], bm.verts[6]  # top
                        ))
                        bm.faces.new((
                            bm.verts[0], bm.verts[1], bm.verts[5], bm.verts[4]  # front
                        ))
                        bm.faces.new((
                            bm.verts[2], bm.verts[3], bm.verts[7], bm.verts[6]  # back
                        ))
                        bm.faces.new((
                            bm.verts[0], bm.verts[2], bm.verts[6], bm.verts[4]  # left
                        ))
                        bm.faces.new((
                            bm.verts[1], bm.verts[3], bm.verts[7], bm.verts[5]  # right
                        ))
                    else:
                        cube_size = 20.0 * scale
                        bmesh.ops.create_cube(bm, size=cube_size)
                            
                    bm.to_mesh(mesh)
                    bm.free()
                    
                    bpy.context.scene.collection.objects.link(obj)
                    obj.rotation_mode = 'XYZ'
                    obj["gmod_id"] = gmod_id
                    obj["model_path"] = model
                    obj["gmod_model"] = model
                    
                    add_log(f"Spawned: {model.split('/')[-1]} (ID {gmod_id})")
                    
                    if bpy.context.scene.gmod_livelink_auto_refine and model:
                        add_log(f"Entity Spawn Refine ATTEMPT: {model} (ID {gmod_id})")
                        # Pre-position the placeholder so refined model is spawned in place
                        scene_origin = bpy.context.scene.get("gmod_scene_origin", [0.0, 0.0, 0.0])
                        rel_pos = [pos[0] - scene_origin[0], pos[1] - scene_origin[1], pos[2] - scene_origin[2]]
                        is_bsp_mode = bool(bpy.context.scene.gmod_livelink_map_loaded)
                        if is_bsp_mode:
                            obj.location = mathutils.Vector((rel_pos[0] * scale, rel_pos[1] * scale, rel_pos[2] * scale))
                            obj.rotation_euler = [math.radians(ang[2]), math.radians(ang[0]), math.radians(ang[1])]
                        else:
                            obj.location = mathutils.Vector((-rel_pos[1] * scale, rel_pos[0] * scale, rel_pos[2] * scale))
                            obj.rotation_euler = [math.radians(ang[0]), math.radians(ang[1]), math.radians(ang[2])]
                        
                        refined = refine_single_object(obj)
                        if refined:
                            obj = refined
                            add_log(f"Entity Spawn Refine SUCCESS: {model} (ID {gmod_id})")
                        else:
                            add_log(f"Entity Spawn Refine FAILED: {model} (ID {gmod_id})")
                
                # Skip GMod position updates if user is controlling this object
                user_control_timeout = obj.get("user_control_timeout", obj.gmod_user_control_timeout if hasattr(obj, 'gmod_user_control_timeout') else 10.0)
                if time.time() - obj.get("last_user_move_time", 0.0) < user_control_timeout:
                    add_log(f"User control active for {obj.name}, skipping GMod sync")
                    continue
                
                scene_origin = bpy.context.scene.get("gmod_scene_origin", [0.0, 0.0, 0.0])
                rel_pos = [pos[0] - scene_origin[0], pos[1] - scene_origin[1], pos[2] - scene_origin[2]]
                scale = bpy.context.scene.gmod_global_scale
                
                is_bsp_mode = bool(bpy.context.scene.gmod_livelink_map_loaded)
                is_frozen = packet.get("frozen", False)
                skin = packet.get("skin", 0)
                bodygroups = packet.get("bodygroups", {})
                
                gmod_data_dict = {
                    "skin": skin,
                    "bodygroups": bodygroups,
                    "frozen": is_frozen
                }
                obj["gmod_data"] = json.dumps(gmod_data_dict)
                
                if is_bsp_mode:
                    bl_pos = mathutils.Vector((rel_pos[0] * scale, rel_pos[1] * scale, rel_pos[2] * scale))
                    p = math.radians(ang[2]) # Roll
                    y = math.radians(ang[1]) # Yaw
                    r = math.radians(ang[0]) # Pitch
                    SCRIPT_UPDATED_OBJECTS.add(obj.name)
                    obj.location = bl_pos
                    obj.rotation_euler = [p, r, y]
                else:
                    bl_pos = mathutils.Vector((-rel_pos[1] * scale, rel_pos[0] * scale, rel_pos[2] * scale))
                    p = math.radians(ang[0])
                    y = math.radians(ang[1])
                    r = math.radians(ang[2])
                    SCRIPT_UPDATED_OBJECTS.add(obj.name)
                    obj.location = bl_pos
                    obj.rotation_euler = [p, r, y]
                    
                apply_live_state(obj, skin, bodygroups, bones=packet.get("bones"), scene_origin=scene_origin, scale=scale, is_bsp_mode=is_bsp_mode)
                
            elif packet_type == "entity_delete":
                gmod_id = packet.get("gmod_id")
                obj_name = f"GMod_Prop_{gmod_id}"
                obj = bpy.data.objects.get(obj_name)
                if obj:
                    bpy.data.objects.remove(obj, do_unlink=True)
                    add_log(f"Deleted: Prop ID {gmod_id}")
                
        except queue.Empty:
            break
        except Exception as e:
            print(f"[GModLiveLink] Timer processing error: {e}")
            break
            
    # Perform smooth interpolation (LERP) for all player cameras
    import time
    all_cams = [o for o in bpy.data.objects
                if (o.name == "GMod_Player_Camera" or o.name.startswith("GMod_Player_"))
                and o.type != 'ARMATURE'
                and "target_loc" in o]
    
    # Force send transform packets for user-controlled objects every frame
    for camera_obj in all_cams:
        user_control_timeout = camera_obj.get("user_control_timeout", camera_obj.gmod_user_control_timeout if hasattr(camera_obj, 'gmod_user_control_timeout') else 10.0)
        is_user_controlled = time.time() - camera_obj.get("last_user_move_time", 0.0) < user_control_timeout
        
        if is_user_controlled:
            # Send transform packet immediately for user-controlled objects
            scale = scene.gmod_global_scale
            scene_origin = scene.get("gmod_scene_origin", [0.0, 0.0, 0.0])
            is_bsp_mode = bool(scene.gmod_livelink_map_loaded)
            
            if is_bsp_mode:
                gmod_pos = [
                    (camera_obj.location.x / scale) + scene_origin[0],
                    (camera_obj.location.y / scale) + scene_origin[1],
                    (camera_obj.location.z / scale) + scene_origin[2]
                ]
                rot = camera_obj.rotation_euler
                gmod_ang = [
                    90 - math.degrees(rot.x),
                    math.degrees(rot.z) + 90,
                    math.degrees(rot.y)
                ]
            else:
                gmod_pos = [
                    (camera_obj.location.y / scale) + scene_origin[0],
                    (-camera_obj.location.x / scale) + scene_origin[1],
                    (camera_obj.location.z / scale) + scene_origin[2]
                ]
                rot = camera_obj.rotation_euler
                gmod_ang = [
                    90 - math.degrees(rot.x),
                    math.degrees(rot.z),
                    math.degrees(rot.y)
                ]
            
            packet = {
                "type": "player_teleport",
                "pos": gmod_pos,
                "ang": gmod_ang,
                "scale": [camera_obj.scale.x, camera_obj.scale.y, camera_obj.scale.z]
            }
            if camera_obj.get("steamid"):
                packet["steamid"] = camera_obj["steamid"]
            elif camera_obj.name.startswith("GMod_Player_"):
                packet["steamid"] = camera_obj.name.replace("GMod_Player_", "")
            
            OUTGOING_QUEUE.put(packet)
            add_log(f"Force transform sent: {camera_obj.name}")
            continue  # Skip interpolation for user-controlled objects
        try:
            target_loc = mathutils.Vector(camera_obj["target_loc"])
            target_rot = mathutils.Euler(camera_obj["target_rot"], 'XYZ')
            camera_obj["last_gmod_sync_time"] = time.time()
            SCRIPT_UPDATED_OBJECTS.add(camera_obj.name)
            camera_obj.location = camera_obj.location.lerp(target_loc, 0.25)
            q_curr = camera_obj.rotation_euler.to_quaternion()
            q_targ = target_rot.to_quaternion()
            q_interp = q_curr.slerp(q_targ, 0.25)
            camera_obj.rotation_euler = q_interp.to_euler('XYZ')
        except Exception as e:
            print(f"[GModLiveLink] Interpolation error ({camera_obj.name}): {e}")
    # Mocap Animation Recording
    if bpy.context.scene.gmod_livelink_record:
        current_frame = bpy.context.scene.frame_current
        for obj in bpy.data.objects:
            gmod_id = obj.get("gmod_id")
            steamid = obj.get("steamid")
            if (gmod_id is not None) or (steamid is not None):
                if obj.name in SCRIPT_UPDATED_OBJECTS:
                    try:
                        obj.keyframe_insert(data_path="location", frame=current_frame)
                        if obj.rotation_mode == 'QUATERNION':
                            obj.keyframe_insert(data_path="rotation_quaternion", frame=current_frame)
                        else:
                            obj.keyframe_insert(data_path="rotation_euler", frame=current_frame)
                        if obj.type == 'ARMATURE':
                            for bone in obj.pose.bones:
                                bone.keyframe_insert(data_path="location", frame=current_frame)
                                if bone.rotation_mode == 'QUATERNION':
                                    bone.keyframe_insert(data_path="rotation_quaternion", frame=current_frame)
                                elif bone.rotation_mode == 'AXIS_ANGLE':
                                    bone.keyframe_insert(data_path="rotation_axis_angle", frame=current_frame)
                                else:
                                    bone.keyframe_insert(data_path="rotation_euler", frame=current_frame)
                    except Exception as k_err:
                        pass
        bpy.context.scene.frame_current += 1
            
    return 0.01  # Run again in 10ms


# Desgraph update handler to track Blender object shifts
def livelink_depsgraph_handler(scene, depsgraph):
    if not scene.gmod_livelink_active:
        return
        
    import time
    current_time = time.time()
    
    for update in depsgraph.updates:
        obj = update.id
        if isinstance(obj, bpy.types.Object):
            # Skip throttling for user-controlled objects - send immediately
            user_control_timeout = obj.get("user_control_timeout", obj.gmod_user_control_timeout if hasattr(obj, 'gmod_user_control_timeout') else 10.0)
            is_user_controlled = current_time - obj.get("last_user_move_time", 0.0) < user_control_timeout
            
            if not is_user_controlled and current_time - obj.get("last_gmod_sync_time", 0.0) < 0.2:
                continue
                
            # Handle GMod player camera manual movement
            is_player_cam = (obj.name == "GMod_Player_Camera") or obj.name.startswith("GMod_Player_") or (obj.name == "GMod_Operator_Camera")
            if is_player_cam:
                if update.is_updated_transform:
                    # User dragged the camera manually!
                    import time
                    obj["last_user_move_time"] = time.time()
                    
                    # Set target_loc/rot to current location so interpolation doesn't fight the user
                    obj["target_loc"] = list(obj.location)
                    obj["target_rot"] = list(obj.rotation_euler)
                    
                    scale = scene.gmod_global_scale
                    scene_origin = scene.get("gmod_scene_origin", [0.0, 0.0, 0.0])
                    is_bsp_mode = bool(scene.gmod_livelink_map_loaded)
                    
                    if is_bsp_mode:
                        gmod_pos = [
                            (obj.location.x / scale) + scene_origin[0],
                            (obj.location.y / scale) + scene_origin[1],
                            (obj.location.z / scale) + scene_origin[2]
                        ]
                        import math
                        rot = obj.rotation_euler
                        gmod_ang = [
                            90 - math.degrees(rot.x),
                            math.degrees(rot.z) + 90,
                            math.degrees(rot.y)
                        ]
                    else:
                        gmod_pos = [
                            (obj.location.y / scale) + scene_origin[0],
                            (-obj.location.x / scale) + scene_origin[1],
                            (obj.location.z / scale) + scene_origin[2]
                        ]
                        import math
                        rot = obj.rotation_euler
                        gmod_ang = [
                            90 - math.degrees(rot.x),
                            math.degrees(rot.z),
                            math.degrees(rot.y)
                        ]
                    
                    packet = {
                        "type": "player_teleport",
                        "pos": gmod_pos,
                        "ang": gmod_ang,
                        "scale": [obj.scale.x, obj.scale.y, obj.scale.z]
                    }
                    if obj.name == "GMod_Operator_Camera":
                        pass
                    elif obj.get("steamid"):
                        packet["steamid"] = obj["steamid"]
                    elif obj.name.startswith("GMod_Player_"):
                        # Recover name from prefix
                        packet["name"] = obj.name[12:]
                        
                    OUTGOING_QUEUE.put(packet)
                    add_log(f"Player teleport packet sent: {obj.name}")
                continue
                
            # Queue the transform update if the object coordinates were updated
            if update.is_updated_transform:
                # User dragged the prop manually!
                import time
                obj["last_user_move_time"] = time.time()
                
                loc = obj.location
                rot = obj.rotation_euler
                
                # Retrieve GMod Entity Index
                gmod_id = obj.get("gmod_id")
                if gmod_id is None:
                    parent = obj.parent
                    while parent:
                        gmod_id = parent.get("gmod_id")
                        if gmod_id is not None:
                            break
                        parent = parent.parent
                
                if gmod_id is None:
                    continue
                    
                # Convert Blender coordinates back to GMod units (inches) and add scene origin
                scale = scene.gmod_global_scale
                scene_origin = scene.get("gmod_scene_origin", [0.0, 0.0, 0.0])
                is_bsp_mode = bool(scene.gmod_livelink_map_loaded)
                
                if is_bsp_mode:
                    gmod_pos = [
                        (loc.x / scale) + scene_origin[0],
                        (loc.y / scale) + scene_origin[1],
                        (loc.z / scale) + scene_origin[2]
                    ]
                    import math
                    gmod_ang = [
                        math.degrees(rot.y), # Pitch
                        math.degrees(rot.z), # Yaw
                        math.degrees(rot.x)  # Roll
                    ]
                else:
                    gmod_pos = [
                        (loc.y / scale) + scene_origin[0],
                        (-loc.x / scale) + scene_origin[1],
                        (loc.z / scale) + scene_origin[2]
                    ]
                    import math
                    gmod_ang = [
                        math.degrees(rot.x),
                        math.degrees(rot.z),
                        math.degrees(rot.y)
                    ]
                
                packet = {
                    "type": "entity_transform",
                    "name": obj.name,
                    "pos": gmod_pos,
                    "ang": gmod_ang,
                    "scale": [obj.scale.x, obj.scale.y, obj.scale.z]
                }
                packet["gmod_id"] = int(gmod_id)
                OUTGOING_QUEUE.put(packet)
                add_log(f"Entity transform packet sent: {obj.name} (ID {gmod_id})")


class GModStartLiveLinkServer(bpy.types.Operator):
    bl_idname = "gmod.start_livelink_server"
    bl_label = "Start Live Link Server"
    bl_description = "Start the local HTTP sync server in the background"
    bl_options = {'REGISTER'}

    def execute(self, context):
        global LIVELINK_THREAD, LIVELINK_DEPSGRAPH_HANDLER
        
        scene = context.scene
        if scene.gmod_livelink_active:
            self.report({'WARNING'}, "Live Link server is already running.")
            return {'CANCELLED'}
            
        FAILED_REFINE_IDS.clear()
            
        port = scene.gmod_livelink_port
        
        # Start server thread
        LIVELINK_THREAD = threading.Thread(target=run_server, args=(port,), daemon=True)
        LIVELINK_THREAD.start()
        
        # Set status properties
        scene.gmod_livelink_active = True
        scene.gmod_livelink_packets_recv = 0
        
        # Register main-thread timer
        bpy.app.timers.register(livelink_timer_callback)
        
        # Register depsgraph update listener
        LIVELINK_DEPSGRAPH_HANDLER = livelink_depsgraph_handler
        bpy.app.handlers.depsgraph_update_post.append(LIVELINK_DEPSGRAPH_HANDLER)
        
        self.report({'INFO'}, f"Live Link server started on port {port}")
        return {'FINISHED'}


class GModStopLiveLinkServer(bpy.types.Operator):
    bl_idname = "gmod.stop_livelink_server"
    bl_label = "Stop Live Link Server"
    bl_description = "Stop the background local HTTP server"
    bl_options = {'REGISTER'}

    def execute(self, context):
        global LIVELINK_SERVER, LIVELINK_THREAD, LIVELINK_DEPSGRAPH_HANDLER
        
        scene = context.scene
        if not scene.gmod_livelink_active:
            self.report({'WARNING'}, "Live Link server is not running.")
            return {'CANCELLED'}
            
        scene.gmod_livelink_active = False
        scene.gmod_livelink_map_loaded = ""
        
        # Shutdown server
        if LIVELINK_SERVER:
            LIVELINK_SERVER.shutdown()
            LIVELINK_SERVER.server_close()
            LIVELINK_SERVER = None
            
        LIVELINK_THREAD = None
        
        # Unregister depsgraph handler
        if LIVELINK_DEPSGRAPH_HANDLER in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(LIVELINK_DEPSGRAPH_HANDLER)
            LIVELINK_DEPSGRAPH_HANDLER = None
            
        # Empty queues
        while not INCOMING_QUEUE.empty():
            INCOMING_QUEUE.get()
        while not OUTGOING_QUEUE.empty():
            OUTGOING_QUEUE.get()
            
        self.report({'INFO'}, "Live Link server stopped.")
        return {'FINISHED'}


class GModLaunchDedicatedServer(bpy.types.Operator):
    bl_idname = "gmod.launch_srcds"
    bl_label = "Launch GMod Server"
    bl_description = "Launch Garry's Mod Dedicated Server (srcds.exe) in the background with local HTTP allowed"
    bl_options = {'REGISTER'}

    def execute(self, context):
        import os
        import subprocess
        
        scene = context.scene
        
        # Resolve GMod path
        gmod_dir = getattr(scene, "gmod_livelink_root_path", "")
        if not gmod_dir or not os.path.exists(gmod_dir):
            gmod_dir = scene.gmod_root_path
            
        if not gmod_dir or not os.path.exists(gmod_dir):
            gmod_dir = scene.gmod_weapon_root_path
            
        if not gmod_dir or not os.path.exists(gmod_dir):
            self.report({'ERROR'}, "GMod Folder is not configured or does not exist!")
            return {'CANCELLED'}
            
        # Copy addon from client folder to server folder automatically
        import shutil
        normalized_gmod_dir = os.path.abspath(gmod_dir)
        client_gmod_dir = os.path.dirname(normalized_gmod_dir)
        client_addon = os.path.join(client_gmod_dir, "garrysmod", "addons", "gmod_exporter_addon")
        server_addon = os.path.join(gmod_dir, "garrysmod", "addons", "gmod_exporter_addon")
        
        if os.path.exists(client_addon):
            try:
                os.makedirs(os.path.dirname(server_addon), exist_ok=True)
                if os.path.exists(server_addon):
                    shutil.rmtree(server_addon)
                shutil.copytree(client_addon, server_addon)
                print(f"[GModLiveLink] Auto-synced addon to server: {server_addon}")
            except Exception as e:
                print(f"[GModLiveLink] Failed to auto-sync addon to server: {e}")
            
        # Search for srcds.exe in various subdirectories
        candidate_paths = [
            os.path.join(gmod_dir, "srcds.exe"),
            os.path.join(gmod_dir, "bin", "win64", "srcds.exe"),
            os.path.join(gmod_dir, "bin", "win32", "srcds.exe"),
            os.path.join(gmod_dir, "bin", "srcds.exe"),
            # Also try parent dir in case they pointed to a subfolder
            os.path.join(os.path.dirname(gmod_dir), "srcds.exe"),
            os.path.join(os.path.dirname(gmod_dir), "bin", "win64", "srcds.exe")
        ]
        
        srcds_path = None
        for path in candidate_paths:
            if os.path.exists(path):
                srcds_path = path
                break
                
        if not srcds_path:
            self.report({'ERROR'}, f"srcds.exe not found in {gmod_dir} (checked root and bin folders)!")
            return {'CANCELLED'}
                
        # Get map name
        map_name = getattr(scene, "gmod_livelink_server_map", "gm_construct")
        if not map_name:
            map_name = "gm_construct"
            
        # Build startup arguments
        args = [
            srcds_path,
            "-game", "garrysmod",
            "-console",
            "+map", map_name,
            "+maxplayers", "4",
            "-allowlocalhttp",
            "+sv_cheats", "1",
            "+sv_allowcslua", "1"
        ]
        
        print(f"[GModLiveLink] Launching: {' '.join(args)}")
        
        try:
            # Launch in background, disconnected
            subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE, cwd=os.path.dirname(srcds_path))
            self.report({'INFO'}, f"GMod Dedicated Server launched on map '{map_name}'!")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to launch srcds.exe: {e}")
            return {'CANCELLED'}


class GModSpawnOperator(bpy.types.Operator):
    bl_idname = "gmod.spawn_operator"
    bl_label = "Spawn Operator"
    bl_description = "Spawn the Blender operator camera representation in Garry's Mod at 3D Cursor location"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        cursor = context.scene.cursor
        loc = cursor.location
        rot = cursor.rotation_euler
        scale = context.scene.gmod_global_scale
        scene_origin = context.scene.get("gmod_scene_origin", [0.0, 0.0, 0.0])
        
        # Spawn Camera object in Blender representing the Operator
        op_cam = bpy.data.objects.get("GMod_Operator_Camera")
        if not op_cam:
            camera_data = bpy.data.cameras.new(name="GMod_Operator_Camera_Data")
            camera_data.display_size = 0.5 * getattr(context.scene, 'gmod_global_scale', 0.0254)
            op_cam = bpy.data.objects.new(name="GMod_Operator_Camera", object_data=camera_data)
            get_target_collection("GMOD_CAMERAS").objects.link(op_cam)
            op_cam.rotation_mode = 'XYZ'
            print("[GModLiveLink] Created operator camera in Blender.")
        
        # Temporarily mark it as script-updated so depsgraph handler doesn't feedback loop it
        SCRIPT_UPDATED_OBJECTS.add(op_cam.name)
        op_cam.location = loc.copy()
        op_cam.rotation_euler = rot.copy()
        
        import math
        is_bsp_mode = bool(context.scene.gmod_livelink_map_loaded)
        if is_bsp_mode:
            view_pos = [
                (loc.x / scale) + scene_origin[0],
                (loc.y / scale) + scene_origin[1],
                (loc.z / scale) + scene_origin[2]
            ]
            view_rot = [
                math.degrees(rot.x),
                math.degrees(rot.z),
                math.degrees(rot.y)
            ]
        else:
            view_pos = [
                (loc.y / scale) + scene_origin[0],
                (-loc.x / scale) + scene_origin[1],
                (loc.z / scale) + scene_origin[2]
            ]
            view_rot = [
                90 - math.degrees(rot.x),
                math.degrees(rot.z),
                math.degrees(rot.y)
            ]
            
        packet = {
            "type": "spawn_operator",
            "pos": view_pos,
            "ang": view_rot
        }
        OUTGOING_QUEUE.put(packet)
        self.report({'INFO'}, "Spawned Operator Camera at 3D Cursor location.")
        return {'FINISHED'}


class GModAlignOriginWithMap(bpy.types.Operator):
    bl_idname = "gmod.align_origin_with_map"
    bl_label = "Align Origin with Map"
    bl_description = "Reset scene origin to [0,0,0] to align with imported BSP map absolute coordinates"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        context.scene["gmod_scene_origin"] = [0.0, 0.0, 0.0]
        if "gmod_scene_origin_rotation" in context.scene:
            context.scene["gmod_scene_origin_rotation"] = 0.0
        self.report({'INFO'}, "Scene origin reset to [0, 0, 0] for BSP map alignment.")
        return {'FINISHED'}


def gmod_freeze_update_callback(self, context):
    add_log(f"Freeze callback triggered: {self.name}, livelink_active={context.scene.gmod_livelink_active}")
    if not context.scene.gmod_livelink_active:
        return
    
    # Check if this update came from GMod sync (via SCRIPT_UPDATED_OBJECTS)
    if self.name in SCRIPT_UPDATED_OBJECTS:
        add_log(f"Freeze callback skipped: {self.name} in SCRIPT_UPDATED_OBJECTS")
        return
    
    # Debounce: only send if state actually changed
    import time
    last_freeze_time = self.get("last_freeze_update_time", 0.0)
    last_freeze_value = self.get("last_freeze_value", None)
    
    # Skip if value hasn't changed
    if last_freeze_value == self.gmod_physics_frozen:
        return
    
    # Skip if too soon (debounce)
    if time.time() - last_freeze_time < 0.1:  # 100ms debounce
        return
    
    gmod_id = self.get("gmod_id")
    if gmod_id is not None:
        packet = {
            "type": "freeze_prop",
            "gmod_id": int(gmod_id),
            "frozen": self.gmod_physics_frozen
        }
        OUTGOING_QUEUE.put(packet)
        self["last_freeze_update_time"] = time.time()
        self["last_freeze_value"] = self.gmod_physics_frozen
        add_log(f"Freeze packet sent: ID {gmod_id}, frozen={self.gmod_physics_frozen}")
