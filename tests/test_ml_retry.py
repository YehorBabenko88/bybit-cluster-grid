from grid.ml_retry import retry_delay_seconds,classify_failure
def test_retry_backoff_is_bounded_and_classifies_data_errors_permanent():
    assert retry_delay_seconds(1)==30
    assert retry_delay_seconds(2)==60
    assert retry_delay_seconds(20)==1800
    kind,_=classify_failure(ValueError("bad dataset"))
    assert kind=="permanent"
    kind,_=classify_failure(TimeoutError("temporary"))
    assert kind=="retryable"
