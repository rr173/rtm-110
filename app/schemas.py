from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime
from enum import Enum


class TemperatureClassEnum(str, Enum):
    FROZEN = "FROZEN"
    REFRIGERATED = "REFRIGERATED"
    AMBIENT = "AMBIENT"


class CargoTypeEnum(str, Enum):
    GENERAL = "GENERAL"
    ELECTRONICS = "ELECTRONICS"
    FRAGILE = "FRAGILE"
    LIQUID = "LIQUID"
    HAZARDOUS = "HAZARDOUS"
    FOOD = "FOOD"


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
    hazard_class: Optional[int] = Field(default=None, ge=1, le=6, description="危险品等级 1-6类，None为普通货物")
    declared_name: Optional[str] = Field(default=None, description="海关申报品名")
    declared_weight: Optional[float] = Field(default=None, ge=0, description="海关申报重量 kg")
    declared_value: Optional[float] = Field(default=0.0, ge=0, description="申报价值 CNY")
    temperature_class: Optional[TemperatureClassEnum] = Field(
        default=TemperatureClassEnum.AMBIENT,
        description="温控等级: FROZEN冷冻(-18℃以下)/REFRIGERATED冷藏(0-5℃)/AMBIENT常温"
    )
    cargo_type: Optional[CargoTypeEnum] = Field(
        default=CargoTypeEnum.GENERAL,
        description="货物类型: GENERAL普通货物/ELECTRONICS电子产品/FRAGILE易碎品/LIQUID液体/HAZARDOUS危险品/FOOD食品"
    )


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
    hazard_class: Optional[int] = None
    declared_name: Optional[str] = None
    declared_weight: Optional[float] = None
    declared_value: Optional[float] = None
    temperature_class: Optional[TemperatureClassEnum] = None
    cargo_type: Optional[CargoTypeEnum] = None


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
    temperature_class: Optional[TemperatureClassEnum] = TemperatureClassEnum.AMBIENT


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
    temperature_class: Optional[TemperatureClassEnum] = TemperatureClassEnum.AMBIENT

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


class SplitBoxPlan(BaseModel):
    box_index: int
    container_id: int
    container_name: str
    container_length: float
    container_width: float
    container_height: float
    placed_cargos: List[PlacedCargo]
    placed_count: int
    total_weight: float
    volume_utilization: float
    center_of_gravity: dict
    cog_within_limit: bool
    cog_offset_x_ratio: float
    cog_offset_y_ratio: float


class ContainerUsageSummary(BaseModel):
    container_id: int
    container_name: str
    count: int


class SplitPackingResult(BaseModel):
    total_boxes: int
    total_cargos: int
    placed_cargos_count: int
    unplaced_cargos: List[dict]
    total_weight: float
    average_volume_utilization: float
    container_usage: List[ContainerUsageSummary]
    boxes: List[SplitBoxPlan]
    recommendation: str


class PackingCompareRequest(BaseModel):
    cargo_ids: List[int]
    container_ids: List[int] = []
    enable_split: bool = False


class PackingCompareResult(BaseModel):
    comparison_id: str
    plans: List[PackingPlan]
    ranking: List[dict]
    recommendation: str
    split_result: Optional[SplitPackingResult] = None


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


class TrailerBase(BaseModel):
    name: str
    total_length: float = Field(gt=0, description="拖车总长 mm")
    platform_length: float = Field(gt=0, description="平板长度 mm")
    platform_width: float = Field(gt=0, description="平板宽度 mm")
    front_axle_position: float = Field(description="前轴位置（距前端距离） mm")
    rear_axle_position: float = Field(description="后轴位置（距前端距离） mm")
    front_axle_max_load: float = Field(gt=0, description="前轴最大承重 kg")
    rear_axle_max_load: float = Field(gt=0, description="后轴最大承重 kg")
    total_max_weight: float = Field(gt=0, description="总限重 kg")


class TrailerCreate(TrailerBase):
    pass


class Trailer(TrailerBase):
    id: int
    is_default: bool = False

    class Config:
        from_attributes = True


class TrailerBoxSpec(BaseModel):
    box_id: int
    box_name: str
    length: float = Field(gt=0, description="箱体长度 mm")
    width: float = Field(gt=0, description="箱体宽度 mm")
    weight: float = Field(gt=0, description="箱体重量 kg")
    cog_offset_x: float = Field(default=0.0, description="重心沿长度方向偏移（相对几何中心，正=向前） mm")


class TrailerLoadBox(BaseModel):
    box_id: int
    box_name: str
    x: float
    y: float
    length: float
    width: float
    weight: float
    cog_offset_x: float


class TrailerUnloadStep(BaseModel):
    step_number: int
    box_id: int
    box_name: str
    front_axle_load_before: float
    rear_axle_load_before: float
    front_axle_load_after: float
    rear_axle_load_after: float
    left_weight_before: float
    right_weight_before: float
    left_right_ratio_before: float
    left_right_within_limit_before: bool
    axles_within_limit_before: bool


class TrailerLoadPlanBase(BaseModel):
    trailer_id: int
    trailer_name: str
    total_boxes: int
    total_weight: float
    front_axle_load: float
    rear_axle_load: float
    front_axle_load_ratio: float
    rear_axle_load_ratio: float
    axles_within_limit: bool
    left_right_balance_ratio: float
    left_right_within_limit: bool
    cog_x: float
    cog_y: float
    score: float = 0.0
    recommendation: str = ""


class TrailerLoadPlanCreate(TrailerLoadPlanBase):
    plan_no: str
    loaded_boxes: List[TrailerLoadBox] = []
    unload_sequence: List[TrailerUnloadStep] = []


class TrailerLoadPlan(TrailerLoadPlanBase):
    id: int
    plan_no: str
    created_at: str

    class Config:
        from_attributes = True


class TrailerLoadPlanDetail(TrailerLoadPlan):
    loaded_boxes: List[TrailerLoadBox] = []
    unload_sequence: List[TrailerUnloadStep] = []


class TrailerLoadRequest(BaseModel):
    trailer_id: int
    boxes: List[TrailerBoxSpec]


class TrailerLoadOptimizationResult(BaseModel):
    plan_id: Optional[int] = None
    plan_no: Optional[str] = None
    trailer_id: int
    trailer_name: str
    total_boxes: int
    total_weight: float
    front_axle_load: float
    rear_axle_load: float
    front_axle_load_ratio: float
    rear_axle_load_ratio: float
    axles_within_limit: bool
    left_right_balance_ratio: float
    left_right_within_limit: bool
    cog_x: float
    cog_y: float
    score: float
    recommendation: str
    loaded_boxes: List[TrailerLoadBox]
    unload_sequence: List[TrailerUnloadStep]
    all_steps_valid: bool
    invalid_steps_count: int


class HazardSegregationMatrixBase(BaseModel):
    class_a: int = Field(ge=1, le=6, description="危险品等级A")
    class_b: int = Field(ge=1, le=6, description="危险品等级B")
    min_distance_mm: float = Field(ge=0, description="最小隔离距离 mm")
    segregation_level: str = Field(default="separated", description="隔离等级")
    description: Optional[str] = None


class HazardSegregationMatrixCreate(HazardSegregationMatrixBase):
    pass


class HazardSegregationMatrix(HazardSegregationMatrixBase):
    id: int
    is_active: bool
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class PackingPlanMetaUpdate(BaseModel):
    container_no: Optional[str] = Field(default=None, description="实际集装箱箱号")
    seal_no: Optional[str] = Field(default=None, description="铅封号")
    declared_weight: Optional[float] = Field(default=None, ge=0, description="整箱申报重量 kg")


class HazardViolation(BaseModel):
    cargo_a_id: int
    cargo_a_name: str
    hazard_class_a: int
    cargo_b_id: int
    cargo_b_name: str
    hazard_class_b: int
    actual_distance_mm: float
    required_distance_mm: float
    position_a: dict
    position_b: dict


class WeightViolation(BaseModel):
    cargo_id: Optional[int] = None
    cargo_name: str
    declared_weight_kg: Optional[float] = None
    actual_weight_kg: float
    deviation_ratio: float
    is_total: bool = False


class NameViolation(BaseModel):
    cargo_id: int
    cargo_name: str
    declared_name: Optional[str] = None
    issue: str


