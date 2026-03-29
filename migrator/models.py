from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DataType(str, Enum):
    REVIEWS = "reviews"


class SubmissionStatus(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class ScrapedItem:
    fragrance_name: str
    brand: str
    review_text: str


@dataclass
class SubmissionResult:
    item: ScrapedItem
    status: SubmissionStatus
    reason: Optional[str] = None  # populated on skip/fail


@dataclass
class MigrationReport:
    total_scraped: int
    successful: int
    skipped: int
    failed: int
    results: list[SubmissionResult] = field(default_factory=list)


@dataclass
class MigrationConfig:
    profile_url: str
    parfumo_username: str
    parfumo_password: str  # held in memory only, never logged
    data_type: str = "reviews"
    confidence_threshold: int = 80
    output_path: Optional[str] = None
    headless: bool = False
