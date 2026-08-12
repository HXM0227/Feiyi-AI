from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InputType(str, Enum):
    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    EXHIBIT_ID = "exhibit_id"


class UserInput(ContractModel):
    type: InputType = InputType.TEXT
    text: str | None = Field(default=None, max_length=4000)
    media_url: HttpUrl | None = None
    exhibit_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def require_type_payload(self) -> "UserInput":
        payloads = {
            InputType.TEXT: self.text.strip() if self.text else "",
            InputType.AUDIO: self.media_url,
            InputType.IMAGE: self.media_url,
            InputType.EXHIBIT_ID: self.exhibit_id.strip() if self.exhibit_id else "",
        }
        if not payloads[self.type]:
            raise ValueError(f"input.type={self.type.value} 缺少对应内容")
        return self


class NormalizeRequest(ContractModel):
    input: UserInput
    source_language: str = Field(default="auto", min_length=1, max_length=16)


class NormalizeResponse(ContractModel):
    query: str = Field(min_length=1, max_length=4000)
    detected_language: str
    confidence: float = Field(ge=0, le=1)


class SynthesizeRequest(ContractModel):
    text: str = Field(min_length=1, max_length=12000)
    language: str = Field(default="zh-CN", min_length=1, max_length=16)
    voice: str | None = Field(default=None, max_length=64)


class SynthesizeResponse(ContractModel):
    url: str
    mime_type: str = "audio/mpeg"
    voice: str


class HealthResponse(ContractModel):
    status: str = "ok"
    mode: str
    contract_version: str
