"""Pure memory crash/replay protocol model, never a durable store."""
import pytest
from dataclasses import replace


def binding():
    return {'audience':'VM_LAB_TEST_ONLY','plan_sha256':'a'*64,'image_sha256':'b'*64,
            'code_sha256':'c'*64,'artifact_sha256':'d'*64,
            'host_id':'33333333-3333-4333-8333-333333333333',
            'vm_id':'22222222-2222-4222-8222-222222222222',
            'session_id':'77777777-7777-4777-8777-777777777777','policy_epoch':1}


def prepared():
    from installer.vm_replay_model import ReplayModel,AssumedValidation
    m=ReplayModel();b=binding();n=m.issue(b,'issuer',0,0,m.revision)
    claim=m.claim(n,'77777777-7777-4777-8777-777777777777',b,1,1,m.revision)
    return m,b,n,claim,AssumedValidation(claim,'e'*64,('observer','approval'))


def test_model_positive_never_proves_durability_or_guest_execution():
    m,b,n,c,v=prepared();m.consume(c,v,2,2,m.revision)
    r=m.report();assert r['status']=='BLOCKED' and r['durable_storage']=='NOT_IMPLEMENTED'
    assert not r['readiness_passed'] and not r['execution_authorized']
    assert len(r['negative_cases'])==12 and all(x['execution']=='NOT_RUN' for x in r['negative_cases'])


@pytest.mark.parametrize('point,consumed',[('before_prepare',False),('after_prepare',False),('after_commit',True),('after_ack',True)])
def test_consume_crash_boundaries_and_restart(point,consumed):
    from installer.vm_replay_model import ReplayModel,ModelCrash
    m,b,n,c,v=prepared()
    with pytest.raises(ModelCrash):m.consume(c,v,2,2,m.revision,crash=point)
    recovered=ReplayModel.recover(m.checkpoint(),m.anchor)
    if consumed:
        with pytest.raises(ValueError):recovered.consume(c,v,2,2,recovered.revision)
    else:recovered.consume(c,v,2,2,recovered.revision)


def test_torn_commit_refuses_recovery():
    from installer.vm_replay_model import ReplayModel,ModelCrash
    m,b,n,c,v=prepared()
    with pytest.raises(ModelCrash):m.consume(c,v,2,2,m.revision,crash='torn_commit')
    with pytest.raises(ValueError,match='VM_MODEL_RECOVERY_UNCERTAIN'):
        ReplayModel.recover(m.checkpoint(),m.anchor)


def test_old_snapshot_refused_against_independent_current_anchor():
    from installer.vm_replay_model import ReplayModel
    m,b,n,c,v=prepared();old=m.checkpoint();m.consume(c,v,2,2,m.revision)
    with pytest.raises(ValueError):ReplayModel.recover(old,m.anchor)
    with pytest.raises(ValueError):ReplayModel.recover(old,None)


def test_correlated_rollback_remains_an_explicit_unproven_limit():
    from installer.vm_replay_model import ReplayModel
    m,b,n,c,v=prepared();old=m.checkpoint();anchor=m.anchor;m.consume(c,v,2,2,m.revision)
    stale=ReplayModel.recover(old,anchor)  # ALL state rolled back: cannot distinguish.
    stale.consume(c,v,2,2,stale.revision)
    assert stale.report()['status']=='BLOCKED'
    assert 'INDEPENDENT_NONROLLBACK_ANCHOR_ASSUMED' in stale.report()['blockers']


def test_claim_takeover_fences_old_verifier_and_delayed_consume():
    m,b,n,c,v=prepared()
    with pytest.raises(ValueError):m.consume(c,v,8,8,m.revision)
    newer=m.claim(n,'88888888-8888-4888-8888-888888888888',b,8,8,m.revision)
    with pytest.raises(ValueError):m.consume(c,v,9,9,m.revision)
    from installer.vm_replay_model import AssumedValidation
    fresh=AssumedValidation(newer,v.evidence,v.roles)
    m.consume(newer,fresh,9,9,m.revision)


def test_concurrent_claim_compare_and_set_has_one_winner():
    from installer.vm_replay_model import ReplayModel
    from concurrent.futures import ThreadPoolExecutor
    m=ReplayModel();b=binding();n=m.issue(b,'issuer',0,0,m.revision);revision=m.revision
    def attempt(_):
        try:m.claim(n,'77777777-7777-4777-8777-777777777777',b,1,1,revision);return 1
        except ValueError:return 0
    with ThreadPoolExecutor(max_workers=4) as pool:assert sum(pool.map(attempt,range(4)))==1


@pytest.mark.parametrize('bad',['role','binding','evidence','epoch','clock','audience'])
def test_bad_validation_rotation_clock_or_bindings_never_consume(bad):
    from installer.vm_replay_model import AssumedValidation
    m,b,n,c,v=prepared();revision=m.revision
    if bad=='role':v=AssumedValidation(c,'e'*64,('observer',))
    elif bad=='binding':v=AssumedValidation(replace(c,binding='f'*64),'e'*64,('observer','approval'))
    elif bad=='evidence':v=AssumedValidation(c,'bad',('observer','approval'))
    elif bad=='epoch':m.rotate('policy-authority',2,2,m.revision)
    elif bad=='clock':
        with pytest.raises(ValueError):m.consume(c,v,20,2,m.revision)
        assert m.revision==revision;return
    elif bad=='audience':
        b['audience']='production'
        with pytest.raises(ValueError):m.claim(n,'77777777-7777-4777-8777-777777777777',b,2,2,m.revision)
        assert m.revision==revision;return
    revision=m.revision
    with pytest.raises(ValueError):m.consume(c,v,2,2,m.revision)
    assert m.revision==revision


