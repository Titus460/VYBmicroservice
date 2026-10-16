"""RingCentral SMS helper for phone OTP delivery."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

from ringcentral import SDK

CONFIG_FILE = "ringcentral_config.json"


class RingCentralSMS:
    """Thin wrapper around the RingCentral SDK (JWT auth + SMS send)."""

    _sdk = None
    _platform = None

    def __init__(self, config_path: str | None = None):
        path = config_path or os.path.join(os.getcwd(), CONFIG_FILE)
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        self.from_number = cfg["from_phone_number"]
        client_id = cfg["client_id"]
        client_secret = cfg["client_secret"]
        server = cfg.get("server", "https://platform.ringcentral.com")
        jwt_token = cfg["jwt"]

        if RingCentralSMS._sdk is None:
            RingCentralSMS._sdk = SDK(client_id, client_secret, server)
            RingCentralSMS._platform = RingCentralSMS._sdk.platform()
            RingCentralSMS._platform.login(jwt=jwt_token)

        self.platform = RingCentralSMS._platform

    def send_sms(self, to_number: str, text: str) -> Dict[str, Any]:
        params = {
            "from": {"phoneNumber": self.from_number},
            "to": [{"phoneNumber": to_number}],
            "text": text,
        }
        response = self.platform.post(
            "/restapi/v1.0/account/~/extension/~/sms",
            params,
        )
        return response.json()
