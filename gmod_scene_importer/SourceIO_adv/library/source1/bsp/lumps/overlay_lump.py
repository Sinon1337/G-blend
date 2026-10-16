from gmod_scene_importer.SourceIO_adv.library.shared.app_id import SteamAppId
from gmod_scene_importer.SourceIO_adv.library.source1.bsp import Lump, ValveLumpInfo, lump_tag
from gmod_scene_importer.SourceIO_adv.library.source1.bsp.bsp_file import VBSPFile
from gmod_scene_importer.SourceIO_adv.library.source1.bsp.datatypes.overlay import Overlay, VOverlay
from gmod_scene_importer.SourceIO_adv.library.utils import Buffer


@lump_tag(45, 'LUMP_OVERLAYS')
class OverlayLump(Lump):
    def __init__(self, lump_info: ValveLumpInfo):
        super().__init__(lump_info)
        self.overlays = []

    def parse(self, buffer: Buffer, bsp: VBSPFile):
        while buffer:
            self.overlays.append(Overlay.from_buffer(buffer, self.version, bsp))
        return self


@lump_tag(45, 'LUMP_OVERLAYS', steam_id=SteamAppId.VINDICTUS)
class VOverlayLump(Lump):
    def __init__(self, lump_info: ValveLumpInfo):
        super().__init__(lump_info)
        self.overlays = []

    def parse(self, buffer: Buffer, bsp: VBSPFile):
        while buffer:
            self.overlays.append(VOverlay.from_buffer(buffer, self.version, bsp))
        return self
