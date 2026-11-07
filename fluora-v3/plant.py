"""High-level Fluora plant controls discovered from firmware 3.1.6 traffic."""

from __future__ import annotations

import json
import logging
import socket
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast

from .coap import (
    OPTION_BLOCK2,
    CoAPClient,
    CoAPCode,
    CoAPError,
    CoAPMessage,
    CoAPType,
    block2_option,
    decode_message,
    encode_message,
    observe_register_option,
    option_value_to_int,
    random_message_id,
    random_token,
    uri_path_options,
)
from .enums import SCENE_EFFECTS, FluoraEffect, FluoraMode, FluoraScene
from .fluora_dataclasses import SCENE_ANIMATION_PARAMETER_IDS, FluoraDiscovery, ParameterIds

DEFAULT_PARAMETER_IDS = ParameterIds()

_LOGGER = logging.getLogger(__name__)


class FluoraPlant:
    """Simple synchronous controller for a Fluora LED plant."""

    def __init__(
        self,
        host: str,
        *,
        port: int = 5683,
        local_port: int | None = None,
        timeout: float = 2.0,
        parameter_ids: ParameterIds = DEFAULT_PARAMETER_IDS,
    ) -> None:
        """Initialize a synchronous controller for a Fluora plant."""
        self.parameter_ids = parameter_ids
        self._coap = CoAPClient(host, port, local_port=local_port, timeout=timeout)

    def __enter__(self) -> FluoraPlant:
        """Enter the context manager and return this plant controller."""
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Exit the context manager and close the CoAP client."""
        self.close()

    @property
    def scene_list(self) -> list[FluoraScene]:
        """Return a list of all available Fluora scenes."""
        return list(FluoraScene)

    @property
    def effect_list(self) -> list[FluoraEffect]:
        """Return a list of all captured Fluora effects."""
        return list(FluoraEffect)

    def close(self) -> None:
        """Close the underlying CoAP client."""
        self._coap.close()

    def set_hue(self, value: float) -> dict[str, Any]:
        """Set the manual-mode hue to a normalized value."""
        return self.set_parameter(self.parameter_ids.hue, _unit_float(value))

    def set_brightness(self, value: float) -> dict[str, Any]:
        """Set the plant brightness to a normalized value."""
        return self.set_parameter(self.parameter_ids.brightness, _unit_float(value))

    def set_saturation(self, value: float) -> dict[str, Any]:
        """Set the manual-mode saturation to a normalized value."""
        return self.set_parameter(self.parameter_ids.saturation, _unit_float(value))

    def set_effect_index(self, index: int) -> dict[str, Any]:
        """Set the manual-mode animation effect by zero-based index."""
        if index < 0:
            raise ValueError("effect index must be >= 0")
        return self.set_parameter(self.parameter_ids.effect, index)

    def set_effect(self, effect: FluoraEffect | int | str) -> dict[str, Any]:
        """Set the manual-mode effect by enum, index, or name."""
        effect_value = FluoraEffect.from_value(effect)
        return self.set_effect_index(int(effect_value))

    def set_mode(self, mode: FluoraMode | int) -> dict[str, Any]:
        """Set the plant operating mode."""
        mode_value = FluoraMode(mode)
        return self.set_parameter(self.parameter_ids.mode, int(mode_value))

    def set_manual_mode(self) -> dict[str, Any]:
        """Switch the plant to manual mode."""
        return self.set_mode(FluoraMode.MANUAL)

    def set_auto_mode(self) -> dict[str, Any]:
        """Switch the plant to auto mode."""
        return self.set_mode(FluoraMode.AUTO)

    def set_scene_mode(self) -> dict[str, Any]:
        """Switch the plant to scene mode."""
        return self.set_mode(FluoraMode.SCENE)

    def set_scene(self, scene: FluoraScene | int) -> dict[str, Any]:
        """Select the active scene by enum value or integer."""
        scene_value = FluoraScene(scene)
        return self.set_parameter(self.parameter_ids.active_scene, int(scene_value))

    def set_scene_effect_index(self, scene: FluoraScene | int, index: int) -> dict[str, Any]:
        """Set the animation effect index for a specific scene."""
        if index < 0:
            raise ValueError("effect index must be >= 0")
        scene_value = FluoraScene(scene)
        _LOGGER.info("Setting scene %s effect index to %d", scene_value.name, index)
        return self.set_parameter(SCENE_ANIMATION_PARAMETER_IDS[scene_value], index)

    def set_scene_effect(
        self,
        scene: FluoraScene | int,
        effect: FluoraEffect | int | str,
    ) -> dict[str, Any]:
        """Set a scene effect by enum, index, or name."""
        effect_value = FluoraEffect.from_value(effect)
        if effect_value not in SCENE_EFFECTS:
            raise ValueError(f"{effect_value.label} is not available in scenes")
        return self.set_scene_effect_index(scene, int(effect_value))

    def set_effect_parameter(self, parameter_id: str, value: float) -> dict[str, Any]:
        """Set an animation parameter slider by captured parameter ID."""
        _LOGGER.info("Setting effect parameter %s to %f", parameter_id, value)
        return self.set_parameter(parameter_id, _unit_float(value))

    def turn_on(self) -> dict[str, Any]:
        """Turn on the plant display."""
        return self.set_parameter(self.parameter_ids.is_displaying, True)

    def turn_off(self) -> dict[str, Any]:
        """Turn off the plant display."""
        return self.set_parameter(self.parameter_ids.is_displaying, False)

    def set_parameter(self, parameter_id: str, value: Any) -> dict[str, Any]:
        """Set a raw Fluora parameter and return the sent JSON message."""
        message = _json_message("parameter", "POST", {"id": parameter_id, "value": value})
        response = self._coap.request(
            CoAPCode.POST,
            "/parameter",
            payload=_json_bytes(message),
            confirmable=True,
        )
        if response.code != CoAPCode.CHANGED:
            raise CoAPError(f"unexpected /parameter response code: {response.code}")
        _LOGGER.info("Set parameter %s to %s", parameter_id, value)
        return message

    def get_domain(self, domain: str) -> dict[str, Any]:
        """Fetch a named Fluora domain using blockwise CoAP if needed."""
        message = _json_message("domain", "GET", None)
        message["domain"] = domain
        payload = self._get_blockwise_json_payload("/domain", _json_bytes(message))
        _LOGGER.info("Fetched domain %s - %s", domain, _json_from_payload(payload))
        return _json_from_payload(payload)

    def ping(self) -> dict[str, Any]:
        """Ping the plant and return the decoded JSON response."""
        message = _json_message("ping", "GET", None)
        response = self._coap.request(CoAPCode.GET, "/ping", payload=_json_bytes(message))
        if response.code != CoAPCode.CONTENT:
            raise CoAPError(f"unexpected /ping response code: {response.code}")
        _LOGGER.info("Pinged plant with %s", _json_from_payload(response.payload))
        return _json_from_payload(response.payload)

    def _get_blockwise_json_payload(self, path: str, payload: bytes) -> bytes:
        """Fetch and concatenate a blockwise JSON response body."""
        token = random_token()
        chunks: list[bytes] = []
        block_number = 0
        next_payload = payload

        while True:
            response = self._coap.request(
                CoAPCode.GET,
                path,
                payload=next_payload,
                confirmable=False,
                expect_response=True,
                options=(block2_option(block_number),),
                token=token,
                message_id=random_message_id(),
            )
            if response.code != CoAPCode.CONTENT:
                raise CoAPError(f"unexpected {path} response code: {response.code}")
            if response.msg_type == CoAPType.CONFIRMABLE:
                self._coap.send_ack(response.message_id)

            chunks.append(response.payload)
            block_values = response.option_values(OPTION_BLOCK2)
            if not block_values:
                break

            block_value = option_value_to_int(block_values[0])
            more = bool(block_value & 0x08)
            if not more:
                break

            block_number = (block_value >> 4) + 1
            next_payload = b""

        return b"".join(chunks)


class FluoraStateObserver:
    """Observe /deltas and yield JSON state changes from the plant."""

    def __init__(
        self,
        host: str,
        *,
        port: int = 5683,
        local_port: int | None = None,
        timeout: float = 10.0,
    ) -> None:
        """Initialize an observer for Fluora state delta notifications."""
        self._host = host
        self._port = port
        self._coap = CoAPClient(host, port, local_port=local_port, timeout=timeout)
        self._token: bytes | None = None
        self._last_observe_sequence: int | None = None

    def __enter__(self) -> FluoraStateObserver:
        """Enter the context manager and return this state observer."""
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Exit the context manager and close the CoAP client."""
        self.close()

    @property
    def last_observe_sequence(self) -> int | None:
        """Return the most recent CoAP Observe sequence number."""
        _LOGGER.info("Last observe sequence: %s", self._last_observe_sequence)
        return self._last_observe_sequence

    def close(self) -> None:
        """Close the underlying CoAP client."""
        self._coap.close()

    def register(self) -> CoAPMessage:
        """Register for /deltas Observe notifications and return the response."""
        token = b"\x8c\xd9"
        request = CoAPMessage(
            CoAPType.CONFIRMABLE,
            CoAPCode.GET,
            int(time.time_ns() % 0xFFFF) or 1,
            token,
            (observe_register_option(), *uri_path_options("/deltas"), block2_option()),
        )
        self._coap.raw_socket().sendto(encode_message(request), (self._host, self._port))
        response = self._coap.receive_response(token, request.message_id)
        if response.code != CoAPCode.CONTENT:
            raise CoAPError(f"unexpected /deltas registration response code: {response.code}")
        self._token = token
        self._remember_observe_sequence(response)
        _LOGGER.info("Registered for /deltas Observe notifications with response %s", response)
        return response

    def deltas(self) -> Iterator[dict[str, Any]]:
        """Yield decoded JSON state deltas from the plant."""
        if self._token is None:
            self.register()

        sock = self._coap.raw_socket()
        while True:
            data, addr = sock.recvfrom(8192)
            if addr[0] != self._host:
                continue
            message = decode_message(data)
            if message.token != self._token:
                continue

            self._remember_observe_sequence(message)
            if message.msg_type == CoAPType.CONFIRMABLE:
                self._coap.send_ack(message.message_id)

            if message.payload:
                _LOGGER.info(
                    "Received /deltas notification: %s", _json_from_payload(message.payload)
                )
                yield _json_from_payload(message.payload)

    def _remember_observe_sequence(self, message: CoAPMessage) -> None:
        """Store the Observe sequence number from a CoAP message."""
        values = message.option_values(6)
        if values:
            self._last_observe_sequence = option_value_to_int(values[0])


