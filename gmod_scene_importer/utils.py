import bpy
import math
import mathutils

# Constants
SCALE_FACTOR = 0.0254

def convert_source_transform(pos, ang, scale, global_scale=0.0254):
    """
    Creates a full 4x4 Blender Matrix from Source Transform Data.
    pos: [x, y, z] (Source Engine Coordinates)
    ang: [pitch, yaw, roll] (Source Engine Angles)
    scale: [sx, sy, sz]
    """
    # 1. Location Mapping
    # Source: X=Forward, Y=Left, Z=Up
    # Blender: X=Right, Y=Forward, Z=Up
    # Mapping: Blender.X = -Source.Y, Blender.Y = Source.X, Blender.Z = Source.Z
    loc_vec = mathutils.Vector((0, 0, 0))
    if pos:
        loc_vec = mathutils.Vector((-pos[1], pos[0], pos[2])) * global_scale
    
    # 2. Rotation Mapping
    # Create rotation matrix from Source Angles (Pitch=Y, Yaw=Z, Roll=X)
    rot_mat = mathutils.Matrix.Identity(4)
    if ang:
        pitch, yaw, roll = ang
        
        # In Source, Pitch is usually around Y, Yaw around Z, Roll around X
        rad_p = math.radians(pitch)
        rad_y = math.radians(yaw)
        rad_r = math.radians(roll)
        
        # Build Source rotation matrix (Order: Z, Y, X)
        mat_z = mathutils.Matrix.Rotation(rad_y, 4, 'Z')
        mat_y = mathutils.Matrix.Rotation(rad_p, 4, 'Y')
        mat_x = mathutils.Matrix.Rotation(rad_r, 4, 'X')
        source_rot = mat_z @ mat_y @ mat_x
        
        # Apply coordinate system rotation (rotate +90 degrees around Z)
        coord_fix = mathutils.Matrix.Rotation(math.radians(90), 4, 'Z')
        rot_mat = coord_fix @ source_rot

    # 3. Scale
    # Scale is a dimensionless multiplier — do NOT multiply by SCALE_FACTOR!
    scale_vec = mathutils.Vector((1.0, 1.0, 1.0))
    if scale:
        if isinstance(scale, (int, float)):
            scale_vec = mathutils.Vector((scale, scale, scale))
        else:
            scale_vec = mathutils.Vector((scale[0], scale[1], scale[2]))
    
    # 4. Compose Matrix
    mat_trans = mathutils.Matrix.Translation(loc_vec)
    mat_scale = mathutils.Matrix.Diagonal(scale_vec.to_4d())
    
    final_mat = mat_trans @ rot_mat @ mat_scale
    return final_mat

def convert_bone_local_transform(pos, ang, scale, global_scale=0.0254):
    """
    Creates a full 4x4 Blender Matrix from GMod Bone-Local transform data.
    Uses a 180-degree change of basis around the Z-axis to map:
    Blender X = -GMod X, Blender Y = -GMod Y, Blender Z = GMod Z.
    """
    loc_vec = mathutils.Vector((pos[0], pos[1], pos[2])) if pos else mathutils.Vector((0, 0, 0))
    rot_mat = mathutils.Matrix.Identity(4)
    if ang:
        pitch, yaw, roll = ang
        rad_p = math.radians(pitch)
        rad_y = math.radians(yaw)
        rad_r = math.radians(roll)
        
        mat_z = mathutils.Matrix.Rotation(rad_y, 4, 'Z')
        mat_y = mathutils.Matrix.Rotation(rad_p, 4, 'Y')
        mat_x = mathutils.Matrix.Rotation(rad_r, 4, 'X')
        rot_mat = mat_z @ mat_y @ mat_x
        
    scale_vec = mathutils.Vector((1.0, 1.0, 1.0))
    if scale:
        if isinstance(scale, (int, float)):
            scale_vec = mathutils.Vector((scale, scale, scale))
        else:
            scale_vec = mathutils.Vector((scale[0], scale[1], scale[2]))
            
    mat_trans = mathutils.Matrix.Translation(loc_vec)
    mat_scale = mathutils.Matrix.Diagonal(scale_vec.to_4d())
    
    M_gmod = mat_trans @ rot_mat @ mat_scale
    
    # 180 degree rotation around Z change of basis
    C = mathutils.Matrix.Diagonal((-1.0, -1.0, 1.0, 1.0))
    M_blender = C @ M_gmod @ C
    
    # Scale translation to Blender units
    for i in range(3):
        M_blender[i][3] *= global_scale
        
    return M_blender

