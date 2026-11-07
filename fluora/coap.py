"""Small CoAP helpers for the subset used by Fluora firmware 3.x."""

from __future__ import annotations

import os
import random
import socket
import struct
from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum


class CoAPType(IntEnum):
    """Define CoAP message type values used on the wire."""

    CONFIRMABLE = 0
    NON_CONFIRMABLE = 1
    ACKNOWLEDGEMENT = 2
    RESET = 3


class CoAPCode(IntEnum):
    """Define CoAP method and response code values used by Fluora."""

    EMPTY = 0
    GET = 1
    POST = 2
    PUT = 3
    DELETED = 66
    VALID = 67
    CHANGED = 68
    CONTENT = 69
    NOT_FOUND = 132


OPTION_OBSERVE = 6
OPTION_URI_PATH = 11
OPTION_CONTENT_FORMAT = 12
OPTION_BLOCK2 = 23

CONTENT_FORMAT_JSON = 50


@dataclass(frozen=True)
class CoAPOption:
    """Represent a single numbered CoAP option."""

    number: int
    value: bytes


@dataclass(frozen=True)
class CoAPMessage:
    """Represent a decoded or outbound CoAP message."""

    msg_type: CoAPType
    code: int
    message_id: int
    token: bytes
    options: tuple[CoAPOption, ...]
    payload: bytes = b""

    def option_values(self, option_number: int) -> list[bytes]:
        """Return values for all options matching the given option number."""
        return [option.value for option in self.options if option.number == option_number]


class CoAPError(RuntimeError):
    """Raised when a CoAP packet cannot be parsed or a request fails."""


def random_token(length: int = 2) -> bytes:
    """Return a random CoAP token of the requested byte length."""
    return os.urandom(length)


def random_message_id() -> int:
    """Return a random nonzero CoAP message identifier."""
    return random.randint(1, 0xFFFF)


def int_to_option_value(value: int) -> bytes:
    """Encode an integer as the shortest big-endian CoAP option value."""
    if value == 0:
        return b""
    length = (value.bit_length() + 7) // 8
    return value.to_bytes(length, "big")


def option_value_to_int(value: bytes) -> int:
    """Decode a big-endian CoAP option value as an integer."""
    if not value:
        return 0
    return int.from_bytes(value, "big")


def uri_path_options(path: str) -> list[CoAPOption]:
    """Build Uri-Path options for a slash-delimited resource path."""
    return [
        CoAPOption(OPTION_URI_PATH, part.encode("utf-8"))
        for part in path.strip("/").split("/")
        if part
    ]


def observe_register_option() -> CoAPOption:
    """Build the Observe registration option used by Fluora deltas."""
    return CoAPOption(OPTION_OBSERVE, b"")


def block2_option(number: int = 0, more: bool = False, size_exponent: int = 6) -> CoAPOption:
    """Build a Block2 option for blockwise CoAP responses."""
    if not 0 <= size_exponent <= 6:
        raise ValueError("size_exponent must be 0..6")
    value = (number << 4) | (int(more) << 3) | size_exponent
    return CoAPOption(OPTION_BLOCK2, int_to_option_value(value))


def content_format_json_option() -> CoAPOption:
    """Build a Content-Format option for JSON payloads."""
    return CoAPOption(OPTION_CONTENT_FORMAT, int_to_option_value(CONTENT_FORMAT_JSON))


def encode_message(message: CoAPMessage) -> bytes:
    """Encode a CoAP message into wire-format bytes."""
    token_length = len(message.token)
    if token_length > 8:
        raise ValueError("CoAP token length must be <= 8")

    first = (1 << 6) | (int(message.msg_type) << 4) | token_length
    packet = bytearray(struct.pack("!BBH", first, int(message.code), message.message_id))
    packet.extend(message.token)

    previous_number = 0
    for option in sorted(message.options, key=lambda item: item.number):
        delta = option.number - previous_number
        if delta < 0:
            raise ValueError("CoAP options must be sorted by option number")
        delta_nibble, delta_ext = _encode_nibble(delta)
        length_nibble, length_ext = _encode_nibble(len(option.value))
        packet.append((delta_nibble << 4) | length_nibble)
        packet.extend(delta_ext)
        packet.extend(length_ext)
        packet.extend(option.value)
        previous_number = option.number

    if message.payload:
        packet.append(0xFF)
        packet.extend(message.payload)

    return bytes(packet)


