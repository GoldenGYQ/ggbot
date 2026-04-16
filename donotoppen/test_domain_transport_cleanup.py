from __future__ import annotations

import ggbot.core.domain as domain


def test_domain_no_transport_event_model() -> None:
    # Guardrail: transport envelope lives in transport_protocol only.
    assert not hasattr(domain, "TransportEvent")
