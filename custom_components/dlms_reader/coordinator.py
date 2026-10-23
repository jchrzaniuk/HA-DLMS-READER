"""Jeden odczyt API dla wszystkich encji pomiarowych."""

import logging
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ReaderAuthError, ReaderError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ReaderCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN,
                         update_interval=timedelta(seconds=5))
        self.client = client

    async def _async_update_data(self):
        try:
            return await self.client.get_data()
        except ReaderAuthError as error:
            raise ConfigEntryAuthFailed("Dodatek odrzucił token API.") from error
        except ReaderError as error:
            raise UpdateFailed("API dodatku jest niedostępne.") from error
