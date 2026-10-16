from gmod_scene_importer.SourceIO_adv.library.source2.blocks.manifest import ManifestBlock
from gmod_scene_importer.SourceIO_adv.library.source2.compiled_resource import CompiledResource, DATA_BLOCK


class CompiledManifestResource(CompiledResource):

    @property
    def data_block(self):
        return self.get_block(ManifestBlock, block_id=DATA_BLOCK)
