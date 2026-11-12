"""Parse the collector qualification envelope before GitHub schedules jobs."""
from pathlib import Path
import unittest

import yaml


class CollectorWorkflowYamlTest(unittest.TestCase):
    def test_qualification_workflow_parses_and_retains_hash_locked_install(self):
        path = Path(__file__).resolve().parents[2] / '.github/workflows/agent2-unqualified-worker-contract.yml'
        workflow = yaml.load(path.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
        steps = workflow['jobs']['pure-contract']['steps']
        install = next(step['run'] for step in steps if 'python -m pip install' in step.get('run', ''))
        self.assertEqual(
            install.strip(),
            'python -m pip install --only-binary=:all: --require-hashes -r '
            'support/docs/intelligence/research-identity/requirements-${{ matrix.lock }}.lock',
        )


if __name__ == '__main__':
    unittest.main()
