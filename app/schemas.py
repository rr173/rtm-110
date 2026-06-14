from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime
from enum import Enum


class TemperatureClassEnum(str, Enum):
    FROZEN = "FROZEN"
    REFRIGERATED = "REFRIGERATED"
    AMBIENT = "AMBIENT"


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
    temperature_class: Optional[TemperatureClassEnum] = Field(
        default=TemperatureClassEnum.AMBIENT,
        description="温控等级: FROZEN冷冻(-18℃以下)/REFRIGERATED冷藏(0-5℃)/AMBIENT常温"
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
    temperature_class: Optional[TemperatureClassEnum] = None


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

