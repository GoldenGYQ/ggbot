from __future__ import annotations

import ggbot.models.runtime_models as runtime_models


def test_runtime_models_no_transport_event_model() -> None:
    # Guardrail: transport envelope lives in transport_protocol only.
    assert not hasattr(runtime_models, "TransportEvent")
