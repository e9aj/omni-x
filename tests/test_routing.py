from omnix.config import Settings
from omnix.providers import ProviderError
from omnix.routing import Router


def test_free_mode_rejects_paid_requested_provider():
    router = Router(Settings(provider="openai", mode="FREE"))
    try:
        router.complete([{"role": "user", "content": "hello"}])
    except ProviderError as exc:
        assert "paid inference requires allow_paid=true" in str(exc)
    else:
        raise AssertionError("FREE mode accepted a paid-only route")
