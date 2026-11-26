"""New producer namespace, unchanged historical bytes, no compatibility alias."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from market_data.provenance import digest
from market_data.research_handoff import accept_handoff


def test_canonical_producer_acceptance_and_old_identity_refusal_preserve_source():
    source = Path(__file__).parent / 'fixtures/legacy-experiment-export.synthetic.json'
    original = source.read_bytes()
    original_digest = sha256(original).digest()
    legacy = json.loads(original)
    trust = {(legacy['producer_identity'], legacy['source_revision'], legacy['run_id'], legacy['completion_receipt'])}
    assert accept_handoff(legacy, trust)['status'] == 'UNAVAILABLE'
    canonical = deepcopy(legacy)
    canonical['producer'] = 'terminan'
    canonical['completion_receipt'] = digest({key: value for key, value in canonical.items() if key != 'completion_receipt'})
    canonical_trust = {(canonical['producer_identity'], canonical['source_revision'],
                        canonical['run_id'], canonical['completion_receipt'])}
    result = accept_handoff(canonical, canonical_trust)
    assert result['status'] == 'ACCEPTED_HISTORICAL'
    assert result['execution_authority'] is False
    assert result['trading_authorized'] is False
    assert sha256(source.read_bytes()).digest() == original_digest
    assert source.read_bytes() == original
