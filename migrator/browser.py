"""Browser helper: factory for creating a configured Selenium WebDriver."""

from selenium import webdriver
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.chrome import ChromeDriverManager


def create_driver(headless: bool = False, browser: str = "firefox"):
    """Create and return a configured WebDriver instance.

    Args:
        headless: If True, run the browser without a visible window.
        browser: Which browser to use — ``"firefox"`` (default) or ``"chrome"``.

    Returns:
        A configured Selenium WebDriver instance.

    Raises:
        ValueError: If an unsupported browser name is given.
    """
    browser = browser.lower()

    if browser == "firefox":
        from selenium.webdriver.firefox.options import Options
        from selenium.webdriver.firefox.service import Service
        options = Options()
        if headless:
            options.add_argument("--headless")
        service = Service(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=options)
        driver.set_window_size(1280, 900)
        return driver

    if browser == "chrome":
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        options = Options()
        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_window_size(1280, 900)
        return driver

    raise ValueError(f"Unsupported browser '{browser}'. Choose 'firefox' or 'chrome'.")