def _normalize_pos(pos):
    if not pos:
        return [0, 0, 0]
    if isinstance(pos, dict):
        return [pos.get('x', 0), pos.get('y', 0), pos.get('z', 0)]
    return list(pos)

def _normalize_ang(ang):
    if not ang:
        return [0, 0, 0]
    if isinstance(ang, dict):
        return [ang.get('p', 0), ang.get('y', 0), ang.get('r', 0)]
    return list(ang)

def source_to_blender_location(pos, global_scale=0.0254):
    x, y, z = _normalize_pos(pos)
    return (-y * global_scale, x * global_scale, z * global_scale)

def source_to_blender_rotation(ang, global_scale=0.0254):
    pitch, yaw, roll = _normalize_ang(ang)
    mat = convert_source_transform([0, 0, 0], [pitch, yaw, roll], [1, 1, 1], global_scale)
    return mat.to_euler()

# GMod prop_effect uses invisible anchor models (watermelon etc.) — skip on import
PROP_EFFECT_ANCHOR_MODELS = {
    'models/props_junk/watermelon01.mdl',
    'models/props_foliage/watermelon01.mdl',
    'models/props/de_train/biohazardtank.mdl',
}

def should_skip_entity(obj_data):
    """Skip prop_effect anchors, players, and other unneeded map entities."""
    class_name = (obj_data.get('class') or '').lower()
    if class_name in ('player', 'worldspawn', 'info_player_start', 'gmod_hands', 'predicted_viewmodel'):
        return True
    model = (obj_data.get('model') or '').replace('\\', '/').lower().lstrip('/')
    if class_name == 'prop_effect':
        if model in PROP_EFFECT_ANCHOR_MODELS or model == 'models/error.mdl':
            return True
    return False

def importable_entities(entity_list):
    return [o for o in entity_list if not should_skip_entity(o)]

def extract_entity_pos(obj_data):
    pos = _normalize_pos(obj_data.get('pos') or obj_data.get('position'))
    if pos[0] == 0.0 and pos[1] == 0.0 and pos[2] == 0.0:
        bones = obj_data.get('bones', [])
        if bones:
            root_pos = None
            for b in bones:
                p = b.get('parent')
                if p is None or p < 0:
                    root_pos = b.get('pos') or b.get('position')
                    break
            if not root_pos and len(bones) > 0:
                root_pos = bones[0].get('pos') or bones[0].get('position')
            if root_pos:
                return _normalize_pos(root_pos)
    return pos

def extract_entity_ang(obj_data):
    return _normalize_ang(obj_data.get('ang') or obj_data.get('rotation_euler'))

def _normalize_scale(scale):
    if not scale:
        return [1.0, 1.0, 1.0]
    if isinstance(scale, (int, float)):
        return [float(scale), float(scale), float(scale)]
    if isinstance(scale, dict):
        x = scale.get('x', scale.get('sx', scale.get('0', 1.0)))
        y = scale.get('y', scale.get('sy', scale.get('1', 1.0)))
        z = scale.get('z', scale.get('sz', scale.get('2', 1.0)))
        return [float(x), float(y), float(z)]
    # Handle list or other iterables
    try:
        return [float(v) for v in scale]
    except:
        return [1.0, 1.0, 1.0]

def extract_entity_scale(obj_data):
    scale = obj_data.get('scale')
    return _normalize_scale(scale)

def subtract_origin(pos, origin):
    p = _normalize_pos(pos)
    return [p[0] - origin[0], p[1] - origin[1], p[2] - origin[2]]

def compute_scene_origin(data, entity_list):
    """
    Source-space offset to subtract before coordinate conversion.
    Simple export (meta.centroid): positions are already relative — no offset.
    v2 live export: absolute map coords — recenter to average position.
    """
    meta = data.get('meta') or {}
    if meta.get('centroid'):
        return [0.0, 0.0, 0.0]

    if data.get('version', 0) >= 2 or data.get('type') == 'live_scene':
        positions = [extract_entity_pos(o) for o in importable_entities(entity_list)]
        if not positions:
            return [0.0, 0.0, 0.0]
        n = len(positions)
        return [sum(p[i] for p in positions) / n for i in range(3)]

    if 'entities' in data and entity_list:
        positions = [extract_entity_pos(o) for o in importable_entities(entity_list)]
        if not positions:
            return [0.0, 0.0, 0.0]
        n = len(positions)
        return [sum(p[i] for p in positions) / n for i in range(3)]

    return [0.0, 0.0, 0.0]

def get_or_create_collection(name, parent=None):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    new_col = bpy.data.collections.new(name)
    if parent:
        parent.children.link(new_col)
    else:
        bpy.context.scene.collection.children.link(new_col)
    return new_col
