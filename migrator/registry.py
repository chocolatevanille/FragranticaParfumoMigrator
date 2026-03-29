from __future__ import annotations

from typing import TYPE_CHECKING, Type

from migrator.exceptions import UnknownDataTypeError

if TYPE_CHECKING:
    from migrator.base_scraper import BaseScraper
    from migrator.base_submitter import BaseSubmitter


class PluginRegistry:
    def __init__(self) -> None:
        self._registry: dict[str, tuple[Type[BaseScraper], Type[BaseSubmitter]]] = {}

    def register(
        self,
        data_type: str,
        scraper_cls: Type[BaseScraper],
        submitter_cls: Type[BaseSubmitter],
    ) -> None:
        self._registry[data_type] = (scraper_cls, submitter_cls)

    def get(self, data_type: str) -> tuple[Type[BaseScraper], Type[BaseSubmitter]]:
        if data_type not in self._registry:
            raise UnknownDataTypeError(data_type, self.supported_types())
        return self._registry[data_type]

    def supported_types(self) -> list[str]:
        return list(self._registry.keys())
