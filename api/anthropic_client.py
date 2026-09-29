"""api/anthropic_client.py -- the ONE place the app builds an Anthropic client.

Twelve call sites each wrote `anthropic.Anthropic(api_key=key)` (architecture
batch A7, 29 Sep 2026). They now call client(key): the same constructor with the
same single argument, the SDK looked up at call time exactly as each site did,
so spend recording (domain/ai_usage.install_anthropic_recorder patches the SDK's
Messages class) sees every call as before. Where each key COMES FROM is still
decided at each call site -- a separate question, not changed here.
"""


def client(api_key):
    """An Anthropic SDK client for `api_key`. Raises exactly what the SDK raises."""
    import anthropic
    return anthropic.Anthropic(api_key=api_key)
