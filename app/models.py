from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Container(Base):
    __tablename__ = "containers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    length = Column(Float)
    width = Column(Float)
    height = Column(Float)
    max_weight = Column(Float)
    is_default = Column(Boolean, default=False)


class Cargo(Base):
    __tablename__ = "cargos"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    length = Column(Float)
    width = Column(Float)
    height = Column(Float)
    weight = Column(Float)
    can_rotate_horizontal = Column(Boolean, default=True)
    can_flip = Column(Boolean, default=True)
    max_top_load = Column(Float, default=0.0)
    quantity = Column(Integer, default=1)
    hazard_class = Column(Integer, nullable=True, comment="危险品等级 1-6类，None为普通货物")
    declared_name = Column(String, nullable=True, comment="海关申报品名")
    declared_weight = Column(Float, nullable=True, comment="海关申报重量 kg")
    temperature_class = Column(String, nullable=True, default="AMBIENT", comment="温控等级: FROZEN冷冻(-18℃以下)/REFRIGERATED冷藏(0-5℃)/AMBIENT常温")


class PackingPlan(Base):
    __tablename__ = "packing_plans"

    id = Column(Integer, primary_key=True, index=True)
    plan_no = Column(String, unique=True, index=True)
    container_id = Column(Integer, ForeignKey("containers.id"))
    container_name = Column(String)
    total_cargos = Column(Integer)
    placed_count = Column(Integer)
    unplaced_count = Column(Integer)
    total_weight = Column(Float)
    volume_utilization = Column(Float)
    cog_x = Column(Float)
    cog_y = Column(Float)
    cog_z = Column(Float)
    cog_within_limit = Column(Boolean)
    cog_offset_x_ratio = Column(Float)
    cog_offset_y_ratio = Column(Float)
    score = Column(Float, default=0.0)
    rank = Column(Integer, default=0)
    recommendation = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now())
    version = Column(Integer, default=1, comment="方案版本号，每次修改递增")
    content_hash = Column(String, nullable=True, comment="方案内容哈希，用于检测变更")
    container_no = Column(String, nullable=True, comment="实际集装箱箱号")
    seal_no = Column(String, nullable=True, comment="铅封号")
    declared_weight = Column(Float, nullable=True, comment="整箱申报重量 kg")

    placed_cargos = relationship("PackedCargo", back_populates="plan", cascade="all, delete-orphan")
    unplaced_cargos = relationship("UnplacedCargo", back_populates="plan", cascade="all, delete-orphan")
    compliance_audits = relationship("ComplianceAudit", back_populates="plan", cascade="all, delete-orphan")
    customs_documents = relationship("CustomsDocument", back_populates="plan", cascade="all, delete-orphan")


class PackedCargo(Base):
    __tablename__ = "packed_cargos"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("packing_plans.id"))
    cargo_id = Column(Integer)
    cargo_name = Column(String)
    x = Column(Float)
    y = Column(Float)
    z = Column(Float)
    length = Column(Float)
    width = Column(Float)
    height = Column(Float)
    weight = Column(Float)
    orientation = Column(String)
    max_top_load = Column(Float, default=0.0, comment="顶面最大承压 kg（方案生成时快照")
    original_length = Column(Float, nullable=True, comment="原始长度 mm")
    original_width = Column(Float, nullable=True, comment="原始宽度 mm")
    original_height = Column(Float, nullable=True, comment="原始高度 mm")
    temperature_class = Column(String, nullable=True, default="AMBIENT", comment="温控等级: FROZEN/REFRIGERATED/AMBIENT")

    plan = relationship("PackingPlan", back_populates="placed_cargos")


class UnplacedCargo(Base):
    __tablename__ = "unplaced_cargos"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("packing_plans.id"))
    cargo_id = Column(Integer)
    cargo_name = Column(String)
    reason = Column(String)

    plan = relationship("PackingPlan", back_populates="unplaced_cargos")


class Trailer(Base):
    __tablename__ = "trailers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    total_length = Column(Float)
    platform_length = Column(Float)
    platform_width = Column(Float)
    front_axle_position = Column(Float)
    rear_axle_position = Column(Float)
    front_axle_max_load = Column(Float)
    rear_axle_max_load = Column(Float)
    total_max_weight = Column(Float)
    is_default = Column(Boolean, default=False)


