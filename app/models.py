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
    shipment_no = Column(String, nullable=True, comment="运单号/提单号")

    placed_cargos = relationship("PackedCargo", back_populates="plan", cascade="all, delete-orphan")
    unplaced_cargos = relationship("UnplacedCargo", back_populates="plan", cascade="all, delete-orphan")
    compliance_audits = relationship("ComplianceAudit", back_populates="plan", cascade="all, delete-orphan")
    customs_documents = relationship("CustomsDocument", back_populates="plan", cascade="all, delete-orphan")
    publications = relationship("PublicationRecord", back_populates="plan", cascade="all, delete-orphan")


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
    can_flip = Column(Boolean, default=True, comment="是否可翻转")
    site_code = Column(String, nullable=True, comment="卸货站点编码")
    site_order = Column(Integer, nullable=True, comment="卸货顺序")
    unload_sequence = Column(Integer, nullable=True, comment="推演的卸货顺序号")

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
    packing_plan_id = Column(Integer, ForeignKey("packing_plans.id"), nullable=True, comment="关联的配载方案ID")
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
    plan_version = Column(Integer, comment="关联的配载方案版本")
    plan_content_hash = Column(String, nullable=True, comment="关联的配载方案内容哈希")
    status = Column(String, default="valid", comment="状态: valid有效/outdated已过期/void已作废")

    loaded_boxes = relationship("TrailerLoadedBox", back_populates="plan", cascade="all, delete-orphan")
    unload_sequence = relationship("UnloadStep", back_populates="plan", cascade="all, delete-orphan")
    packing_plan = relationship("PackingPlan")


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
    status = Column(String, default="valid", comment="状态: valid有效/outdated已过期/void已作废")
    void_reason = Column(String, nullable=True, comment="作废/过期原因")
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
    plan_content_hash = Column(String, nullable=True, comment="关联的方案内容哈希")
    total_cargos = Column(Integer, comment="货物总数")
    flipped_count = Column(Integer, default=0, comment="被翻转的货物数量")
    warning_count = Column(Integer, default=0, comment="承压预警货物数量")
    danger_count = Column(Integer, default=0, comment="承压危险货物数量")
    health_score = Column(Float, default=0.0, comment="堆码健康度评分(0-100)")
    report_data = Column(JSON, default=dict, comment="完整报告数据(JSON)")
    summary = Column(JSON, default=dict, comment="摘要数据")
    status = Column(String, default="valid", comment="状态: valid有效/outdated已过期/void已作废")
    void_reason = Column(String, nullable=True, comment="作废/过期原因")
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


class ChangeDraft(Base):
    __tablename__ = "change_drafts"

    id = Column(Integer, primary_key=True, index=True)
    draft_no = Column(String, unique=True, index=True, comment="变更草案编号")
    plan_id = Column(Integer, ForeignKey("packing_plans.id"), comment="关联方案ID")
    plan_no = Column(String, index=True, comment="关联方案编号")
    base_version = Column(Integer, comment="基于的方案版本")
    base_content_hash = Column(String, comment="基于的方案内容哈希")
    status = Column(String, default="draft", comment="状态: draft草稿/analyzing分析中/analyzed已分析/applied已应用/cancelled已取消")
    change_type = Column(String, comment="变更类型: cargo_info货物资料/site_assign站点分配/plan_meta方案元数据/mixed混合")
    change_description = Column(Text, nullable=True, comment="变更描述")
    proposed_changes = Column(JSON, default=dict, comment="拟变更内容(JSON)")
    created_by = Column(String, nullable=True, comment="创建人")
    created_at = Column(DateTime, server_default=func.now())
    analyzed_at = Column(DateTime, nullable=True, comment="分析时间")
    applied_at = Column(DateTime, nullable=True, comment="应用时间")
    applied_by = Column(String, nullable=True, comment="应用人")
    remarks = Column(Text, nullable=True)

    plan = relationship("PackingPlan")
    impact_analysis = relationship("ChangeImpactAnalysis", back_populates="draft", uselist=False, cascade="all, delete-orphan")