class TemperatureViolation(BaseModel):
    violation_type: str
    cargo_a_id: Optional[int] = None
    cargo_a_name: Optional[str] = None
    temperature_class_a: Optional[str] = None
    cargo_b_id: Optional[int] = None
    cargo_b_name: Optional[str] = None
    temperature_class_b: Optional[str] = None
    position_a: Optional[dict] = None
    position_b: Optional[dict] = None
    description: str
    frozen_volume_cbm: Optional[float] = None
    container_volume_cbm: Optional[float] = None
    frozen_volume_ratio: Optional[float] = None
    max_allowed_ratio: Optional[float] = None


class ComplianceAuditRequest(BaseModel):
    plan_identifier: str = Field(description="方案ID或方案编号")


class ComplianceAuditBase(BaseModel):
    plan_id: int
    plan_version: int
    is_passed: bool = False
    hazard_check_passed: bool = True
    weight_check_passed: bool = True
    name_check_passed: bool = True
    temperature_check_passed: bool = True
    hazard_violations: List[Any] = []
    weight_violations: List[Any] = []
    name_violations: List[Any] = []
    temperature_violations: List[Any] = []
    audit_details: Dict[str, Any] = {}
    auditor: Optional[str] = None
    remarks: Optional[str] = None


class ComplianceAuditCreate(ComplianceAuditBase):
    audit_no: str
    plan_content_hash: Optional[str] = None


class ComplianceAudit(ComplianceAuditBase):
    id: int
    audit_no: str
    plan_content_hash: Optional[str] = None
    audited_at: Optional[str] = None

    class Config:
        from_attributes = True


class ComplianceAuditDetail(ComplianceAudit):
    plan_no: Optional[str] = None
    container_name: Optional[str] = None
    temperature_violations_count: Optional[int] = 0


class CustomsDocumentItemBase(BaseModel):
    item_no: int
    cargo_id: Optional[int] = None
    cargo_name: str
    declared_name: Optional[str] = None
    package_count: int = 1
    package_type: str = "CTN"
    weight_kg: float = 0.0
    declared_weight_kg: Optional[float] = None
    length_mm: Optional[float] = None
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    volume_cbm: Optional[float] = None
    x_mm: float
    y_mm: float
    z_mm: float
    stack_layer: int = 1
    hazard_class: Optional[int] = None
    marks_and_numbers: Optional[str] = None
    hs_code: Optional[str] = None


class CustomsDocumentItem(CustomsDocumentItemBase):
    id: int
    document_id: int

    class Config:
        from_attributes = True


class CustomsDocumentBase(BaseModel):
    document_type: str = Field(description="PACKING_LIST 或 CLC")
    container_no: Optional[str] = None
    seal_no: Optional[str] = None
    issued_by: Optional[str] = None
    original_customs_declaration_no: Optional[str] = None


class CustomsDocumentGenerateRequest(BaseModel):
    plan_identifier: str = Field(description="方案ID或方案编号")
    document_type: str = Field(default="BOTH", description="PACKING_LIST / CLC / BOTH")
    issued_by: Optional[str] = None


class CustomsDocumentQueryRequest(BaseModel):
    document_no: Optional[str] = None
    document_type: Optional[str] = None
    plan_identifier: Optional[str] = None
    status: Optional[str] = None


class CustomsDocumentVoidRequest(BaseModel):
    reason: str = Field(description="作废原因")


class CustomsDocumentReissueRequest(BaseModel):
    reason: str = Field(description="重开原因")
    issued_by: Optional[str] = None


class CustomsDocument(CustomsDocumentBase):
    id: int
    document_no: str
    plan_id: int
    plan_version: int
    plan_content_hash: Optional[str] = None
    audit_id: Optional[int] = None
    status: str
    superseded_by: Optional[int] = None
    total_packages: int = 0
    total_weight_kg: float = 0.0
    total_volume_cbm: float = 0.0
    cog_offset_ratio: Optional[float] = None
    volume_utilization: Optional[float] = None
    weight_utilization: Optional[float] = None
    document_content: Dict[str, Any] = {}
    issued_at: Optional[str] = None
    voided_at: Optional[str] = None
    void_reason: Optional[str] = None
    original_hauler_signature: Optional[str] = None

    class Config:
        from_attributes = True


class CustomsDocumentDetail(CustomsDocument):
    plan_no: Optional[str] = None
    container_name: Optional[str] = None
    document_items: List[CustomsDocumentItem] = []


class StowageReportCargoItem(BaseModel):
    packed_cargo_id: int
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
    original_orientation: str
    is_flipped: bool
    max_top_load: float
    top_load_weight: float
    pressure_utilization: float
    pressure_status: str


class StowageReportLayer(BaseModel):
    layer_index: int
    z_start: float
    z_end: float
    cargos: List[StowageReportCargoItem]


class StowageReportBase(BaseModel):
    plan_id: int
    plan_no: str
    plan_version: int
    total_cargos: int
    flipped_count: int
    warning_count: int
    danger_count: int
    health_score: float


class StowageReportCreate(StowageReportBase):
    report_no: str
    report_data: dict
    summary: dict


class StowageReport(StowageReportBase):
    id: int
    report_no: str
    summary: dict
    created_at: str

    class Config:
        from_attributes = True


class StowageReportDetail(StowageReport):
    layers: List[StowageReportLayer]
    overall_health: dict
    statistics: dict


class ReviewTaskBase(BaseModel):
    plan_id: Optional[int] = None
    plan_no: Optional[str] = None
    created_by: Optional[str] = None
    remarks: Optional[str] = None


class ReviewTaskCreate(ReviewTaskBase):
    pass


class ReviewTaskUpdate(BaseModel):
    status: Optional[str] = None
    remarks: Optional[str] = None


class ReviewTask(BaseModel):
    id: int
    task_no: str
    plan_id: int
    plan_no: str
    plan_version: int
    plan_content_hash: Optional[str] = None
    status: str
    is_valid: bool
    invalid_reason: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    remarks: Optional[str] = None
    total_cargos: Optional[int] = 0
    reviewed_count: Optional[int] = 0
    discrepancy_count: Optional[int] = 0
    blocking_count: Optional[int] = 0

    class Config:
        from_attributes = True


class ReviewCargoRecordBase(BaseModel):
    pass


class ReviewCargoRecordCreate(BaseModel):
    plan_cargo_id: Optional[int] = None
    cargo_id: int
    cargo_name: str
    actual_x: Optional[float] = None
    actual_y: Optional[float] = None
    actual_z: Optional[float] = None
    actual_orientation: Optional[str] = None
    actual_load_order: Optional[int] = None
    loaded_at: Optional[str] = None
    review_status: str = "confirmed"
    reviewed_by: Optional[str] = None
    remarks: Optional[str] = None


class ReviewCargoRecordUpdate(BaseModel):
    actual_x: Optional[float] = None
    actual_y: Optional[float] = None
    actual_z: Optional[float] = None
    actual_orientation: Optional[str] = None
    actual_load_order: Optional[int] = None
    loaded_at: Optional[str] = None
    review_status: Optional[str] = None
    reviewed_by: Optional[str] = None
    remarks: Optional[str] = None


class ReviewCargoRecord(BaseModel):
    id: int
    task_id: int
    plan_cargo_id: Optional[int] = None
    cargo_id: int
    cargo_name: str
    review_status: str
    plan_x: Optional[float] = None
    plan_y: Optional[float] = None
    plan_z: Optional[float] = None
    plan_orientation: Optional[str] = None
    plan_load_order: Optional[int] = None
    actual_x: Optional[float] = None
    actual_y: Optional[float] = None
    actual_z: Optional[float] = None
    actual_orientation: Optional[str] = None
    actual_load_order: Optional[int] = None
    loaded_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    remarks: Optional[str] = None
    discrepancies: Optional[List[dict]] = []

    class Config:
        from_attributes = True


class ReviewDiscrepancyBase(BaseModel):
    pass


class ReviewDiscrepancyCreate(BaseModel):
    cargo_record_id: Optional[int] = None
    discrepancy_type: str
    severity: str = "releasable"
    description: str
    details: Optional[dict] = {}


class ReviewDiscrepancyWaive(BaseModel):
    waive_reason: str
    waived_by: Optional[str] = None


class ReviewDiscrepancyResolve(BaseModel):
    resolution_note: str
    resolved_by: Optional[str] = None