class TrailerLoadPlan(Base):
    __tablename__ = "trailer_load_plans"

    id = Column(Integer, primary_key=True, index=True)
    plan_no = Column(String, unique=True, index=True)
    trailer_id = Column(Integer, ForeignKey("trailers.id"))
    trailer_name = Column(String)
    total_boxes = Column(Integer)
    total_weight = Column(Float)
    front_axle_load = Column(Float)
    rear_axle_load = Column(Float)
    front_axle_load_ratio = Column(Float)
    rear_axle_load_ratio = Column(Float)
    axles_within_limit = Column(Boolean)
    left_right_balance_ratio = Column(Float)
    left_right_within_limit = Column(Boolean)
    cog_x = Column(Float)
    cog_y = Column(Float)
    score = Column(Float, default=0.0)
    recommendation = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now())

    loaded_boxes = relationship("TrailerLoadedBox", back_populates="plan", cascade="all, delete-orphan")
    unload_sequence = relationship("UnloadStep", back_populates="plan", cascade="all, delete-orphan")


class TrailerLoadedBox(Base):
    __tablename__ = "trailer_loaded_boxes"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("trailer_load_plans.id"))
    box_id = Column(Integer)
    box_name = Column(String)
    x = Column(Float)
    y = Column(Float)
    length = Column(Float)
    width = Column(Float)
    weight = Column(Float)
    cog_offset_x = Column(Float)

    plan = relationship("TrailerLoadPlan", back_populates="loaded_boxes")


class UnloadStep(Base):
    __tablename__ = "unload_steps"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("trailer_load_plans.id"))
    step_number = Column(Integer)
    box_id = Column(Integer)
    box_name = Column(String)
    front_axle_load_before = Column(Float)
    rear_axle_load_before = Column(Float)
    front_axle_load_after = Column(Float)
    rear_axle_load_after = Column(Float)
    left_weight_before = Column(Float)
    right_weight_before = Column(Float)
    left_right_ratio_before = Column(Float)
    left_right_within_limit_before = Column(Boolean)
    axles_within_limit_before = Column(Boolean)

    plan = relationship("TrailerLoadPlan", back_populates="unload_sequence")


class HazardSegregationMatrix(Base):
    __tablename__ = "hazard_segregation_matrix"

    id = Column(Integer, primary_key=True, index=True)
    class_a = Column(Integer, comment="危险品等级A")
    class_b = Column(Integer, comment="危险品等级B")
    min_distance_mm = Column(Float, comment="最小隔离距离 mm")
    segregation_level = Column(String, default="separated", comment="隔离等级: separated/isolated/away_from")
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class ComplianceAudit(Base):
    __tablename__ = "compliance_audits"

    id = Column(Integer, primary_key=True, index=True)
    audit_no = Column(String, unique=True, index=True, comment="审计编号")
    plan_id = Column(Integer, ForeignKey("packing_plans.id"))
    plan_version = Column(Integer, comment="审计时的方案版本")
    plan_content_hash = Column(String, nullable=True, comment="审计时的方案内容哈希")
    is_passed = Column(Boolean, default=False, comment="是否通过")
    hazard_check_passed = Column(Boolean, default=True, comment="危险品隔离校验")
    weight_check_passed = Column(Boolean, default=True, comment="重量偏差校验")
    name_check_passed = Column(Boolean, default=True, comment="品名匹配校验")
    temperature_check_passed = Column(Boolean, default=True, comment="温控分区校验")
    hazard_violations = Column(JSON, default=list, comment="危险品违规详情")
    weight_violations = Column(JSON, default=list, comment="重量违规详情")
    name_violations = Column(JSON, default=list, comment="品名违规详情")
    temperature_violations = Column(JSON, default=list, comment="温控违规详情")
    audit_details = Column(JSON, default=dict, comment="完整审计报告")
    auditor = Column(String, nullable=True, comment="审计员")
    audited_at = Column(DateTime, server_default=func.now())
    remarks = Column(Text, nullable=True)

    plan = relationship("PackingPlan", back_populates="compliance_audits")


