import unittest
from grid.authority_runtime_v1 import PartitionIdentity,RuntimeLayout,common_key_preimage,canonical
class LayoutTests(unittest.TestCase):
    def test_current_partition_key_has_no_job_or_generation(self):
        identity=PartitionIdentity('11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222','source.v1','partition.0')
        layout=RuntimeLayout(identity)
        self.assertEqual(layout.assignment,RuntimeLayout(identity).assignment)
        self.assertNotIn('job',layout.assignment)
        self.assertTrue(layout.assignment.startswith('unified/'+identity.cluster_id+'/runtime-v1/partitions/'))
        self.assertNotEqual(layout.assignment,RuntimeLayout(PartitionIdentity(identity.cluster_id,identity.dataset_id,'source.v2','partition.0')).assignment)
    def test_common_key_is_distinct_from_original_mux_preimage(self):
        common=common_key_preimage('11111111-1111-4111-8111-111111111111','owner1','actor1','key1')
        self.assertEqual(common['schema'],'unified.authority.command-key.v1')
        self.assertNotIn('generation',common)
        self.assertNotIn('profile',common)
    def test_invalid_identifiers_reject(self):
        with self.assertRaises(ValueError):RuntimeLayout(PartitionIdentity('bad','22222222-2222-4222-8222-222222222222','source','partition'))
        with self.assertRaises(ValueError):common_key_preimage('11111111-1111-4111-8111-111111111111','../owner','actor','key')
if __name__=='__main__':unittest.main()