def decode_message(data: bytes) -> CoAPMessage:
    """Decode wire-format bytes into a CoAP message."""
    if len(data) < 4:
        raise CoAPError("CoAP packet is shorter than the fixed header")

    first, code, message_id = struct.unpack("!BBH", data[:4])
    version = first >> 6
    if version != 1:
        raise CoAPError(f"unsupported CoAP version: {version}")

    token_length = first & 0x0F
    if token_length > 8:
        raise CoAPError(f"invalid CoAP token length: {token_length}")
    if len(data) < 4 + token_length:
        raise CoAPError("CoAP packet ended before token")

    cursor = 4
    token = data[cursor : cursor + token_length]
    cursor += token_length

    options: list[CoAPOption] = []
    previous_number = 0
    payload = b""
    while cursor < len(data):
        if data[cursor] == 0xFF:
            cursor += 1
            payload = data[cursor:]
            break

        first_option_byte = data[cursor]
        cursor += 1
        delta_nibble = first_option_byte >> 4
        length_nibble = first_option_byte & 0x0F
        delta, cursor = _decode_nibble(delta_nibble, data, cursor)
        length, cursor = _decode_nibble(length_nibble, data, cursor)

        option_number = previous_number + delta
        value = data[cursor : cursor + length]
        if len(value) != length:
            raise CoAPError("CoAP packet ended inside an option")
        cursor += length
        options.append(CoAPOption(option_number, value))
        previous_number = option_number

    msg_type = CoAPType((first >> 4) & 0x03)
    return CoAPMessage(msg_type, code, message_id, token, tuple(options), payload)


class CoAPClient:
    """Synchronous UDP CoAP client for small Fluora requests."""

    def __init__(
        self,
        host: str,
        port: int = 5683,
        *,
        local_port: int | None = None,
        timeout: float = 2.0,
    ) -> None:
        """Initialize a UDP CoAP client for a single remote host."""
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.settimeout(timeout)
        if local_port is not None:
            self._socket.bind(("", local_port))

    def close(self) -> None:
        """Close the underlying UDP socket."""
        self._socket.close()

    def __enter__(self) -> CoAPClient:
        """Enter the context manager and return this client."""
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Exit the context manager and close the socket."""
        self.close()

    def request(
        self,
        code: CoAPCode,
        path: str,
        *,
        payload: bytes = b"",
        confirmable: bool = True,
        expect_response: bool | None = None,
        options: Iterable[CoAPOption] = (),
        token: bytes | None = None,
        message_id: int | None = None,
        timeout: float | None = None,
    ) -> CoAPMessage:
        """Send a CoAP request and optionally wait for its response."""
        token = random_token() if token is None else token
        message_id = random_message_id() if message_id is None else message_id
        request_options = [*options, *uri_path_options(path)]
        message = CoAPMessage(
            CoAPType.CONFIRMABLE if confirmable else CoAPType.NON_CONFIRMABLE,
            int(code),
            message_id,
            token,
            tuple(request_options),
            payload,
        )
        self._socket.sendto(encode_message(message), (self.host, self.port))
        should_wait = confirmable if expect_response is None else expect_response
        if not should_wait:
            return message

        return self.receive_response(
            token,
            message_id if confirmable else None,
            timeout=timeout,
        )

    def receive_response(
        self,
        token: bytes,
        message_id: int | None = None,
        *,
        timeout: float | None = None,
    ) -> CoAPMessage:
        """Receive the next response matching the given token and message ID."""
        previous_timeout = self._socket.gettimeout()
        if timeout is not None:
            self._socket.settimeout(timeout)
        try:
            while True:
                try:
                    data, _addr = self._socket.recvfrom(8192)
                except TimeoutError as exc:
                    raise CoAPError("timed out waiting for CoAP response") from exc

                response = decode_message(data)
                if response.token != token:
                    continue
                if message_id is not None and response.message_id != message_id:
                    continue
                return response
        finally:
            if timeout is not None:
                self._socket.settimeout(previous_timeout)

    def send_ack(self, message_id: int) -> None:
        """Send an empty acknowledgement for a confirmable CoAP message."""
        ack = CoAPMessage(
            CoAPType.ACKNOWLEDGEMENT,
            CoAPCode.EMPTY,
            message_id,
            b"",
            (),
        )
        self._socket.sendto(encode_message(ack), (self.host, self.port))

    def raw_socket(self) -> socket.socket:
        """Return the underlying UDP socket for custom receive loops."""
        return self._socket


def _encode_nibble(value: int) -> tuple[int, bytes]:
    """Encode a CoAP option delta or length nibble and extension bytes."""
    if value < 0:
        raise ValueError("CoAP option delta/length cannot be negative")
    if value < 13:
        return value, b""
    if value < 269:
        return 13, bytes([value - 13])
    if value < 65805:
        return 14, struct.pack("!H", value - 269)
    raise ValueError("CoAP option delta/length is too large")


def _decode_nibble(nibble: int, data: bytes, cursor: int) -> tuple[int, int]:
    """Decode a CoAP option delta or length nibble from a packet cursor."""
    if nibble < 13:
        return nibble, cursor
    if nibble == 13:
        if cursor >= len(data):
            raise CoAPError("CoAP packet ended inside extended option byte")
        return data[cursor] + 13, cursor + 1
    if nibble == 14:
        if cursor + 2 > len(data):
            raise CoAPError("CoAP packet ended inside extended option word")
        return struct.unpack("!H", data[cursor : cursor + 2])[0] + 269, cursor + 2
    raise CoAPError("reserved CoAP option nibble 15 encountered")
