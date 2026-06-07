from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text
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

    placed_cargos = relationship("PackedCargo", back_populates="plan", cascade="all, delete-orphan")
    unplaced_cargos = relationship("UnplacedCargo", back_populates="plan", cascade="all, delete-orphan")


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
