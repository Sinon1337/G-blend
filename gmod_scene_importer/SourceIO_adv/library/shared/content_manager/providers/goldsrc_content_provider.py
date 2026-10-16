from typing import Iterator, Optional, Union

from gmod_scene_importer.SourceIO_adv.library.global_config import GoldSrcConfig
from gmod_scene_importer.SourceIO_adv.library.goldsrc.wad import WadFile
from gmod_scene_importer.SourceIO_adv.library.shared.app_id import SteamAppId
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.provider import ContentProvider, find_file_generic
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.providers.loose_files import LooseFilesContentProvider
from gmod_scene_importer.SourceIO_adv.library.utils import Buffer, TinyPath


class GoldSrcContentProvider(LooseFilesContentProvider):

    @property
    def steam_id(self) -> SteamAppId:
        return self._steamapp_id

    def __init__(self, filepath: TinyPath, steamapp_id: SteamAppId = SteamAppId.UNKNOWN):
        assert filepath.is_dir()
        super().__init__(filepath)
        self._steamapp_id = steamapp_id

    def find_file(self, filepath: TinyPath) -> Optional[Buffer]:
        if not GoldSrcConfig().use_hd and self.filepath.stem.endswith('_hd'):
            return None
        return find_file_generic(self.root, filepath)


class GoldSrcWADContentProvider(ContentProvider):
    def __init__(self, filepath: TinyPath, steamapp_id: SteamAppId = SteamAppId.UNKNOWN):
        assert filepath.suffix == '.wad'
        super().__init__(filepath)
        self._steamapp_id = steamapp_id
        self.wad_file = WadFile(filepath)

    def check(self, filepath: TinyPath) -> bool:
        return self.wad_file.contains(filepath)

    def get_relative_path(self, filepath: TinyPath) -> TinyPath | None:
        return None

    def get_provider_from_path(self, filepath) -> Optional['ContentProvider']:
        if self.check(filepath):
            return self

    def get_steamid_from_asset(self, asset_path: TinyPath) -> SteamAppId | None:
        if self.check(asset_path):
            return self.steam_id

    @property
    def root(self) -> TinyPath:
        return self.filepath.parent

    @property
    def name(self) -> str:
        return self.filepath.stem

    @property
    def steam_id(self) -> SteamAppId:
        return self._steamapp_id

    def find_file(self, filepath: Union[str, TinyPath]) -> Optional[Buffer]:
        return self.wad_file.get_file(filepath.stem)

    def glob(self, pattern: str) -> Iterator[tuple[TinyPath, Buffer]]:
        return iter([])