def discover(
    *,
    broadcast_address: str = "255.255.255.255",
    local_ip: str | None = None,
    timeout: float = 1.0,
    listen_port: int = 12345,
) -> list[FluoraDiscovery]:
    """Broadcast the app's legacy OSC discovery packet and collect responses."""

    payload = _osc_discovery_payload(local_ip or _local_ipv4_hint())
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", listen_port))
        sock.settimeout(timeout)
        sock.sendto(payload, (broadcast_address, 9090))

        plants: list[FluoraDiscovery] = []
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return plants
            sock.settimeout(remaining)
            try:
                data, addr = sock.recvfrom(8192)
            except TimeoutError:
                return plants

            parsed = _parse_discovery_response(data)
            if parsed is None:
                continue
            info = parsed.get("payload", {}).get("info", {})
            plants.append(
                FluoraDiscovery(
                    address=addr[0],
                    serial=str(parsed.get("serial", "")),
                    nickname=str(info.get("nickname", "")),
                    model=str(info.get("model", "")),
                    firmware_version=str(info.get("firmware_version", "")),
                    revisions=parsed.get("payload", {}).get("revisions", {}),
                    raw=parsed,
                )
            )
            _LOGGER.info("Discovered plant %s at %s", parsed.get("serial", ""), addr[0])
    finally:
        sock.close()


