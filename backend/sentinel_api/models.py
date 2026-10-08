from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Action = Literal["snapshot", "network", "logs", "google", "trust", "quality", "patrol", "update_data"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class Login(Input):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(Input):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class Enrollment(Input):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("名称不能为空")
        return value


class Policy(Input):
    google: bool = Field(default=False, strict=True)
    trust: bool = Field(default=False, strict=True)
    interval_minutes: int = Field(default=0, ge=0, le=1440, strict=True)
    scheduled_action: Action = "snapshot"
    region_path: str = "US/CA/Los_Angeles.json"

    @field_validator("interval_minutes")
    @classmethod
    def check_interval(cls, value):
        if 0 < value < 5:
            raise ValueError("周期最少 5 分钟，0 表示关闭")
        return value


class NodeUpdate(Enrollment):
    region: str = Field(default="", max_length=80)
    group_name: str = Field(default="默认分组", min_length=1, max_length=80)
    policy: Policy


class TaskCreate(Input):
    action: Action


class BatchTasks(TaskCreate):
    node_ids: list[str] = Field(min_length=1, max_length=200)


class AgentEnrollment(Input):
    token: str = Field(min_length=16, max_length=256)


class ActiveTask(Input):
    id: str = Field(max_length=64)
    lease: str = Field(max_length=128)
    action: Action | None = None


class Heartbeat(Input):
    metrics: dict[str, Any] = Field(default_factory=dict)
    hostname: str = Field(default="", max_length=120)
    platform: str = Field(default="", max_length=120)
    version: str = Field(default="", max_length=30)
    capabilities: list[Action] = Field(default_factory=list, max_length=20)
    active_job: ActiveTask | None = None


class TaskResult(ActiveTask):
    ok: bool = Field(strict=True)
    cancelled: bool = False
    result: dict[str, Any]


class NotificationSettings(Input):
    telegram_enabled: bool = Field(strict=True)
