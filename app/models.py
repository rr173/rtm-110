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
    hazard_violations = Column(JSON, default=list, comment="危险品违规详情")
    weight_violations = Column(JSON, default=list, comment="重量违规详情")
    name_violations = Column(JSON, default=list, comment="品名违规详情")
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
