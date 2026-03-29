from abc import ABC, abstractmethod

from selenium.webdriver.remote.webdriver import WebDriver

from migrator.models import ScrapedItem, SubmissionResult


class BaseSubmitter(ABC):
    def __init__(self, driver: WebDriver, confidence_threshold: int) -> None:
        self.driver = driver
        self.confidence_threshold = confidence_threshold

    @abstractmethod
    def submit(self, item: ScrapedItem) -> SubmissionResult: ...