class ReviewDiscrepancy(BaseModel):
    id: int
    task_id: int
    cargo_record_id: Optional[int] = None
    discrepancy_type: str
    severity: str
    description: str
    details: Optional[dict] = {}
    is_resolved: bool
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None
    resolution_note: Optional[str] = None
    is_waived: bool
    waived_by: Optional[str] = None
    waived_at: Optional[str] = None
    waive_reason: Optional[str] = None

    class Config:
        from_attributes = True


class LoadingConfirmationBase(BaseModel):
    pass


class LoadingConfirmation(BaseModel):
    id: int
    confirmation_no: str
    task_id: int
    plan_id: int
    plan_no: str
    plan_version: int
    plan_content_hash: Optional[str] = None
    status: str
    is_valid: bool
    total_planned: int
    total_actual: int
    total_discrepancies: int
    blocking_count: int
    releasable_count: int
    is_released: bool
    released_by: Optional[str] = None
    released_at: Optional[str] = None
    release_reason: Optional[str] = None
    summary_data: Optional[dict] = {}
    created_at: Optional[str] = None
    confirmed_at: Optional[str] = None

    class Config:
        from_attributes = True


class LoadingConfirmationDetail(LoadingConfirmation):
    cargo_comparison: Optional[List[dict]] = []
    discrepancies: Optional[List[ReviewDiscrepancy]] = []


class ReviewTaskDetail(ReviewTask):
    cargo_records: Optional[List[ReviewCargoRecord]] = []
    discrepancies: Optional[List[ReviewDiscrepancy]] = []
    confirmations: Optional[List[LoadingConfirmation]] = []


class ReviewTaskQuery(BaseModel):
    plan_no: Optional[str] = None
    status: Optional[str] = None
    only_pending: Optional[bool] = False
    skip: int = 0
    limit: int = 100


class CargoReviewSubmit(BaseModel):
    cargo_records: List[ReviewCargoRecordCreate]
    reviewed_by: Optional[str] = None


class ReleaseConfirmationRequest(BaseModel):
    released_by: str
    release_reason: str


class UnloadingRouteStopBase(BaseModel):
    stop_order: int = Field(ge=1, description="站点顺序，从1开始")
    stop_name: str = Field(description="站点名称")
    stop_code: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None


class UnloadingRouteStopCreate(UnloadingRouteStopBase):
    pass


class UnloadingRouteStop(UnloadingRouteStopBase):
    id: int
    route_id: int

    class Config:
        from_attributes = True


class UnloadingCargoAssignmentBase(BaseModel):
    packed_cargo_id: int = Field(description="关联已装载货物ID")
    cargo_id: int = Field(description="货物ID")
    cargo_name: str = Field(description="货物名称")
    stop_order: int = Field(ge=1, description="所属站点顺序")
    unload_order: int = Field(ge=1, description="在本站点的卸货顺序")


class UnloadingCargoAssignmentCreate(UnloadingCargoAssignmentBase):
    pass


class UnloadingCargoAssignment(UnloadingCargoAssignmentBase):
    id: int
    route_id: int
    stop_id: int

    class Config:
        from_attributes = True


class UnloadingRouteCreate(BaseModel):
    plan_identifier: str = Field(description="配载方案ID或方案编号")
    name: str = Field(description="路线名称")
    description: Optional[str] = None
    created_by: Optional[str] = None
    stops: List[UnloadingRouteStopCreate] = Field(description="站点列表")
    cargo_assignments: List[UnloadingCargoAssignmentCreate] = Field(description="货物站点分配列表")


class UnloadingRouteUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    stops: Optional[List[UnloadingRouteStopCreate]] = None
    cargo_assignments: Optional[List[UnloadingCargoAssignmentCreate]] = None


class UnloadingRouteBase(BaseModel):
    plan_id: int
    plan_no: str
    name: str
    description: Optional[str] = None
    created_by: Optional[str] = None


class UnloadingRoute(UnloadingRouteBase):
    id: int
    route_no: str
    created_at: str
    stops: List[UnloadingRouteStop] = []
    cargo_assignments: List[UnloadingCargoAssignment] = []

    class Config:
        from_attributes = True


class UnloadingRouteSummary(UnloadingRouteBase):
    id: int
    route_no: str
    created_at: str
    total_stops: int
    total_cargos: int
    simulation_count: int

    class Config:
        from_attributes = True


class UnloadingMove(BaseModel):
    move_type: str = Field(description="动作类型: unload卸货 / rehandle_out搬出 / rehandle_in搬回")
    packed_cargo_id: int
    cargo_id: int
    cargo_name: str
    stop_order: int
    move_sequence: int = Field(description="动作序号")
    reason: Optional[str] = None
    cargo_state_snapshot: List[dict] = Field(default_factory=list, description="本次动作完成后所有货物的箱内状态快照，含status字段: in_box在箱内/unloaded已卸/temporary_out临时搬出")


class UnloadingStopResultDetail(BaseModel):
    id: int
    simulation_id: int
    stop_id: int
    stop_order: int
    stop_name: str
    rehandle_count: int
    unload_count: int
    remaining_count: int
    has_deadlock: bool
    deadlock_cargo_ids: List[int]
    moves: List[UnloadingMove]
    remaining_cargos_state: List[dict]


class UnloadingSimulationCreate(BaseModel):
    route_identifier: str = Field(description="路线ID或路线编号")


class UnloadingSimulationBase(BaseModel):
    route_id: int
    route_no: str
    status: str
    total_stops: int
    total_cargos: int
    total_rehandle_count: int
    worst_stop_id: Optional[int] = None
    worst_stop_order: Optional[int] = None
    worst_stop_rehandle_count: int
    has_deadlock: bool
    deadlock_stop_id: Optional[int] = None
    deadlock_stop_order: Optional[int] = None
    deadlock_cargo_ids: List[int]
    poorly_stacked_cargo_ids: List[int]


class UnloadingSimulation(UnloadingSimulationBase):
    id: int
    simulation_no: str
    created_at: str

    class Config:
        from_attributes = True


class UnloadingSimulationDetail(UnloadingSimulation):
    stop_results: List[UnloadingStopResultDetail] = []


class UnloadingSimulationSummary(BaseModel):
    id: int
    simulation_no: str
    route_id: int
    route_no: str
    route_name: str
    status: str
    total_stops: int
    total_cargos: int
    total_rehandle_count: int
    worst_stop_order: Optional[int]
    worst_stop_name: Optional[str]
    worst_stop_rehandle_count: int
    has_deadlock: bool
    deadlock_stop_order: Optional[int]
    deadlock_stop_name: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class RouteComparisonRequest(BaseModel):
    plan_identifier: str = Field(description="配载方案ID或方案编号")
    route_identifiers: List[str] = Field(description="要对比的路线ID或编号列表")


class RouteComparisonItem(BaseModel):
    route_id: int
    route_no: str
    route_name: str
    total_stops: int
    total_cargos: int
    total_rehandle_count: int
    worst_stop_order: Optional[int]
    worst_stop_name: Optional[str]
    worst_stop_rehandle_count: int
    has_deadlock: bool
    latest_simulation_no: Optional[str]


class RouteComparisonResult(BaseModel):
    plan_id: int
    plan_no: str
    plan_name: str
    comparison_id: str
    routes: List[RouteComparisonItem]
    recommendation: str


class ChangeTypeEnum(str, Enum):
    CARGO_INFO = "cargo_info"
    SITE_ASSIGN = "site_assign"
    PLAN_META = "plan_meta"
    MIXED = "mixed"


class ChangeDraftStatusEnum(str, Enum):
    DRAFT = "draft"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    APPLIED = "applied"
    CANCELLED = "cancelled"


class ImpactDecisionEnum(str, Enum):
    KEEP = "keep"
    RERUN = "rerun"
    INVALIDATE = "invalidate"


class ResultTypeEnum(str, Enum):
    STOWAGE_REPORT = "stowage_report"
    COMPLIANCE_AUDIT = "compliance_audit"
    REVIEW_TASK = "review_task"
    UNLOADING_ROUTE = "unloading_route"
    UNLOADING_SIMULATION = "unloading_simulation"
    TRAILER_LOAD = "trailer_load"
    CUSTOMS_DOCUMENT = "customs_document"