class CustomsDocument(Base):
    __tablename__ = "customs_documents"

    id = Column(Integer, primary_key=True, index=True)
    document_no = Column(String, unique=True, index=True, comment="单据编号")
    document_type = Column(String, comment="单据类型: PACKING_LIST / CLC")
    plan_id = Column(Integer, ForeignKey("packing_plans.id"))
    plan_version = Column(Integer, comment="关联的方案版本")
    plan_content_hash = Column(String, nullable=True, comment="关联的方案内容哈希")
    audit_id = Column(Integer, ForeignKey("compliance_audits.id"), nullable=True)
    status = Column(String, default="valid", comment="状态: valid/void/superseded/outdated")
    superseded_by = Column(Integer, ForeignKey("customs_documents.id"), nullable=True, comment="被哪个新单据替换")
    container_no = Column(String, nullable=True, comment="集装箱箱号")
    seal_no = Column(String, nullable=True, comment="铅封号")
    total_packages = Column(Integer, default=0, comment="总件数")
    total_weight_kg = Column(Float, default=0.0, comment="总重量 kg")
    total_volume_cbm = Column(Float, default=0.0, comment="总体积 CBM")
    cog_offset_ratio = Column(Float, nullable=True, comment="重心偏移率")
    volume_utilization = Column(Float, nullable=True, comment="空间利用率")
    weight_utilization = Column(Float, nullable=True, comment="重量利用率")
    document_content = Column(JSON, default=dict, comment="完整单据内容")
    issued_by = Column(String, nullable=True, comment="签发人")
    issued_at = Column(DateTime, server_default=func.now())
    voided_at = Column(DateTime, nullable=True)
    void_reason = Column(Text, nullable=True)
    original_hauler_signature = Column(String, nullable=True)
    original_customs_declaration_no = Column(String, nullable=True, comment="关联报关单号")

    plan = relationship("PackingPlan", back_populates="customs_documents")
    audit = relationship("ComplianceAudit", foreign_keys=[audit_id])
    superseding_document = relationship("CustomsDocument", remote_side=[id], foreign_keys=[superseded_by])
    document_items = relationship("CustomsDocumentItem", back_populates="document", cascade="all, delete-orphan")


class CustomsDocumentItem(Base):
    __tablename__ = "customs_document_items"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("customs_documents.id"))
    item_no = Column(Integer, comment="件号/序号")
    cargo_id = Column(Integer, nullable=True)
    cargo_name = Column(String, comment="品名")
    declared_name = Column(String, nullable=True, comment="申报品名")
    package_count = Column(Integer, default=1, comment="件数")
    package_type = Column(String, default="CTN", comment="包装类型")
    weight_kg = Column(Float, default=0.0, comment="单件重量 kg")
    declared_weight_kg = Column(Float, nullable=True, comment="申报重量 kg")
    length_mm = Column(Float, nullable=True)
    width_mm = Column(Float, nullable=True)
    height_mm = Column(Float, nullable=True)
    volume_cbm = Column(Float, nullable=True)
    x_mm = Column(Float, comment="位置X坐标 mm")
    y_mm = Column(Float, comment="位置Y坐标 mm")
    z_mm = Column(Float, comment="位置Z坐标 mm")
    stack_layer = Column(Integer, default=1, comment="堆叠层号")
    hazard_class = Column(Integer, nullable=True, comment="危险品等级")
    marks_and_numbers = Column(String, nullable=True, comment="唛头")
    hs_code = Column(String, nullable=True, comment="HS编码")

    document = relationship("CustomsDocument", back_populates="document_items")


class StowageReport(Base):
    __tablename__ = "stowage_reports"

    id = Column(Integer, primary_key=True, index=True)
    report_no = Column(String, unique=True, index=True, comment="报告编号")
    plan_id = Column(Integer, ForeignKey("packing_plans.id"))
    plan_no = Column(String, index=True, comment="关联方案编号")
    plan_version = Column(Integer, comment="关联方案版本")
    total_cargos = Column(Integer, comment="货物总数")
    flipped_count = Column(Integer, default=0, comment="被翻转的货物数量")
    warning_count = Column(Integer, default=0, comment="承压预警货物数量")
    danger_count = Column(Integer, default=0, comment="承压危险货物数量")
    health_score = Column(Float, default=0.0, comment="堆码健康度评分(0-100)")
    report_data = Column(JSON, default=dict, comment="完整报告数据(JSON)")
    summary = Column(JSON, default=dict, comment="摘要数据")
    created_at = Column(DateTime, server_default=func.now())

    plan = relationship("PackingPlan")


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_no = Column(String, unique=True, index=True, comment="复核任务编号")
    plan_id = Column(Integer, ForeignKey("packing_plans.id"))
    plan_no = Column(String, index=True, comment="关联方案编号")
    plan_version = Column(Integer, comment="复核时的方案版本")
    plan_content_hash = Column(String, nullable=True, comment="复核时的方案内容哈希")
    status = Column(String, default="pending", comment="状态: pending待开始/in_progress进行中/completed已完成/cancelled已取消")
    is_valid = Column(Boolean, default=True, comment="是否有效，方案变更后自动失效")
    invalid_reason = Column(String, nullable=True, comment="失效原因")
    created_by = Column(String, nullable=True, comment="创建人")
    created_at = Column(DateTime, server_default=func.now())
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    remarks = Column(Text, nullable=True)

    plan = relationship("PackingPlan")
    cargo_records = relationship("ReviewCargoRecord", back_populates="task", cascade="all, delete-orphan")
    discrepancies = relationship("ReviewDiscrepancy", back_populates="task", cascade="all, delete-orphan")
    confirmations = relationship("LoadingConfirmation", back_populates="task", cascade="all, delete-orphan")