def _json_message(message_type: str, method: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    """Build a Fluora JSON request envelope."""
    request_id = int(time.time() * 1000)
    message: dict[str, Any] = {
        "protocol": "1.1",
        "type": message_type,
        "method": method,
        "timestamp": _timestamp_ms(),
        "request_id": request_id,
    }
    if payload is not None:
        message["payload"] = payload
    return message


def _json_bytes(message: dict[str, Any]) -> bytes:
    """Encode a Fluora JSON message without extra whitespace."""
    return json.dumps(message, separators=(",", ":")).encode("utf-8")


def _json_from_payload(payload: bytes) -> dict[str, Any]:
    """Decode a CoAP JSON payload into a dictionary."""
    return cast(dict[str, Any], json.loads(payload.decode("utf-8")))


def _timestamp_ms() -> str:
    """Return the current UTC timestamp in Fluora's millisecond format."""
    now = datetime.now(UTC)
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _unit_float(value: float) -> float:
    """Validate and return a normalized float parameter value."""
    if not 0.0 <= value <= 1.0:
        raise ValueError("value must be between 0.0 and 1.0")
    return float(value)


def _parse_discovery_response(data: bytes) -> dict[str, Any] | None:
    """Parse a Fluora OSC discovery response payload."""
    if not data.startswith(b"${"):
        return None
    return cast(dict[str, Any], json.loads(data[1:].decode("utf-8")))


def _local_ipv4_hint() -> str:
    """Return the preferred local IPv4 address for discovery payloads."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        return "0.0.0.0"
    finally:
        sock.close()


def _osc_discovery_payload(ip_address: str) -> bytes:
    """Build the legacy OSC discovery payload for the given IPv4 address."""
    address = _osc_string("/fluoraDiscovery")
    type_tag = _osc_string("," + ("i" * len(ip_address)))
    args = b"".join(ord(char).to_bytes(4, "big", signed=True) for char in ip_address)
    return address + type_tag + args


def _osc_string(value: str) -> bytes:
    """Encode an OSC string with NUL termination and four-byte padding."""
    encoded = value.encode("ascii") + b"\0"
    padding = (-len(encoded)) % 4
    return encoded + (b"\0" * padding)
