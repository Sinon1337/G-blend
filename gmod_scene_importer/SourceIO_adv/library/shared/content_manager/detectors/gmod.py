from typing import Collection
from gmod_scene_importer.SourceIO_adv.library.archives.gma import check_gma
from gmod_scene_importer.SourceIO_adv.library.shared.app_id import SteamAppId
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.source1 import Source1Detector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.provider import ContentProvider
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.gma_provider import GMAContentProvider
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.loose_files import LooseFilesContentProvider
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.source1_gameinfo_provider import Source1GameInfoProvider
from gmod_scene_importer.SourceIO_adv.library.utils import backwalk_file_resolver, TinyPath


class GModDetector(Source1Detector):

    @classmethod
    def game(cls) -> str:
        return "Garry's Mod"

    @classmethod
    def find_game_root(cls, path: TinyPath) -> TinyPath | None:
        gmod_dir = backwalk_file_resolver(path, 'garrysmod/dupes')
        if gmod_dir is not None:
            return gmod_dir.parent
        return None

    @classmethod
    def scan(cls, path: TinyPath) -> tuple[Collection[ContentProvider] | None, TinyPath | None]:
        gmod_root = cls.find_game_root(path)
        if gmod_root is None:
            return None, None
        gmod_dir = gmod_root / 'garrysmod'

        providers = set()
        initial_mod_gi_path = backwalk_file_resolver(path, "gameinfo.txt")
        if initial_mod_gi_path is not None:
            cls.add_provider(Source1GameInfoProvider(initial_mod_gi_path), providers)

        garrysmod_mod_gi_path = gmod_root / "gameinfo.txt"
        if initial_mod_gi_path != garrysmod_mod_gi_path:
            cls.add_provider(Source1GameInfoProvider(garrysmod_mod_gi_path), providers)

        cls.register_common(gmod_root.parent, providers)
        for addon in (gmod_dir / "addons").iterdir():
            if addon.suffix == ".gma":
                if not check_gma(addon):
                    continue
                provider = GMAContentProvider(addon)
            else:
                provider = LooseFilesContentProvider(addon, SteamAppId.GARRYS_MOD)
            cls.add_provider(provider, providers)
        return providers, gmod_root
