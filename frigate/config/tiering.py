from typing import Self

from pydantic import Field, model_validator

from .base import FrigateBaseModel
from .env import EnvString

__all__ = ["TieringConfig"]


class TieringConfig(FrigateBaseModel):
    enabled: bool = Field(
        default=False,
        title="Enable S3 tiering",
        description="Mirror finished recording segments to S3 compatible storage.",
    )
    endpoint: str | None = Field(
        default=None,
        title="S3 endpoint",
        description="URL of the S3 compatible endpoint, for example http://weed-s3.seaweedfs:8333.",
    )
    region: str = Field(
        default="us-east-1",
        title="S3 region",
        description="Region name sent to the S3 endpoint; most self hosted servers ignore it.",
    )
    access_key: EnvString | None = Field(
        default=None,
        title="S3 access key",
        description="S3 access key; can be provided via environment variables or secrets.",
    )
    secret_key: EnvString | None = Field(
        default=None,
        title="S3 secret key",
        description="S3 secret key; can be provided via environment variables or secrets.",
    )
    recordings_bucket: str = Field(
        default="frigate-recordings",
        title="Recordings bucket",
        description="Bucket that receives recording segments; it must already exist.",
    )

    exports_bucket: str = Field(
        default="frigate-exports",
        title="Exports bucket",
        description="Bucket that receives exported videos; it must already exist.",
    )
    read_url: str | None = Field(
        default=None,
        title="Read URL",
        description="Base URL used to read uploaded files back over HTTP with range requests, for example http://weed-filer.seaweedfs:8888/buckets for a SeaweedFS filer. Required for local_max_gb.",
    )
    local_max_gb: float | None = Field(
        default=None,
        gt=0,
        title="Local recordings limit",
        description="When local recordings exceed this size, the oldest segments that are already in S3 are removed from local disk and played from S3. Exports are removed locally once uploaded. Leave unset to keep everything local.",
    )
    backfill_hours: float | None = Field(
        default=None,
        gt=0,
        title="Backfill window",
        description="Only upload segments that ended within this many hours; older recordings stay local only. Leave unset to upload everything.",
    )

    @model_validator(mode="after")
    def validate_settings(self) -> Self:
        if self.enabled and not (self.endpoint and self.access_key and self.secret_key):
            raise ValueError(
                "tiering requires endpoint, access_key and secret_key when enabled"
            )

        if self.local_max_gb and not (self.enabled and self.read_url):
            raise ValueError("tiering local_max_gb requires enabled and read_url")

        return self
