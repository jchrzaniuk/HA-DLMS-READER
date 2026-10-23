"""Klient API dodatku z uwierzytelnianiem i dostępem tylko do odczytu."""

import asyncio
import math

from aiohttp import ClientError, ClientSession, ClientTimeout
from yarl import URL


class ReaderError(Exception):
    """Brak odpowiedzi API lub odpowiedź w nieprawidłowym formacie."""


class ReaderAuthError(ReaderError):
    """API odrzuciło token dostępu."""


def validate_snapshot(data):
    if not isinstance(data, dict) or data.get("api_version") != 1:
        raise ReaderError("Nieobsługiwana wersja API.")
    device = data.get("device")
    if not isinstance(device, dict) or not isinstance(device.get("id"), str) or not device["id"]:
        raise ReaderError("Nieprawidłowy identyfikator urządzenia.")
    if not isinstance(data.get("registers"), list):
        raise ReaderError("Nieprawidłowa lista rejestrów.")
    keys = set()
    for register in data["registers"]:
        key = register.get("key")
        if not isinstance(key, str) or not key or key in keys:
            raise ReaderError("Nieprawidłowy identyfikator rejestru.")
        keys.add(key)
        sample = register.get("sample")
        if sample is not None:
            value = sample.get("value")
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ReaderError("Nieprawidłowa wartość pomiaru.")
    if type(data.get("expire_after")) not in (int, float) or not 0 < data["expire_after"] <= 300000:
        raise ReaderError("Nieprawidłowy czas ważności pomiaru.")
    return data


class ReaderClient:
    def __init__(self, session: ClientSession, host: str, port: int, token: str):
        self.session = session
        self.url = URL.build(scheme="http", host=host, port=port, path="/v1/data")
        self.token = token

    async def get_data(self):
        try:
            async with self.session.get(self.url, headers={"Authorization": f"Bearer {self.token}"},
                                        timeout=ClientTimeout(total=10)) as response:
                if response.status in (401, 403):
                    raise ReaderAuthError("API odrzuciło token dostępu.")
                if response.status != 200:
                    raise ReaderError("Nie udało się pobrać danych z API.")
                return validate_snapshot(await response.json())
        except (ClientError, asyncio.TimeoutError, ValueError, TypeError, KeyError) as error:
            raise ReaderError("Nie można odczytać danych z API dodatku.") from error
