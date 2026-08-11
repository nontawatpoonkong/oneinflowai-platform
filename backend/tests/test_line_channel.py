"""Deterministic LINE adapter tests."""

import base64
import hashlib
import hmac

from app.integrations.channels.line import LineChannelProvider


def test_line_signature_and_text_normalization():
    provider = LineChannelProvider(
        {"channel_access_token": "token", "channel_secret": "secret"}
    )
    body = b'{"events":[]}'
    signature = base64.b64encode(
        hmac.new(b"secret", body, hashlib.sha256).digest()
    ).decode()
    assert provider.verify_signature(body, signature)
    assert not provider.verify_signature(body, "invalid")
    items = provider.parse(
        {
            "events": [
                {
                    "type": "message",
                    "source": {"userId": "U1"},
                    "message": {"id": "m1", "type": "text", "text": "hello"},
                },
                {"type": "follow", "source": {"userId": "U1"}},
                {
                    "type": "message",
                    "source": {"userId": "U1"},
                    "message": {"id": "m2", "type": "image"},
                },
            ]
        }
    )
    assert [
        (item.external_user_id, item.external_message_id, item.text) for item in items
    ] == [("U1", "m1", "hello")]
