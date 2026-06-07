from pydantic import BaseModel, Field
from typing import Optional, List


class ContainerBase(BaseModel):
    name: str
    length: float = Field(gt=0, description="内部长度 mm")
    width: float = Field(gt=0, description="内部宽度 mm")
    height: float = Field(gt=0, description="内部高度 mm")
    max_weight: float = Field(gt=0, description="最大载重 kg")


class ContainerCreate(ContainerBase):
    pass


class Container(ContainerBase):
    id: int
    is_default: bool = False

    class Config:
        from_attributes = True


class CargoBase(BaseModel):
    name: str
    length: float = Field(gt=0, description="长度 mm")
    width: float = Field(gt=0, description="宽度 mm")
    height: float = Field(gt=0, description="高度 mm")
    weight: float = Field(gt=0, description="重量 kg")
    can_rotate_horizontal: bool = Field(default=True, description="是否允许水平旋转（90度）")
    can_flip: bool = Field(default=True, description="是否允许翻转（立着放/倒着放）")
    max_top_load: float = Field(default=0.0, ge=0, description="顶面最大承压 kg")
    quantity: int = Field(default=1, ge=1, description="数量")


class CargoCreate(CargoBase):
    pass


class CargoUpdate(BaseModel):
    name: Optional[str] = None
    length: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    can_rotate_horizontal: Optional[bool] = None
    can_flip: Optional[bool] = None
    max_top_load: Optional[float] = None
    quantity: Optional[int] = None


class Cargo(CargoBase):
    id: int

    class Config:
        from_attributes = True


class PlacedCargo(BaseModel):
    cargo_id: int
    cargo_name: str
    x: float
    y: float
    z: float
    length: float
    width: float
    height: float
    weight: float
    orientation: str


class PackingResult(BaseModel):
    container_id: int
    container_name: str
    placed_cargos: List[PlacedCargo]
    unplaced_cargos: List[dict]
    total_weight: float
    volume_utilization: float
    center_of_gravity: dict
    cog_within_limit: bool


class PackedCargoSchema(BaseModel):
    id: int
    plan_id: int
    cargo_id: int
    cargo_name: str
    x: float
    y: float
    z: float
    length: float
    width: float
    height: float
    weight: float
    orientation: str

    class Config:
        from_attributes = True


class PackingPlanBase(BaseModel):
    container_id: int
    container_name: str
    total_cargos: int
    placed_count: int
    unplaced_count: int
    total_weight: float
    volume_utilization: float
    cog_x: float
    cog_y: float
    cog_z: float
    cog_within_limit: bool
    cog_offset_x_ratio: float
    cog_offset_y_ratio: float
    score: float = 0.0
    rank: int = 0
    recommendation: str = ""


class PackingPlanCreate(PackingPlanBase):
    plan_no: str
    placed_cargos: List[PlacedCargo] = []


class PackingPlan(PackingPlanBase):
    id: int
    plan_no: str
    created_at: str

    class Config:
        from_attributes = True


class PackingPlanDetail(PackingPlan):
    placed_cargos: List[PackedCargoSchema] = []
    unplaced_cargos: List[dict] = []


class PackingCompareRequest(BaseModel):
    cargo_ids: List[int]
    container_ids: List[int] = []


class PackingCompareResult(BaseModel):
    comparison_id: str
    plans: List[PackingPlan]
    ranking: List[dict]
    recommendation: str