class CargoChangeItem(BaseModel):
    cargo_id: int
    field_name: str
    old_value: Any
    new_value: Any


class SiteChangeItem(BaseModel):
    packed_cargo_id: int
    old_stop_order: Optional[int] = None
    new_stop_order: Optional[int] = None
    old_unload_order: Optional[int] = None
    new_unload_order: Optional[int] = None


class PlanMetaChangeItem(BaseModel):
    field_name: str
    old_value: Any
    new_value: Any


class ProposedChanges(BaseModel):
    cargo_changes: List[CargoChangeItem] = []
    site_changes: List[SiteChangeItem] = []
    plan_meta_changes: List[PlanMetaChangeItem] = []


class ChangeDraftCreate(BaseModel):
    plan_identifier: str = Field(description="方案ID或方案编号")
    change_type: ChangeTypeEnum
    change_description: Optional[str] = None
    proposed_changes: ProposedChanges
    created_by: Optional[str] = None
    remarks: Optional[str] = None


class ChangeDraftUpdate(BaseModel):
    change_type: Optional[ChangeTypeEnum] = None
    change_description: Optional[str] = None
    proposed_changes: Optional[ProposedChanges] = None
    remarks: Optional[str] = None


class ChangeImpactItemBase(BaseModel):
    result_type: ResultTypeEnum
    result_id: int
    result_no: str
    result_version: Optional[int] = None
    impact_decision: ImpactDecisionEnum
    impact_reason: str
    affected_fields: List[str] = []


class ChangeImpactItem(ChangeImpactItemBase):
    id: int
    analysis_id: int
    created_at: str

    class Config:
        from_attributes = True


class FieldDiffItem(BaseModel):
    field_name: str
    old_value: Any
    new_value: Any
    change_type: str


class CargoDiffItem(BaseModel):
    cargo_id: int
    cargo_name: str
    field_diffs: List[FieldDiffItem] = []


class ChangeDiffSnapshotBase(BaseModel):
    plan_id: int
    plan_no: str
    base_version: int
    new_version: int
    before_data: Dict[str, Any] = {}
    after_data: Dict[str, Any] = {}
    field_diffs: List[FieldDiffItem] = []
    cargo_diffs: List[CargoDiffItem] = []


class ChangeDiffSnapshot(ChangeDiffSnapshotBase):
    id: int
    snapshot_no: str
    analysis_id: int
    created_at: str

    class Config:
        from_attributes = True


class ChangeImpactAnalysisBase(BaseModel):
    plan_id: int
    plan_no: str
    base_version: int
    new_version: int
    total_affected_count: int = 0
    need_rerun_count: int = 0
    can_keep_count: int = 0
    must_invalidate_count: int = 0
    analysis_summary: Optional[str] = None


class ChangeImpactAnalysis(ChangeImpactAnalysisBase):
    id: int
    analysis_no: str
    draft_id: int
    created_at: str
    impact_items: List[ChangeImpactItem] = []
    diff_snapshot: Optional[ChangeDiffSnapshot] = None

    class Config:
        from_attributes = True


class ChangeImpactAnalysisDetail(ChangeImpactAnalysis):
    impact_items: List[ChangeImpactItem] = []
    diff_snapshot: Optional[ChangeDiffSnapshot] = None


class ChangeDraftBase(BaseModel):
    plan_id: int
    plan_no: str
    base_version: int
    base_content_hash: str
    status: ChangeDraftStatusEnum
    change_type: ChangeTypeEnum
    change_description: Optional[str] = None
    proposed_changes: ProposedChanges
    created_by: Optional[str] = None
    remarks: Optional[str] = None


class ChangeDraft(ChangeDraftBase):
    id: int
    draft_no: str
    created_at: str
    analyzed_at: Optional[str] = None
    applied_at: Optional[str] = None
    applied_by: Optional[str] = None

    class Config:
        from_attributes = True


class ChangeDraftDetail(ChangeDraft):
    impact_analysis: Optional[ChangeImpactAnalysisDetail] = None


class ChangeDraftList(ChangeDraft):
    impact_analysis: Optional[ChangeImpactAnalysisBase] = None


class ChangeApplyRequest(BaseModel):
    applied_by: Optional[str] = None
    remarks: Optional[str] = None


class ChangeImpactAnalysisResult(BaseModel):
    draft_id: int
    draft_no: str
    analysis: ChangeImpactAnalysisDetail


class GateCheckItem(BaseModel):
    check_name: str = Field(description="检查项名称")
    passed: bool = Field(description="是否通过")
    detail: Optional[str] = None


class GateCheckResult(BaseModel):
    can_publish: bool = Field(description="是否可以发布")
    checks: List[GateCheckItem] = []
    summary: Optional[str] = None


class PublicationRequest(BaseModel):
    plan_identifier: str = Field(description="方案ID或方案编号")
    route_identifier: Optional[str] = Field(default=None, description="路线ID或编号,可选指定")
    simulation_identifier: Optional[str] = Field(default=None, description="推演ID或编号,可选指定")
    trailer_plan_identifier: Optional[str] = Field(default=None, description="拖车方案ID或编号,可选指定")
    published_by: Optional[str] = None


class PublicationApproveRequest(BaseModel):
    approved_by: str


class PublicationRejectRequest(BaseModel):
    rejected_reason: str


class PublicationBase(BaseModel):
    plan_id: int
    plan_no: str
    plan_version: int
    plan_content_hash: Optional[str] = None
    container_no: Optional[str] = None
    seal_no: Optional[str] = None
    audit_no: Optional[str] = None
    audit_passed: bool = False
    confirmation_no: Optional[str] = None
    confirmation_released: bool = False
    route_no: Optional[str] = None
    simulation_no: Optional[str] = None
    trailer_plan_no: Optional[str] = None


class Publication(PublicationBase):
    id: int
    publication_no: str
    status: str
    published_by: Optional[str] = None
    published_at: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejected_reason: Optional[str] = None
    gate_check_result: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class PublicationDetail(Publication):
    document_snapshot: List[Dict[str, Any]] = []
    snapshot_data: Optional[Dict[str, Any]] = None
    dispatch_task: Optional[dict] = None


class DispatchTaskUpdateRequest(BaseModel):
    vehicle_no: Optional[str] = None
    driver_name: Optional[str] = None
    planned_departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    terminal_window: Optional[str] = None


class DispatchStatusTransitionRequest(BaseModel):
    target_status: str = Field(description="目标状态: pending_dispatch/loading/dispatched/cancelled")
    reason: Optional[str] = None


class DispatchTaskBase(BaseModel):
    plan_id: int
    plan_no: str
    frozen_version: int
    frozen_content_hash: Optional[str] = None
    status: str


class DispatchTask(DispatchTaskBase):
    id: int
    task_no: str
    publication_id: int
    vehicle_no: Optional[str] = None
    driver_name: Optional[str] = None
    planned_departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    terminal_window: Optional[str] = None
    block_reasons: List[Dict[str, Any]] = []
    last_validated_at: Optional[str] = None
    status_changed_at: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class DispatchTaskDetail(DispatchTask):
    frozen_snapshot: Optional[Dict[str, Any]] = None
    publication_no: Optional[str] = None


class DispatchTaskQuery(BaseModel):
    plan_no: Optional[str] = None
    status: Optional[str] = None
    skip: int = 0
    limit: int = 100


class BlockReasonItem(BaseModel):
    type: str = Field(description="阻断类型: version_change/audit_invalidated/review_not_released/route_outdated/trailer_outdated/document_outdated")
    detail: str = Field(description="阻断详情")


class BatchStatusEnum(str, Enum):
    PENDING_GROUPING = "pending_grouping"
    GROUPING = "grouping"
    PENDING_DEPARTURE = "pending_departure"
    DISPATCHED = "dispatched"
    CANCELLED = "cancelled"


class BatchTaskItemBase(BaseModel):
    dispatch_task_id: int = Field(description="发运任务ID")
    loading_order: int = Field(default=0, ge=0, description="装车顺序")
    vehicle_assignment: Optional[str] = Field(default=None, description="分配的车辆标识")


