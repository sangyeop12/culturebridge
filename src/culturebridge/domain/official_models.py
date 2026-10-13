from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class OfficialHeritageItem(BaseModel):
    kind_code: str = Field(pattern=r"^\d{2}$")
    asset_number: str = Field(pattern=r"^\d{1,20}$")
    region_code: str = Field(pattern=r"^\d{2}$")
    name: str
    designation: str = ""
    region: str = ""
    city: str = ""

    @property
    def record_id(self) -> str:
        return f"khs:{self.kind_code}:{self.asset_number}:{self.region_code}"


class OfficialSearchResult(BaseModel):
    items: list[OfficialHeritageItem]
    total: int
    page: int
    page_size: int


class OfficialDocument(OfficialHeritageItem):
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    period: str = ""
    address: str = ""
    content: str
    source_url: HttpUrl
    retrieved_at: datetime
    cached: bool = False
    stale: bool = False
    notice: str = "국가유산청 API 원문입니다. 비교·퀴즈용 구조화 항목과는 별도로 제공합니다."


class OfficialLocation(BaseModel):
    name: str
    designation: str
    location: str
    projected_x: float
    projected_y: float
    coordinate_system: str = "UTM-K (공식 응답의 X·Y, 미변환)"
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    source_url: HttpUrl
    geographic_source_url: HttpUrl
    retrieved_at: datetime
    cached: bool = False
    stale: bool = False
