from airtable_client import is_airtable_rate_limit_error


def test_is_airtable_rate_limit_error_detects_urllib_message():
    exc = RuntimeError(
        "HTTPSConnectionPool(host='api.airtable.com', port=443): Max retries exceeded "
        "with url: /v0/app0nHzjgm8HEKOCQ/Pending?filterByFormula=%7BReview+Status%7D "
        "(Caused by ResponseError('too many 429 error responses'))"
    )
    assert is_airtable_rate_limit_error(exc)


def test_is_airtable_rate_limit_error_walks_cause():
    inner = RuntimeError("too many 429 error responses")
    outer = RuntimeError("Max retries exceeded")
    outer.__cause__ = inner
    assert is_airtable_rate_limit_error(outer)


def test_is_airtable_rate_limit_error_ignores_other_failures():
    assert not is_airtable_rate_limit_error(RuntimeError("Live record verification failed"))
    assert not is_airtable_rate_limit_error(None)