class BatchShipmentCreate(BaseModel):
    transport_direction: str = Field(description="运输方向")
    fleet_name: Optional[str] = None
    fleet_contact: Optional[str] = None
    fleet_phone: Optional[str] = None
    tractor_no: Optional[str] = None
    trailer_no: Optional[str] = None
    planned_departure_time: Optional[str] = None
    assembly_location: Optional[str] = None
    task_items: List[BatchTaskItemBase] = Field(description="编入批次的发运任务列表")
    created_by: Optional[str] = None


class BatchShipmentUpdate(BaseModel):
    transport_direction: Optional[str] = None
    fleet_name: Optional[str] = None
    fleet_contact: Optional[str] = None
    fleet_phone: Optional[str] = None
    tractor_no: Optional[str] = None
    trailer_no: Optional[str] = None
    planned_departure_time: Optional[str] = None
    assembly_location: Optional[str] = None


class BatchTaskItemSchema(BaseModel):
    id: int
    batch_id: int
    dispatch_task_id: int
    dispatch_task_no: str
    plan_id: int
    plan_no: str
    container_no: Optional[str] = None
    seal_no: Optional[str] = None
    route_no: Optional[str] = None
    frozen_snapshot: Optional[Dict[str, Any]] = None
    loading_order: int = 0
    vehicle_assignment: Optional[str] = None
    is_blocked: bool = False
    block_reason: Optional[str] = None
    removed_at: Optional[str] = None
    remove_reason: Optional[str] = None

    class Config:
        from_attributes = True


class BatchShipmentBase(BaseModel):
    transport_direction: str
    fleet_name: Optional[str] = None
    fleet_contact: Optional[str] = None
    fleet_phone: Optional[str] = None
    tractor_no: Optional[str] = None
    trailer_no: Optional[str] = None
    planned_departure_time: Optional[str] = None
    assembly_location: Optional[str] = None


class BatchShipment(BatchShipmentBase):
    id: int
    batch_no: str
    status: str
    total_containers: int = 0
    total_weight: float = 0.0
    block_reasons: List[Dict[str, Any]] = []
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    cancel_reason: Optional[str] = None

    class Config:
        from_attributes = True


class BatchShipmentDetail(BatchShipment):
    task_items: List[BatchTaskItemSchema] = []


class BatchTaskItemAddRequest(BaseModel):
    dispatch_task_id: int = Field(description="要加入的发运任务ID")
    loading_order: int = Field(default=0, ge=0, description="装车顺序")
    vehicle_assignment: Optional[str] = Field(default=None, description="分配的车辆标识")


class BatchTaskItemsAddRequest(BaseModel):
    task_items: List[BatchTaskItemAddRequest] = Field(description="要加入的发运任务列表")


class BatchTaskItemRemoveRequest(BaseModel):
    remove_reason: str = Field(description="移出原因")


class BatchStatusTransitionRequest(BaseModel):
    target_status: BatchStatusEnum = Field(description="目标状态")
    reason: Optional[str] = None


class BatchShipmentQuery(BaseModel):
    transport_direction: Optional[str] = None
    status: Optional[str] = None
    skip: int = 0
    limit: int = 100


# ==================== 费用核算与分摊 Schemas ====================

class HazardSurchargeConfig(BaseModel):
    hazard_class: int = Field(ge=1, le=6, description="危险品等级 1-6")
    surcharge_amount: float = Field(ge=0, description="该等级的附加费 元/箱")


class ContainerRateConfigBase(BaseModel):
    container_id: int = Field(description="集装箱箱型ID")
    base_freight: float = Field(ge=0, default=0.0, description="单箱基础运费")
    overweight_threshold_kg: float = Field(ge=0, default=0.0, description="超重判定阈值 kg, 0表示按箱型max_weight")
    overweight_surcharge_per_kg: float = Field(ge=0, default=0.0, description="超重附加费 元/kg(超出部分)")
    overweight_surcharge_flat: float = Field(ge=0, default=0.0, description="超重附加费 定额 元/箱")
    reefer_surcharge: float = Field(ge=0, default=0.0, description="冷链(冷藏/冷冻)附加费 元/箱")
    frozen_surcharge: float = Field(ge=0, default=0.0, description="冷冻附加费(在冷藏基础上额外加收) 元/箱")
    hazard_surcharges: List[HazardSurchargeConfig] = Field(default=[], description="按危险品等级的附加费配置列表")
    hazard_surcharge_per_kg: float = Field(ge=0, default=0.0, description="危险品按重量附加费 元/kg")
    is_active: bool = Field(default=True, description="是否启用")


class ContainerRateConfigCreate(ContainerRateConfigBase):
    pass


class ContainerRateConfigUpdate(BaseModel):
    base_freight: Optional[float] = None
    overweight_threshold_kg: Optional[float] = None
    overweight_surcharge_per_kg: Optional[float] = None
    overweight_surcharge_flat: Optional[float] = None
    reefer_surcharge: Optional[float] = None
    frozen_surcharge: Optional[float] = None
    hazard_surcharges: Optional[List[HazardSurchargeConfig]] = None
    hazard_surcharge_per_kg: Optional[float] = None
    is_active: Optional[bool] = None


class ContainerRateConfig(ContainerRateConfigBase):
    id: int
    scheme_id: int
    container_name: str
    hazard_surcharge_by_class: Dict[str, float] = Field(default={}, description="按危险品等级的附加费配置字典 {class: amount}")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class RateSchemeBase(BaseModel):
    scheme_code: str = Field(description="费率方案编码(唯一)")
    scheme_name: str = Field(description="费率方案名称")
    carrier: Optional[str] = Field(default=None, description="承运商/船公司")
    trade_lane: Optional[str] = Field(default=None, description="贸易航线")
    effective_from: Optional[str] = Field(default=None, description="生效起始日期 ISO格式")
    effective_to: Optional[str] = Field(default=None, description="生效截止日期 ISO格式")
    currency: str = Field(default="CNY", description="币种")
    is_default: bool = Field(default=False, description="是否为默认费率方案")
    is_active: bool = Field(default=True, description="是否启用")
    description: Optional[str] = Field(default=None, description="备注说明")
    created_by: Optional[str] = Field(default=None)


class RateSchemeCreate(RateSchemeBase):
    container_rates: List[ContainerRateConfigCreate] = Field(default=[], description="各箱型费率配置列表")


class RateSchemeUpdate(BaseModel):
    scheme_name: Optional[str] = None
    carrier: Optional[str] = None
    trade_lane: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    currency: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


