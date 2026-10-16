from typing import Collection

from gmod_scene_importer.SourceIO_adv.library.shared.app_id import SteamAppId
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.source1 import Source1Detector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.provider import ContentProvider
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.loose_files import LooseFilesContentProvider
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.zip_content_provider import ZIPContentProvider
from gmod_scene_importer.SourceIO_adv.library.utils import backwalk_file_resolver, TinyPath


class QuakeIDTech3Detector(Source1Detector):

    @classmethod
    def game(cls) -> str:
        return 'Quake3'

    @classmethod
    def find_game_root(cls, path: TinyPath) -> TinyPath | None:
        return backwalk_file_resolver(path, 'baseq3')

    @classmethod
    def scan(cls, path: TinyPath) -> tuple[Collection[ContentProvider] | None, TinyPath | None]:
        base_dir = cls.find_game_root(path)
        if base_dir is None:
            return None, None
        providers = set()
        cls.add_provider(LooseFilesContentProvider(base_dir, SteamAppId.QUAKE3), providers)
        for pk3_file in base_dir.glob('*.pk3'):
            cls.add_provider(ZIPContentProvider(pk3_file, SteamAppId.QUAKE3), providers)

        return providers, base_dir
