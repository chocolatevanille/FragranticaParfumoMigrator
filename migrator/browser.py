"""Browser helper: factory for creating a configured Selenium WebDriver."""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


def create_driver(headless: bool = False) -> webdriver.Chrome:
    """Create and return a configured Chrome WebDriver instance.

    Args:
        headless: If True, run Chrome in headless mode (no visible window).

    Returns:
        A configured ``selenium.webdriver.Chrome`` instance.
    """
    options = Options()
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)