def test_issuer_role_policy_and_monotonic_clock_are_assumptions_not_declarations():
    from installer.vm_replay_model import ReplayModel
    m=ReplayModel();b=binding()
    with pytest.raises(ValueError):m.issue(b,'observer',0,0,m.revision)
    m.issue(b,'issuer',10,10,m.revision)
    with pytest.raises(ValueError):m.issue(b,'issuer',9,9,m.revision)
    m.rotate('policy-authority',11,11,m.revision)
    with pytest.raises(ValueError):m.issue(b,'issuer',12,12,m.revision)


@pytest.mark.parametrize('point,issued',[('before_prepare',False),('after_prepare',False),('after_commit',True)])
def test_issue_ack_crash_never_returns_an_uncommitted_challenge(point,issued):
    from installer.vm_replay_model import ReplayModel,ModelCrash
    m=ReplayModel()
    with pytest.raises(ModelCrash):m.issue(binding(),'issuer',0,0,m.revision,crash=point)
    recovered=ReplayModel.recover(m.checkpoint(),m.anchor)
    assert recovered.checkpoint().image.counter==int(issued)


def test_binding_detached_before_model_clock_check(monkeypatch):
    from installer.vm_replay_model import ReplayModel
    m=ReplayModel();b=binding();check=m._check
    def mutate(*args):
        b['policy_epoch']=2
        return check(*args)
    monkeypatch.setattr(m,'_check',mutate)
    m.issue(b,'issuer',0,0,m.revision)


def test_corrupt_checkpoint_refused_even_with_a_matching_forged_anchor():
    from dataclasses import replace
    from installer.vm_replay_model import ReplayModel,Witness,Checkpoint,_fingerprint
    m=ReplayModel();bad=replace(m.checkpoint().image,clock=-1)
    witness=Witness(bad.revision,_fingerprint(bad))
    with pytest.raises(ValueError,match='VM_MODEL_RECOVERY_UNCERTAIN'):
        ReplayModel.recover(Checkpoint(bad,witness),witness)


def test_model_storage_budget_has_no_unsafe_eviction():
    from installer.vm_replay_model import ReplayModel
    m=ReplayModel();b=binding()
    for _ in range(64):m.issue(b,'issuer',0,0,m.revision)
    revision=m.revision
    with pytest.raises(ValueError,match='VM_MODEL_BUDGET'):m.issue(b,'issuer',0,0,m.revision)
    assert m.revision==revision and len(m.checkpoint().image.records)==64



def test_seeded_binding_changes_and_restarts_preserve_model_invariants():
    import copy,random
    from installer.vm_replay_model import ReplayModel
    rng=random.Random(6223923239);m=ReplayModel();b=binding();nonces=[]
    for _ in range(12):
        nonce=m.issue(b,'issuer',0,0,m.revision);nonces.append(nonce)
        m=ReplayModel.recover(m.checkpoint(),m.anchor)
    assert len(set(nonces))==12
    revision=m.revision
    for _ in range(64):
        bad=copy.deepcopy(b);field=rng.choice(list(b))
        bad[field]=('production' if field=='audience' else 2 if field=='policy_epoch' else
                    '99999999-9999-4999-8999-999999999999' if field in ('host_id','vm_id','session_id') else 'f'*64)
        with pytest.raises(ValueError):m.claim(nonces[0],'77777777-7777-4777-8777-777777777777',bad,1,1,m.revision)
        assert m.revision==revision and m.report()['status']=='BLOCKED'


@pytest.mark.parametrize('scope',['new_nonce','takeover'])
def test_validation_event_must_be_specific_to_nonce_and_claim_fence(scope):
    m,b,n,c,v=prepared()
    if scope=='new_nonce':
        other=m.issue(b,'issuer',2,2,m.revision)
        newer=m.claim(other,'88888888-8888-4888-8888-888888888888',b,2,2,m.revision)
        now=3
    else:
        newer=m.claim(n,'88888888-8888-4888-8888-888888888888',b,8,8,m.revision);now=9
    revision=m.revision
    with pytest.raises(ValueError):m.consume(newer,v,now,now,m.revision)
    assert m.revision==revision



def test_session_binding_cannot_be_substituted_on_an_issued_nonce():
    from installer.vm_replay_model import ReplayModel
    m=ReplayModel();b=binding();nonce=m.issue(b,'issuer',0,0,m.revision)
    b['session_id']='99999999-9999-4999-8999-999999999999'
    with pytest.raises(ValueError,match='VM_MODEL_BINDING'):
        m.claim(nonce,'88888888-8888-4888-8888-888888888888',b,1,1,m.revision)
