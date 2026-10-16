from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.content_detector import ContentDetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.cs2 import CS2Detector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.csgo import CSGODetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.deadlock import DeadlockDetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.gmod import GModDetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.goldsrc import GoldSrcDetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.hla import HLADetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.quake3 import QuakeIDTech3Detector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.infra import InfraDetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.left4dead import Left4DeadDetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.portal2 import Portal2Detector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.portal2_revolution import Portal2RevolutionDetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.robot_repair import RobotRepairDetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.sbox import SBoxDetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.sfm import SFMDetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.source1 import Source1Detector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.source2 import Source2Detector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.sourcemod import SourceMod
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.swjk2 import StarWarsJediKnights2Detector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.titanfall1 import TitanfallDetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.vindictus import VindictusDetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.detectors.vampire import VampireDetector
from gmod_scene_importer.SourceIO_adv.library.shared.content_manager.provider import ContentProvider
from gmod_scene_importer.SourceIO_adv.library.utils.tiny_path import TinyPath
from gmod_scene_importer.SourceIO_adv.logger import SourceLogMan

log_manager = SourceLogMan()
logger = log_manager.get_logger('game_detector')


def detect_game(path: TinyPath) -> set[ContentProvider]:
    detector_addons: list[ContentDetector] = [
        GoldSrcDetector(),
        SFMDetector(), GModDetector(), InfraDetector(), Left4DeadDetector(),
        Portal2Detector(),
        Portal2RevolutionDetector(), CSGODetector(), SourceMod(), Source1Detector(),
        # VindictusDetector(), TitanfallDetector(),
        SBoxDetector(), CS2Detector(), HLADetector(),
        RobotRepairDetector(), DeadlockDetector(), Source2Detector(),
        StarWarsJediKnights2Detector(), QuakeIDTech3Detector(),
        VampireDetector()
    ]
    content_providers = set()
    for detector in detector_addons:
        results, root_path = detector.scan(path)
        if results:
            logger.info(f"Detected {detector.game()} game: {root_path}")
            content_providers.update(results)
    return content_providers or None