class UnloadingRoute(Base):
    __tablename__ = "unloading_routes"

    id = Column(Integer, primary_key=True, index=True)
    route_no = Column(String, unique=True, index=True, comment="路线编号")
    plan_id = Column(Integer, ForeignKey("packing_plans.id"), comment="关联配载方案ID")
    plan_no = Column(String, index=True, comment="关联配载方案编号")
    name = Column(String, comment="路线名称")
    description = Column(Text, nullable=True, comment="路线描述")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(String, nullable=True)

    plan = relationship("PackingPlan")
    stops = relationship("UnloadingRouteStop", back_populates="route", cascade="all, delete-orphan", order_by="UnloadingRouteStop.stop_order")
    cargo_assignments = relationship("UnloadingCargoAssignment", back_populates="route", cascade="all, delete-orphan")
    simulations = relationship("UnloadingSimulation", back_populates="route", cascade="all, delete-orphan")


class UnloadingRouteStop(Base):
    __tablename__ = "unloading_route_stops"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("unloading_routes.id"))
    stop_order = Column(Integer, comment="站点顺序，从1开始")
    stop_name = Column(String, comment="站点名称")
    stop_code = Column(String, nullable=True, comment="站点编码")
    contact_person = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    address = Column(Text, nullable=True)

    route = relationship("UnloadingRoute", back_populates="stops")


class UnloadingCargoAssignment(Base):
    __tablename__ = "unloading_cargo_assignments"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("unloading_routes.id"))
    packed_cargo_id = Column(Integer, ForeignKey("packed_cargos.id"), comment="关联已装载货物ID")
    cargo_id = Column(Integer, comment="货物ID")
    cargo_name = Column(String, comment="货物名称")
    stop_id = Column(Integer, ForeignKey("unloading_route_stops.id"), comment="所属站点ID")
    stop_order = Column(Integer, comment="所属站点顺序")
    unload_order = Column(Integer, comment="在本站点的卸货顺序")

    route = relationship("UnloadingRoute", back_populates="cargo_assignments")
    stop = relationship("UnloadingRouteStop")
    packed_cargo = relationship("PackedCargo")


class UnloadingSimulation(Base):
    __tablename__ = "unloading_simulations"

    id = Column(Integer, primary_key=True, index=True)
    simulation_no = Column(String, unique=True, index=True, comment="推演编号")
    route_id = Column(Integer, ForeignKey("unloading_routes.id"))
    route_no = Column(String, index=True)
    status = Column(String, default="completed", comment="推演状态: pending/running/completed/failed/deadlock")
    total_stops = Column(Integer, comment="总站数")
    total_cargos = Column(Integer, comment="总货物数")
    total_rehandle_count = Column(Integer, default=0, comment="总返搬次数")
    worst_stop_id = Column(Integer, nullable=True, comment="最糟糕站点ID")
    worst_stop_order = Column(Integer, nullable=True, comment="最糟糕站点顺序")
    worst_stop_rehandle_count = Column(Integer, default=0, comment="最糟糕站点返搬次数")
    has_deadlock = Column(Boolean, default=False, comment="是否存在死局")
    deadlock_stop_id = Column(Integer, nullable=True, comment="死局发生站点ID")
    deadlock_stop_order = Column(Integer, nullable=True, comment="死局发生站点顺序")
    deadlock_cargo_ids = Column(JSON, default=list, comment="造成死局的货物ID列表")
    poorly_stacked_cargo_ids = Column(JSON, default=list, comment="从头到尾不该被压在前站货上面的货物ID列表")
    simulation_data = Column(JSON, default=dict, comment="完整推演数据")
    created_at = Column(DateTime, server_default=func.now())

    route = relationship("UnloadingRoute", back_populates="simulations")
    stop_results = relationship("UnloadingStopResult", back_populates="simulation", cascade="all, delete-orphan", order_by="UnloadingStopResult.stop_order")


