from pathlib import Path


def test_subscription_ack_args_are_type_checked_before_set_conversion():
    source=(Path(__file__).resolve().parents[1]/"grid"/"microstructure.py").read_text()
    validation='not isinstance(args,list) or not all(isinstance(topic,str) for topic in args)'
    matching='not set(batch_topics).issubset(set(args))'
    assert validation in source
    assert matching in source
    assert source.index(validation)<source.index(matching)
