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
    plan_id: Optional[int] = None
    plan_no: Optional[str] = None


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
    unplaced_cargos: Optional[List[dict]] = None


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


class ThreeViewsResponse(BaseModel):
    plan_id: int
    plan_no: str
    container_name: str
    container_length: float
    container_width: float
    container_height: float
    top_view: str
    front_view: str
    side_view: str
    cargo_count: int
    cargo_colors: List[dict]


class SequenceStepInfo(BaseModel):
    step: int
    cargo_idx: int
    cargo_id: int
    cargo_name: str
    position: dict
    dimensions: dict
    weight: float
    cog_after: dict
    cog_offset_x_ratio: float
    cog_offset_y_ratio: float
    cog_within_limit: bool


class PackingSequenceResponse(BaseModel):
    plan_id: int
    plan_no: str
    total_steps: int
    cargo_count: int
    all_placed: bool
    all_steps_within_limit: bool
    max_cog_offset_ratio: float
    final_cog: dict
    final_cog_within_limit: bool
    final_cog_offset_x_ratio: float
    final_cog_offset_y_ratio: float
    sequence: List[dict]


class SnapshotCargoInfo(BaseModel):
    cargo_idx: int
    cargo_id: int
    cargo_name: str
    position: dict
    dimensions: dict
    weight: float


class StepSnapshotResponse(BaseModel):
    plan_id: int
    plan_no: str
    step: int
    total_steps: int
    placed_count: int
    placed_cargos: List[dict]
    cog: dict
    cog_within_limit: bool
    cog_offset_x_ratio: float
    cog_offset_y_ratio: float
    last_placed: Optional[dict] = None
    top_view: str
    front_view: str
    side_view: str