class UnloadingStopResult(Base):
    __tablename__ = "unloading_stop_results"

    id = Column(Integer, primary_key=True, index=True)
    simulation_id = Column(Integer, ForeignKey("unloading_simulations.id"))
    stop_id = Column(Integer, ForeignKey("unloading_route_stops.id"))
    stop_order = Column(Integer, comment="站点顺序")
    stop_name = Column(String, comment="站点名称")
    rehandle_count = Column(Integer, default=0, comment="本站返搬次数")
    unload_count = Column(Integer, default=0, comment="本站卸货数量")
    remaining_count = Column(Integer, default=0, comment="本站结束后剩余货物数量")
    has_deadlock = Column(Boolean, default=False, comment="本站是否发生死局")
    deadlock_cargo_ids = Column(JSON, default=list, comment="本站造成死局的货物ID列表")
    moves = Column(JSON, default=list, comment="本站所有动作列表")
    remaining_cargos_state = Column(JSON, default=list, comment="本站结束后箱内剩余货物状态")

    simulation = relationship("UnloadingSimulation", back_populates="stop_results")
    stop = relationship("UnloadingRouteStop")


class ReviewCargoRecord(Base):
    __tablename__ = "review_cargo_records"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("review_tasks.id"))
    plan_cargo_id = Column(Integer, nullable=True, comment="对应计划中的PackedCargo ID，None表示多装")
    cargo_id = Column(Integer)
    cargo_name = Column(String)
    review_status = Column(String, default="pending", comment="复核状态: pending待复核/confirmed已确认/missing漏装/extra多装")
    plan_x = Column(Float, nullable=True)
    plan_y = Column(Float, nullable=True)
    plan_z = Column(Float, nullable=True)
    plan_orientation = Column(String, nullable=True)
    plan_load_order = Column(Integer, nullable=True, comment="计划装入顺序")
    actual_x = Column(Float, nullable=True)
    actual_y = Column(Float, nullable=True)
    actual_z = Column(Float, nullable=True)
    actual_orientation = Column(String, nullable=True)
    actual_load_order = Column(Integer, nullable=True, comment="实际装入顺序")
    loaded_at = Column(DateTime, nullable=True, comment="实际装入时间")
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    remarks = Column(Text, nullable=True)

    task = relationship("ReviewTask", back_populates="cargo_records")
    discrepancies = relationship("ReviewDiscrepancy", back_populates="cargo_record")


class ReviewDiscrepancy(Base):
    __tablename__ = "review_discrepancies"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("review_tasks.id"))
    cargo_record_id = Column(Integer, ForeignKey("review_cargo_records.id"), nullable=True)
    discrepancy_type = Column(String, comment="差异类型: missing漏装/extra多装/position位置偏差/orientation朝向偏差/pressure_risk承压风险/temperature_violation温控失效")
    severity = Column(String, default="releasable", comment="严重等级: blocking阻断/releasable可放行")
    description = Column(String, comment="差异描述")
    details = Column(JSON, default=dict, comment="详细信息")
    is_resolved = Column(Boolean, default=False, comment="是否已处理")
    resolved_by = Column(String, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_note = Column(Text, nullable=True)
    is_waived = Column(Boolean, default=False, comment="是否已放行")
    waived_by = Column(String, nullable=True)
    waived_at = Column(DateTime, nullable=True)
    waive_reason = Column(Text, nullable=True)

    task = relationship("ReviewTask", back_populates="discrepancies")
    cargo_record = relationship("ReviewCargoRecord", back_populates="discrepancies")


class LoadingConfirmation(Base):
    __tablename__ = "loading_confirmations"

    id = Column(Integer, primary_key=True, index=True)
    confirmation_no = Column(String, unique=True, index=True, comment="确认单编号")
    task_id = Column(Integer, ForeignKey("review_tasks.id"))
    plan_id = Column(Integer, ForeignKey("packing_plans.id"))
    plan_no = Column(String, index=True)
    plan_version = Column(Integer)
    plan_content_hash = Column(String, nullable=True)
    status = Column(String, default="draft", comment="状态: draft草稿/confirmed已确认/void已失效")
    is_valid = Column(Boolean, default=True, comment="是否有效，方案变更后自动失效")
    total_planned = Column(Integer, default=0, comment="计划件数")
    total_actual = Column(Integer, default=0, comment="实际件数")
    total_discrepancies = Column(Integer, default=0, comment="总差异数")
    blocking_count = Column(Integer, default=0, comment="阻断差异数")
    releasable_count = Column(Integer, default=0, comment="可放行差异数")
    is_released = Column(Boolean, default=False, comment="是否放行")
    released_by = Column(String, nullable=True)
    released_at = Column(DateTime, nullable=True)
    release_reason = Column(Text, nullable=True)
    summary_data = Column(JSON, default=dict, comment="汇总数据")
    created_at = Column(DateTime, server_default=func.now())
    confirmed_at = Column(DateTime, nullable=True)

    task = relationship("ReviewTask", back_populates="confirmations")
    plan = relationship("PackingPlan")