class ChangeImpactAnalysis(Base):
    __tablename__ = "change_impact_analyses"

    id = Column(Integer, primary_key=True, index=True)
    analysis_no = Column(String, unique=True, index=True, comment="分析编号")
    draft_id = Column(Integer, ForeignKey("change_drafts.id"), comment="关联变更草案ID")
    plan_id = Column(Integer, ForeignKey("packing_plans.id"), comment="关联方案ID")
    plan_no = Column(String, index=True, comment="关联方案编号")
    base_version = Column(Integer, comment="分析时的方案版本")
    new_version = Column(Integer, comment="变更后的方案版本")
    total_affected_count = Column(Integer, default=0, comment="受影响的结果总数")
    need_rerun_count = Column(Integer, default=0, comment="需要重跑的数量")
    can_keep_count = Column(Integer, default=0, comment="可沿用的数量")
    must_invalidate_count = Column(Integer, default=0, comment="需失效的数量")
    analysis_summary = Column(Text, nullable=True, comment="分析摘要")
    created_at = Column(DateTime, server_default=func.now())

    draft = relationship("ChangeDraft", back_populates="impact_analysis")
    plan = relationship("PackingPlan")
    impact_items = relationship("ChangeImpactItem", back_populates="analysis", cascade="all, delete-orphan")
    diff_snapshot = relationship("ChangeDiffSnapshot", back_populates="analysis", uselist=False, cascade="all, delete-orphan")


class ChangeImpactItem(Base):
    __tablename__ = "change_impact_items"

    id = Column(Integer, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("change_impact_analyses.id"), comment="关联分析ID")
    result_type = Column(String, comment="结果类型: stowage_report堆码报告/compliance_audit合规审核/review_task装箱复核/unloading_route卸货路线/unloading_simulation卸货推演/trailer_load拖车装载/customs_document海关单据")
    result_id = Column(Integer, comment="关联结果ID")
    result_no = Column(String, index=True, comment="关联结果编号")
    result_version = Column(Integer, nullable=True, comment="结果关联的方案版本")
    impact_decision = Column(String, comment="影响决策: keep可沿用/rerun需重跑/invalidate需失效")
    impact_reason = Column(Text, comment="影响原因")
    affected_fields = Column(JSON, default=list, comment="受影响的字段列表")
    created_at = Column(DateTime, server_default=func.now())

    analysis = relationship("ChangeImpactAnalysis", back_populates="impact_items")


class ChangeDiffSnapshot(Base):
    __tablename__ = "change_diff_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_no = Column(String, unique=True, index=True, comment="快照编号")
    analysis_id = Column(Integer, ForeignKey("change_impact_analyses.id"), comment="关联分析ID")
    plan_id = Column(Integer, ForeignKey("packing_plans.id"), comment="关联方案ID")
    plan_no = Column(String, index=True, comment="关联方案编号")
    base_version = Column(Integer, comment="变更前版本")
    new_version = Column(Integer, comment="变更后版本")
    before_data = Column(JSON, default=dict, comment="变更前完整数据")
    after_data = Column(JSON, default=dict, comment="变更后完整数据")
    field_diffs = Column(JSON, default=list, comment="字段级差异列表")
    cargo_diffs = Column(JSON, default=list, comment="货物级差异列表")
    created_at = Column(DateTime, server_default=func.now())

    analysis = relationship("ChangeImpactAnalysis", back_populates="diff_snapshot")
    plan = relationship("PackingPlan")