class RateScheme(RateSchemeBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class RateSchemeDetail(RateScheme):
    container_rates: List[ContainerRateConfig] = []


class RateSchemeSummary(BaseModel):
    id: int
    scheme_code: str
    scheme_name: str
    carrier: Optional[str] = None
    trade_lane: Optional[str] = None
    currency: str
    is_default: bool
    is_active: bool
    container_count: int = Field(default=0, description="配置的箱型数量")
    description: Optional[str] = None
    created_at: Optional[str] = None


class CostCalculateRequest(BaseModel):
    plan_identifier: str = Field(description="配载方案ID或方案编号")
    scheme_identifier: Optional[str] = Field(default=None, description="费率方案ID或编码,不传则使用默认费率方案")
    recalculate: bool = Field(default=False, description="是否强制重新计算")
    calculated_by: Optional[str] = Field(default=None)
    remarks: Optional[str] = Field(default=None)


class BoxCostDetailSchema(BaseModel):
    id: int
    calculation_id: int
    box_index: int
    container_id: int
    container_name: str
    actual_weight_kg: float
    total_cargo_volume_cbm: float
    cargo_count: int
    has_hazard: bool
    highest_hazard_class: Optional[int] = None
    temperature_mode: str
    base_freight: float
    overweight_surcharge: float
    overweight_details: Dict[str, Any] = {}
    reefer_surcharge: float
    frozen_surcharge: float
    hazard_surcharge: float
    hazard_details: Dict[str, Any] = {}
    temperature_details: Dict[str, Any] = {}
    subtotal_shared: float
    subtotal_dedicated: float
    subtotal_all: float
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class CargoCostAllocationSchema(BaseModel):
    id: int
    calculation_id: int
    box_detail_id: int
    packed_cargo_id: int
    cargo_id: int
    cargo_name: str
    box_index: int
    volume_cbm: float
    volume_ratio: float
    weight_kg: float
    hazard_class: Optional[int] = None
    temperature_class: Optional[str] = None
    allocated_base_freight: float
    allocated_overweight_surcharge: float
    allocated_reefer_surcharge: float
    allocated_frozen_surcharge: float
    allocated_hazard_surcharge: float
    total_allocated: float
    shared_portion: float
    dedicated_portion: float
    allocation_breakdown: Dict[str, Any] = {}
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class CostCalculationBase(BaseModel):
    scheme_id: int
    plan_id: int
    plan_no: str
    plan_version: int
    currency: str
    total_base_freight: float
    total_overweight_surcharge: float
    total_reefer_surcharge: float
    total_frozen_surcharge: float
    total_hazard_surcharge: float
    total_cost: float
    calculation_status: str = "completed"
    error_message: Optional[str] = None
    remarks: Optional[str] = None
    calculated_by: Optional[str] = None


class CostCalculation(CostCalculationBase):
    id: int
    calculation_no: str
    plan_content_hash: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class CostCalculationDetail(CostCalculation):
    scheme_name: Optional[str] = None
    scheme_code: Optional[str] = None
    carrier: Optional[str] = None
    box_count: int = 0
    total_cargo_count: int = 0
    box_details: List[BoxCostDetailSchema] = []
    cargo_allocations: List[CargoCostAllocationSchema] = []


class CostCalculationSummary(BaseModel):
    id: int
    calculation_no: str
    plan_id: int
    plan_no: str
    plan_version: int
    scheme_id: int
    scheme_code: str
    scheme_name: str
    carrier: Optional[str] = None
    currency: str
    total_base_freight: float
    total_overweight_surcharge: float
    total_reefer_surcharge: float
    total_frozen_surcharge: float
    total_hazard_surcharge: float
    total_cost: float
    box_count: int = 0
    total_cargo_count: int = 0
    calculation_status: str
    created_at: Optional[str] = None


class CostCalculationQuery(BaseModel):
    plan_identifier: Optional[str] = Field(default=None, description="按配载方案ID或编号查询")
    scheme_identifier: Optional[str] = Field(default=None, description="按费率方案ID或编码查询")
    calculation_status: Optional[str] = Field(default=None, description="计算状态筛选")
    skip: int = 0
    limit: int = 100


class RateCompareRequest(BaseModel):
    plan_identifier: str = Field(description="配载方案ID或方案编号")
    scheme_identifiers: List[str] = Field(description="要对比的费率方案ID或编码列表(至少2个)")


class PerCargoCostDiff(BaseModel):
    packed_cargo_id: int
    cargo_id: int
    cargo_name: str
    box_index: int
    base_cost: float
    compare_cost: float
    diff_amount: float
    diff_ratio: float
    breakdown: Dict[str, Any] = {}


class RateCompareResult(BaseModel):
    comparison_id: str
    plan_id: int
    plan_no: str
    plan_version: int
    currency: str
    base_scheme: CostCalculationSummary
    compared_schemes: List[Dict[str, Any]]
    total_cost_diff_summary: List[Dict[str, Any]]
    per_cargo_diffs: List[PerCargoCostDiff]
    recommendation: str


# ==================== 货损理赔与责任判定 Schemas ====================

class DamageStatusEnum(str, Enum):
    INTACT = "intact"
    MINOR_DAMAGE = "minor_damage"
    SEVERE_DAMAGE = "severe_damage"
    LOST = "lost"


class DamageTypeEnum(str, Enum):
    CRUSH = "crush"
    WET = "wet"
    TILT = "tilt"
    TEMPERATURE = "temperature"
    CHEMICAL = "chemical"


class ConfidenceLevelEnum(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResponsibilityEnum(str, Enum):
    CARRIER = "carrier"
    PACKER = "packer"
    SHIPPER = "shipper"
    FORCE_MAJEURE = "force_majeure"


class InspectionCargoItemBase(BaseModel):
    packed_cargo_id: int = Field(description="关联已装货物ID")
    damage_status: DamageStatusEnum = Field(description="损坏状态")
    damage_type: Optional[DamageTypeEnum] = Field(default=None, description="损坏类型")
    declared_value: float = Field(default=0.0, ge=0, description="申报价值")
    damage_description: Optional[str] = Field(default=None, description="损坏描述")


class InspectionCargoItemCreate(InspectionCargoItemBase):
    pass


class InspectionCargoItemUpdate(BaseModel):
    damage_status: Optional[DamageStatusEnum] = None
    damage_type: Optional[DamageTypeEnum] = None
    declared_value: Optional[float] = None
    damage_description: Optional[str] = None


class InspectionCargoItem(InspectionCargoItemBase):
    id: int
    inspection_id: int
    cargo_id: int
    cargo_name: str
    item_no: int
    position_x: float = 0.0
    position_y: float = 0.0
    position_z: float = 0.0
    length: float = 0.0
    width: float = 0.0
    height: float = 0.0
    weight: float = 0.0
    max_top_load: float = 0.0
    temperature_class: Optional[str] = None
    hazard_class: Optional[int] = None
    stack_layer: int = 1
    is_door_side: bool = False
    is_bottom_layer: bool = False
    top_pressure_weight: float = 0.0

    class Config:
        from_attributes = True


class CargoDamageInspectionBase(BaseModel):
    plan_identifier: str = Field(description="配载方案ID或方案编号")
    inspector: Optional[str] = Field(default=None, description="检验员")
    inspection_date: Optional[str] = Field(default=None, description="检验日期 ISO格式")
    remarks: Optional[str] = Field(default=None, description="检验备注")


class CargoDamageInspectionCreate(CargoDamageInspectionBase):
    inspection_items: List[InspectionCargoItemCreate] = Field(description="检验货物明细列表")


class CargoDamageInspectionSubmit(BaseModel):
    pass


class DamageInferenceBase(BaseModel):
    inferred_cause: str
    confidence_level: str
    responsibility: str
    explanation: Optional[str] = None
    evidence_list: List[str] = []
    inference_detail: Dict[str, Any] = {}


class DamageInference(DamageInferenceBase):
    id: int
    inspection_id: int
    inspection_item_id: int
    cargo_id: int
    cargo_name: str
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class ClaimItemBase(BaseModel):
    damage_status: str
    damage_type: Optional[str] = None
    declared_value: float
    claim_ratio: float
    claim_amount: float
    primary_responsibility: str


class ClaimItem(ClaimItemBase):
    id: int
    claim_id: int
    inspection_item_id: int
    cargo_id: int
    cargo_name: str
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class ClaimRecordBase(BaseModel):
    total_declared_value: float = 0.0
    total_claim_amount: float = 0.0
    minor_damage_amount: float = 0.0
    severe_damage_amount: float = 0.0
    lost_amount: float = 0.0
    carrier_responsibility_amount: float = 0.0
    packer_responsibility_amount: float = 0.0
    shipper_responsibility_amount: float = 0.0
    force_majeure_amount: float = 0.0


class ClaimRecord(ClaimRecordBase):
    id: int
    claim_no: str
    inspection_id: int
    plan_id: int
    plan_no: str
    container_no: Optional[str] = None
    shipment_no: Optional[str] = None
    status: str
    handler: Optional[str] = None
    remarks: Optional[str] = None
    claim_date: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class ClaimRecordDetail(ClaimRecord):
    claim_items: List[ClaimItem] = []


class CargoDamageInspection(CargoDamageInspectionBase):
    id: int
    inspection_no: str
    plan_id: int
    plan_no: str
    plan_version: int
    container_no: Optional[str] = None
    shipment_no: Optional[str] = None
    total_cargos: int = 0
    intact_count: int = 0
    minor_damage_count: int = 0
    severe_damage_count: int = 0
    lost_count: int = 0
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class CargoDamageInspectionDetail(CargoDamageInspection):
    inspection_items: List[InspectionCargoItem] = []
    damage_inferences: List[DamageInference] = []
    claim_record: Optional[ClaimRecordDetail] = None


class DamageAnalysisResult(BaseModel):
    inspection_id: int
    inspection_no: str
    inferences: List[DamageInferenceBase]
    claim_summary: Dict[str, Any]


class ClaimStatisticsByResponsibility(BaseModel):
    carrier_amount: float = 0.0
    packer_amount: float = 0.0
    shipper_amount: float = 0.0
    force_majeure_amount: float = 0.0
    total_amount: float = 0.0
    claim_count: int = 0


class DamageInspectionQuery(BaseModel):
    plan_identifier: Optional[str] = Field(default=None, description="按配载方案ID或编号查询")
    status: Optional[str] = Field(default=None, description="状态筛选")
    skip: int = 0
    limit: int = 100


class ClaimQuery(BaseModel):
    plan_identifier: Optional[str] = Field(default=None, description="按配载方案ID或编号查询")
    status: Optional[str] = Field(default=None, description="状态筛选")
    skip: int = 0
    limit: int = 100


# ==================== 理赔趋势分析 Schemas ====================

class TrendAnalysisRequest(BaseModel):
    time_granularity: str = Field(default="month", description="时间粒度: month月/quarter季度")
    carrier: Optional[str] = Field(default=None, description="按承运商筛选")
    container_type: Optional[str] = Field(default=None, description="按箱型筛选(container_name)")
    damage_type: Optional[str] = Field(default=None, description="按损坏类型筛选")
    start_date: Optional[str] = Field(default=None, description="开始日期 ISO格式")
    end_date: Optional[str] = Field(default=None, description="结束日期 ISO格式")


class DamageTypeRatio(BaseModel):
    damage_type: str
    count: int
    amount: float
    ratio: float


class ResponsibilityRatio(BaseModel):
    responsibility: str
    amount: float
    ratio: float


class TrendPeriodData(BaseModel):
    period: str
    claim_count: int
    total_amount: float
    damage_type_distribution: List[DamageTypeRatio] = []
    responsibility_distribution: List[ResponsibilityRatio] = []


class TrendAnalysisResult(BaseModel):
    time_granularity: str
    total_claim_count: int
    total_claim_amount: float
    periods: List[TrendPeriodData] = []
    applied_filters: Dict[str, Any] = {}


# ==================== 预警规则 Schemas ====================

class AlertRuleTypeEnum(str, Enum):
    AMOUNT_THRESHOLD = "amount_threshold"
    RATIO_THRESHOLD = "ratio_threshold"
    CONSECUTIVE_AMOUNT = "consecutive_amount"


class AlertRuleScopeEnum(str, Enum):
    CARRIER = "carrier"
    DAMAGE_TYPE = "damage_type"
    CONTAINER_TYPE = "container_type"
    ALL = "all"


class AlertRuleBase(BaseModel):
    rule_name: str = Field(description="规则名称")
    rule_type: AlertRuleTypeEnum = Field(description="规则类型")
    description: Optional[str] = Field(default=None, description="规则描述")
    is_active: bool = Field(default=True, description="是否启用")
    scope: Optional[AlertRuleScopeEnum] = Field(default=AlertRuleScopeEnum.ALL, description="适用范围")
    scope_value: Optional[str] = Field(default=None, description="适用范围具体值")
    threshold_value: float = Field(gt=0, description="阈值")
    consecutive_months: int = Field(default=1, ge=1, description="连续月份数")
    time_granularity: str = Field(default="month", description="时间粒度: month/quarter")
    suggested_action: Optional[str] = Field(default=None, description="建议措施")
    created_by: Optional[str] = Field(default=None, description="创建人")


class AlertRuleCreate(AlertRuleBase):
    pass


class AlertRuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    rule_type: Optional[AlertRuleTypeEnum] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    scope: Optional[AlertRuleScopeEnum] = None
    scope_value: Optional[str] = None
    threshold_value: Optional[float] = None
    consecutive_months: Optional[int] = None
    time_granularity: Optional[str] = None
    suggested_action: Optional[str] = None


class AlertRule(AlertRuleBase):
    id: int
    rule_no: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


# ==================== 预警事件 Schemas ====================

class AlertEventStatusEnum(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    CLOSED = "closed"
    HANDLED = "handled"


class AlertEventCloseRequest(BaseModel):
    handling_notes: str = Field(description="处理说明(必填)")
    handler: Optional[str] = Field(default=None, description="处理人")


class AlertEventHandleRequest(BaseModel):
    handler: Optional[str] = Field(default=None, description="处理人")
    handling_notes: Optional[str] = Field(default=None, description="处理说明")


class AlertEventBase(BaseModel):
    pass


class AlertEvent(AlertEventBase):
    id: int
    event_no: str
    rule_id: int
    rule_no: str
    rule_name: str
    trigger_time: Optional[str] = None
    trigger_condition: str
    trigger_period: str
    scope: Optional[str] = None
    scope_value: Optional[str] = None
    actual_value: float
    threshold_value: float
    related_claim_ids: List[int] = []
    suggested_action: Optional[str] = None
    status: str
    handler: Optional[str] = None
    handled_at: Optional[str] = None
    handling_notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class AlertEventDetail(AlertEvent):
    related_claims: List[Dict[str, Any]] = []


class AlertEventQuery(BaseModel):
    status: Optional[str] = Field(default=None, description="按状态筛选")
    only_pending: Optional[bool] = Field(default=False, description="仅查询未处理")
    rule_id: Optional[int] = Field(default=None, description="按规则ID筛选")
    skip: int = 0
    limit: int = 100


class AlertEngineRunResult(BaseModel):
    triggered_count: int
    triggered_events: List[AlertEvent] = []


# ==================== 保险模块 Schemas ====================

class InsurancePolicyStatusEnum(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    SURRENDERED = "surrendered"


class InsuranceProductBase(BaseModel):
    product_code: str = Field(description="保险产品编码(唯一)")
    product_name: str = Field(description="保险产品名称")
    description: Optional[str] = Field(default=None, description="产品描述")
    is_active: bool = Field(default=True, description="是否启用")

    applicable_cargo_types: List[CargoTypeEnum] = Field(default_factory=list, description="适用的货物类型列表")
    min_temperature_class: Optional[TemperatureClassEnum] = Field(default=None, description="最低温控等级")
    max_temperature_class: Optional[TemperatureClassEnum] = Field(default=None, description="最高温控等级")
    min_hazard_class: Optional[int] = Field(default=None, ge=1, le=6, description="最低危险品等级 1-6")
    max_hazard_class: Optional[int] = Field(default=None, ge=1, le=6, description="最高危险品等级 1-6")
    max_unit_value: Optional[float] = Field(default=None, ge=0, description="单件最大价值上限, None表示无限制")

    base_rate_pct: float = Field(default=0.0, ge=0, description="基础费率百分比, 如0.15表示0.15%")
    hazard_surcharge_coeff: float = Field(default=1.0, ge=1.0, description="危险品加费系数, 如1.5表示加收50%")
    cold_chain_surcharge_coeff: float = Field(default=1.0, ge=1.0, description="冷链加费系数")
    high_value_threshold: Optional[float] = Field(default=None, ge=0, description="高价值加费阈值")
    high_value_surcharge_coeff: float = Field(default=1.0, ge=1.0, description="高价值加费系数")

    deductible_amount: float = Field(default=0.0, ge=0, description="免赔额 CNY")
    deductible_rate_pct: float = Field(default=0.0, ge=0, description="免赔率百分比, 如5表示损失金额的5%免赔")
    excluded_items: List[str] = Field(default_factory=list, description="不保事项列表")


class InsuranceProductCreate(InsuranceProductBase):
    pass


class InsuranceProductUpdate(BaseModel):
    product_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    applicable_cargo_types: Optional[List[CargoTypeEnum]] = None
    min_temperature_class: Optional[TemperatureClassEnum] = None
    max_temperature_class: Optional[TemperatureClassEnum] = None
    min_hazard_class: Optional[int] = None
    max_hazard_class: Optional[int] = None
    max_unit_value: Optional[float] = None
    base_rate_pct: Optional[float] = None
    hazard_surcharge_coeff: Optional[float] = None
    cold_chain_surcharge_coeff: Optional[float] = None
    high_value_threshold: Optional[float] = None
    high_value_surcharge_coeff: Optional[float] = None
    deductible_amount: Optional[float] = None
    deductible_rate_pct: Optional[float] = None
    excluded_items: Optional[List[str]] = None


class InsuranceProduct(InsuranceProductBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class MatchedInsuranceProduct(BaseModel):
    product_id: int
    product_code: str
    product_name: str
    estimated_premium: float = Field(description="预估保费")
    base_rate_pct: float
    final_rate_pct: float
    breakdown: Dict[str, Any] = Field(description="保费计算明细")
    deductible_summary: Dict[str, Any] = Field(description="免赔条款摘要")


class InsuranceProductMatch(BaseModel):
    product_id: int
    product_code: str
    product_name: str
    estimated_premium: float = Field(description="预估保费")
    base_rate_pct: float
    final_rate_pct: float
    breakdown: Dict[str, Any] = Field(description="保费计算明细")
    deductible_summary: Dict[str, Any] = Field(description="免赔条款摘要")


class InsuranceMatchRequest(BaseModel):
    plan_identifier: str = Field(description="配载方案ID或方案编号")


class InsuranceSingleCargoMatchRequest(BaseModel):
    cargo_type: CargoTypeEnum = Field(description="货物类型")
    declared_value: float = Field(gt=0, description="申报价值 CNY")
    hazard_class: Optional[int] = Field(default=None, ge=1, le=6, description="危险品等级 1-6")
    temperature_class: Optional[TemperatureClassEnum] = Field(default=TemperatureClassEnum.AMBIENT, description="温控等级")


class InsurancePremiumCalculateRequest(BaseModel):
    product_id: int = Field(description="保险产品ID")
    declared_value: float = Field(gt=0, description="申报价值 CNY")
    hazard_class: Optional[int] = Field(default=None, ge=1, le=6, description="危险品等级 1-6")
    temperature_class: Optional[TemperatureClassEnum] = Field(default=TemperatureClassEnum.AMBIENT, description="温控等级")


class InsurancePremiumCalculation(BaseModel):
    base_rate_pct: float
    hazard_coeff: float
    cold_chain_coeff: float
    high_value_coeff: float
    final_rate_pct: float
    premium: float
    breakdown: Dict[str, Any]
    deductible_summary: Dict[str, Any]


class InsurancePolicyGenerateRequest(BaseModel):
    policyholder_name: str = Field(description="投保人名称")
    policyholder_contact: Optional[str] = Field(default=None, description="投保人联系方式")
    voyage_no: Optional[str] = Field(default=None, description="承运航次")
    insurance_period_days: int = Field(default=30, ge=1, description="保险期限 天数")
    created_by: Optional[str] = Field(default=None, description="创建人")
    remarks: Optional[str] = Field(default=None, description="备注")
    auto_select_cheapest: bool = Field(default=True, description="是否自动选择最便宜的保险产品")


class InsurancePolicyStatusTransition(BaseModel):
    new_status: InsurancePolicyStatusEnum = Field(description="目标状态")
    remark: Optional[str] = Field(default=None, description="状态变更备注")


class InsuranceSurrenderResponse(BaseModel):
    policy_id: int
    policy_no: str
    surrender_no: str
    surrender_reason: str
    total_premium: float
    used_days: int
    total_days: int
    refund_ratio: float
    refund_amount: float
    new_status: str
    surrendered_at: str


class InsuranceProductStatistic(BaseModel):
    product_id: int
    product_code: str
    product_name: str
    total_policies: int = Field(description="出单量")
    total_premium: float = Field(description="总保费 CNY")
    total_insured_amount: float = Field(description="总保额 CNY")


class InsuranceMatchResultItem(BaseModel):
    packed_cargo_id: int
    cargo_id: int
    cargo_name: str
    cargo_type: str
    hazard_class: Optional[int]
    temperature_class: Optional[str]
    declared_value: float
    matched_products: List[MatchedInsuranceProduct] = Field(description="按保费从低到高排序的匹配产品(最多3个)")


class InsuranceMatchResponse(BaseModel):
    plan_id: int
    plan_no: str
    match_id: str
    total_cargos: int
    match_results: List[InsuranceMatchResultItem]


class InsurancePolicyItemBase(BaseModel):
    packed_cargo_id: int
    product_id: int = Field(description="选中的保险产品ID")


class InsurancePolicyItemCreate(InsurancePolicyItemBase):
    pass


class InsurancePolicyItem(InsurancePolicyItemBase):
    id: int
    policy_id: int
    cargo_id: int
    cargo_name: str
    cargo_type: str
    hazard_class: Optional[int]
    temperature_class: Optional[str]
    declared_value: float
    base_rate_pct: float
    hazard_coeff: float
    cold_chain_coeff: float
    high_value_coeff: float
    final_rate_pct: float
    premium: float
    deductible_summary: Dict[str, Any] = {}
    alternative_products: List[Dict[str, Any]] = []
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class InsurancePolicyBase(BaseModel):
    plan_identifier: str = Field(description="配载方案ID或方案编号")
    policyholder_name: str = Field(description="投保人名称")
    policyholder_contact: Optional[str] = Field(default=None, description="投保人联系方式")
    voyage_no: Optional[str] = Field(default=None, description="承运航次")
    insurance_period_days: int = Field(default=30, ge=1, description="保险期限 天数")
    created_by: Optional[str] = Field(default=None, description="创建人")
    remarks: Optional[str] = Field(default=None, description="备注")


class InsurancePolicyCreate(InsurancePolicyBase):
    policy_items: List[InsurancePolicyItemCreate] = Field(description="逐件货物的保险产品选择")


class InsurancePolicyUpdate(BaseModel):
    policyholder_name: Optional[str] = None
    policyholder_contact: Optional[str] = None
    voyage_no: Optional[str] = None
    insurance_period_days: Optional[int] = None
    remarks: Optional[str] = None
    policy_items: Optional[List[InsurancePolicyItemCreate]] = None


class InsurancePolicy(InsurancePolicyBase):
    id: int
    policy_no: str
    plan_id: int
    plan_no: str
    plan_version: int
    container_no: Optional[str] = None
    shipment_no: Optional[str] = None
    total_insured_amount: float
    total_premium: float
    currency: str
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    status: str
    status_changed_at: Optional[str] = None
    submitted_at: Optional[str] = None
    accepted_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class InsurancePolicyDetail(InsurancePolicy):
    policy_items: List[InsurancePolicyItem] = []
    surrender_record: Optional[Dict[str, Any]] = None


class InsurancePolicyStatusTransitionRequest(BaseModel):
    target_status: InsurancePolicyStatusEnum = Field(description="目标状态")
    handled_by: Optional[str] = Field(default=None, description="处理人")
    remarks: Optional[str] = Field(default=None, description="备注")


class InsuranceSurrenderRequest(BaseModel):
    surrender_reason: str = Field(description="退保原因")
    handled_by: Optional[str] = Field(default=None, description="处理人")
    remarks: Optional[str] = Field(default=None, description="备注")


class InsuranceSurrenderRecord(BaseModel):
    id: int
    policy_id: int
    surrender_no: str
    surrender_reason: str
    total_premium: float
    used_days: int
    total_days: int
    refund_ratio: float
    refund_amount: float
    surrendered_at: Optional[str] = None
    handled_by: Optional[str] = None
    remarks: Optional[str] = None

    class Config:
        from_attributes = True


class InsuranceProductStats(BaseModel):
    product_id: int
    product_code: str
    product_name: str
    total_policies: int = Field(description="出单量")
    total_premium: float = Field(description="总保费 CNY")
    total_insured_amount: float = Field(description="总保额 CNY")


class InsurancePolicyQuery(BaseModel):
    plan_identifier: Optional[str] = Field(default=None, description="按配载方案ID或编号查询")
    status: Optional[InsurancePolicyStatusEnum] = Field(default=None, description="状态筛选")
    product_id: Optional[int] = Field(default=None, description="按保险产品ID筛选")
    skip: int = 0
    limit: int = 100


class InsuranceGenerateRequest(BaseModel):
    match_id: str = Field(description="匹配结果ID, 用于关联匹配结果")
    policyholder_name: str = Field(description="投保人名称")
    policyholder_contact: Optional[str] = Field(default=None, description="投保人联系方式")
    voyage_no: Optional[str] = Field(default=None, description="承运航次")
    insurance_period_days: int = Field(default=30, ge=1, description="保险期限 天数")
    created_by: Optional[str] = Field(default=None, description="创建人")
    remarks: Optional[str] = Field(default=None, description="备注")
    use_top_match: bool = Field(default=True, description="是否使用每个货物的第一个(最便宜)匹配产品")
    custom_selections: Optional[Dict[int, int]] = Field(default=None, description="自定义选择 {packed_cargo_id: product_id}, 如指定则覆盖use_top_match")

