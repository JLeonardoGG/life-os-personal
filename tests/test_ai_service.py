from __future__ import annotations

import asyncio

from lifeos.services.ai_service import AIService


def test_ai_service_is_disabled_by_default(settings):
    result = asyncio.run(AIService(settings).generate("Resume mi día"))
    assert result.status == "disabled"
    assert result.text == ""