class PublicationRecord(Base):
    __tablename__ = "publication_records"

    id = Column(Integer, primary_key=True, index=True)
    publication_no = Column(String, unique=True, index=True, comment="发布编号")
    plan_id = Column(Integer, ForeignKey("packing_plans.id"))
    plan_no = Column(String, index=True, comment="方案编号")
    plan_version = Column(Integer, comment="发布时的方案版本")
    plan_content_hash = Column(String, nullable=True, comment="发布时的方案内容哈希")
    container_no = Column(String, nullable=True, comment="冻结的箱号")
    seal_no = Column(String, nullable=True, comment="冻结的铅封号")
    audit_id = Column(Integer, nullable=True, comment="冻结的审核ID")
    audit_no = Column(String, nullable=True, comment="冻结的审核编号")
    audit_passed = Column(Boolean, default=False, comment="冻结的审核结论")
    confirmation_id = Column(Integer, nullable=True, comment="冻结的确认单ID")
    confirmation_no = Column(String, nullable=True, comment="冻结的确认单编号")
    confirmation_released = Column(Boolean, default=False, comment="冻结的确认单是否放行")
    route_id = Column(Integer, nullable=True, comment="冻结的路线ID")
    route_no = Column(String, nullable=True, comment="冻结的路线编号")
    simulation_id = Column(Integer, nullable=True, comment="冻结的推演ID")
    simulation_no = Column(String, nullable=True, comment="冻结的推演编号")
    trailer_plan_id = Column(Integer, nullable=True, comment="冻结的拖车方案ID")
    trailer_plan_no = Column(String, nullable=True, comment="冻结的拖车方案编号")
    document_snapshot = Column(JSON, default=list, comment="冻结的单据摘要列表")
    snapshot_data = Column(JSON, default=dict, comment="完整发布快照")
    status = Column(String, default="pending_approval", comment="状态: pending_approval待审批/approved已发布/rejected已驳回/revoked已撤回")
    published_by = Column(String, nullable=True, comment="提交人")
    published_at = Column(DateTime, server_default=func.now())
    approved_by = Column(String, nullable=True, comment="审批人")
    approved_at = Column(DateTime, nullable=True)
    rejected_reason = Column(Text, nullable=True, comment="驳回原因")
    gate_check_result = Column(JSON, default=dict, comment="发布闸口检查结果")

    plan = relationship("PackingPlan", back_populates="publications")
    dispatch_task = relationship("DispatchTask", back_populates="publication", uselist=False, cascade="all, delete-orphan")


class DispatchTask(Base):
    __tablename__ = "dispatch_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_no = Column(String, unique=True, index=True, comment="发运任务编号")
    plan_id = Column(Integer, ForeignKey("packing_plans.id"))
    plan_no = Column(String, index=True, comment="方案编号")
    publication_id = Column(Integer, ForeignKey("publication_records.id"))
    frozen_version = Column(Integer, comment="冻结的方案版本")
    frozen_content_hash = Column(String, nullable=True, comment="冻结的方案内容哈希")
    frozen_snapshot = Column(JSON, default=dict, comment="发布时冻结的完整快照(方案/箱号铅封/审核/确认单/路线/拖车/单据)")
    vehicle_no = Column(String, nullable=True, comment="车牌号")
    driver_name = Column(String, nullable=True, comment="司机姓名")
    planned_departure_time = Column(DateTime, nullable=True, comment="计划出车时间")
    arrival_time = Column(DateTime, nullable=True, comment="到场时间")
    terminal_window = Column(String, nullable=True, comment="码头窗口")
    status = Column(String, default="pending_approval", comment="状态: pending_approval待审批/pending_dispatch待出车/loading装车中/dispatched已发运/cancelled已取消/pending_re_review待重审")
    block_reasons = Column(JSON, default=list, comment="阻断原因列表,每项含type和detail")
    last_validated_at = Column(DateTime, nullable=True, comment="最近一次校验时间")
    status_changed_at = Column(DateTime, nullable=True, comment="状态变更时间")
    created_by = Column(String, nullable=True, comment="创建人")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    plan = relationship("PackingPlan")
    publication = relationship("PublicationRecord", back_populates="dispatch_task")
