from abc import ABC, abstractmethod

from selenium.webdriver.remote.webdriver import WebDriver

from migrator.models import ScrapedItem


class BaseScraper(ABC):
    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver

    @abstractmethod
    def scrape(self, profile_url: str) -> list[ScrapedItem]: ...
