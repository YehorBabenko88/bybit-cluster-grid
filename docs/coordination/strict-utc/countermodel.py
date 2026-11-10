"""Executable MODEL_ONLY counterexample; never a Consul client or time oracle.

All times are symbolic integer UTC coordinates supplied by this model's author.
No actual commit, session, principal, clock certificate or native receipt exists.
"""
from dataclasses import asdict, dataclass
import json


@dataclass(frozen=True)
class Execution:
    expiry: int
    precheck: int
    commit: int
    apply: int
    response: int
    session_invalidated: int

    def __post_init__(self):
        if any(type(x) is not int for x in asdict(self).values()):
            raise TypeError('SYMBOLIC_INTEGER_COORDINATES_ONLY')
        if not self.precheck < self.commit <= self.apply <= self.response:
            raise ValueError('MODEL_EVENT_ORDER')

    @property
    def client_precheck_accepts(self):return self.precheck < self.expiry

    @property
    def native_predicates_accept(self):
        # MODEL: fixed generation, leader/index, policy bytes and expected CAS
        # remain equal; only a separately ordered session revocation can change
        # the session check. Vanilla KV predicates do not evaluate expiry UTC.
        return self.apply < self.session_invalidated

    @property
    def native_committed(self):
        # Domain mutation accepted; a rejected transaction's Raft log entry is
        # deliberately NOT called a committed domain mutation in this model.
        return self.client_precheck_accepts and self.native_predicates_accept

    @property
    def committed_before_expiry(self):
        return self.native_committed and self.commit < self.expiry

    @property
    def reader_current_at_response(self):return self.response < self.expiry

    def client_observations(self):
        return {
            'scope':'MODEL_ONLY_UNISSUED_DATA',
            'expiry_utc_symbol':self.expiry,
            'pre_send_observed_utc_symbol':self.precheck,
            'response_observed_utc_symbol':self.response,
            'native_result_fact':'COMMITTED' if self.native_committed else 'REJECTED_THIS_ATTEMPT',
            'native_index_symbol':'41',
            'generation_session_policy_index_join':'SAME_MODEL_BYTES',
            'observed_commit_utc':None,
        }

    def private_fact(self):
        return 'COMMITTED_TIME_UNKNOWN' if self.native_committed else 'REJECTED_THIS_ATTEMPT'

    def public_observation(self):
        # A resource-blind local denial does not retract a native commit.
        if not self.reader_current_at_response:return {'status':'UNAVAILABLE'}
        return {'status':'MODEL_ONLY_NO_ISSUED_VISIBILITY'}

    def report(self):
        return {
            'scope':'MODEL_ONLY_NOT_NATIVE_OBSERVATION_OR_ACTUAL_TIME_EVIDENCE',
            'symbolic_execution':asdict(self),
            'client_observations':self.client_observations(),
            'native_domain_mutation_committed':self.native_committed,
            'strict_expiry_satisfied_in_author_supplied_schedule':self.committed_before_expiry,
            'private_fact':self.private_fact(),
            'public_observation':self.public_observation(),
            'observed_commit_utc':None,
        }


def indistinguishable_pair():
    # Both responses/applications are delayed until after expiry. In the early
    # schedule the quorum event is before expiry; in the late schedule it is
    # after expiry. All pre-send inputs, committed bytes/index and response-side
    # observations are identical. Session invalidation follows both.
    return (
        Execution(expiry=5,precheck=1,commit=2,apply=6,response=7,session_invalidated=10),
        Execution(expiry=5,precheck=1,commit=6,apply=6,response=7,session_invalidated=10),
    )


def disabled_contract():
    return {'logical_mutations':'DISABLED','native_sends':0,
            'strict_positive_admission_available':False,
            'scope':'MODEL_CONTRACT_NOT_AN_IMPLEMENTED_RUNTIME_GATE'}


if __name__=='__main__':
    early,late=indistinguishable_pair()
    print(json.dumps({'scope':'MODEL_ONLY','same_client_observations':
        early.client_observations()==late.client_observations(),
        'early':early.report(),'late':late.report(),
        'operational_policy':disabled_contract(),
        'native_rpc':0,'worker_job_calls':0,'clock_or_commit_certificate_issued':False},
        sort_keys=True,indent=2))
