from sqlalchemy.orm import Session
from app import models, schemas
from app.schemas import TemperatureClassEnum
from datetime import datetime
from typing import List, Optional, Dict, Any
import uuid

VALID_TEMPERATURE_CLASSES = {tc.value for tc in TemperatureClassEnum}


def get_container(db: Session, container_id: int):
    return db.query(models.Container).filter(models.Container.id == container_id).first()


def get_containers(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Container).offset(skip).limit(limit).all()


def create_container(db: Session, container: schemas.ContainerCreate):
    db_container = models.Container(**container.model_dump())
    db.add(db_container)
    db.commit()
    db.refresh(db_container)
    return db_container


def delete_container(db: Session, container_id: int):
    db_container = get_container(db, container_id)
    if db_container:
        db.delete(db_container)
        db.commit()
    return db_container


def get_cargo(db: Session, cargo_id: int):
    return db.query(models.Cargo).filter(models.Cargo.id == cargo_id).first()


def get_cargos(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Cargo).offset(skip).limit(limit).all()


def _normalize_temperature_class(value):
    if value is None:
        return "AMBIENT"
    if isinstance(value, TemperatureClassEnum):
        return value.value
    if isinstance(value, str):
        if value not in VALID_TEMPERATURE_CLASSES:
            raise ValueError(
                f"无效的温控等级 '{value}'，仅允许: {', '.join(sorted(VALID_TEMPERATURE_CLASSES))}"
            )
        return value
    raise ValueError(f"temperature_class 类型错误: {type(value)}")


def create_cargo(db: Session, cargo: schemas.CargoCreate):
    data = cargo.model_dump()
    if "temperature_class" in data:
        data["temperature_class"] = _normalize_temperature_class(data["temperature_class"])
    db_cargo = models.Cargo(**data)
    db.add(db_cargo)
    db.commit()
    db.refresh(db_cargo)
    return db_cargo


def update_cargo(db: Session, cargo_id: int, cargo_update: schemas.CargoUpdate):
    db_cargo = get_cargo(db, cargo_id)
    if not db_cargo:
        return None
    update_data = cargo_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "temperature_class":
            value = _normalize_temperature_class(value)
        setattr(db_cargo, key, value)
    db.commit()
    db.refresh(db_cargo)
    return db_cargo


def delete_cargo(db: Session, cargo_id: int):
    db_cargo = get_cargo(db, cargo_id)
    if db_cargo:
        db.delete(db_cargo)
        db.commit()
    return db_cargo


def create_default_containers(db: Session):
    existing = db.query(models.Container).filter(models.Container.is_default == True).all()
    if existing:
        return

    default_containers = [
        models.Container(
            name="20尺标准箱",
            length=5898.0,
            width=2352.0,
            height=2393.0,
            max_weight=28200.0,
            is_default=True
        ),
        models.Container(
            name="40尺高箱",
            length=12032.0,
            width=2352.0,
            height=2698.0,
            max_weight=26580.0,
            is_default=True
        ),
    ]
    db.add_all(default_containers)
    db.commit()


def generate_plan_no() -> str:
    return f"PLAN-{uuid.uuid4().hex[:8].upper()}"


def create_packing_plan(db: Session, plan_data: dict, placed_cargos: list, unplaced_cargos: list = None) -> models.PackingPlan:
    plan_no = generate_plan_no()
    db_plan = models.PackingPlan(
        plan_no=plan_no,
        container_id=plan_data["container_id"],
        container_name=plan_data["container_name"],
        total_cargos=plan_data["total_cargos"],
        placed_count=plan_data["placed_count"],
        unplaced_count=plan_data["unplaced_count"],
        total_weight=plan_data["total_weight"],
        volume_utilization=plan_data["volume_utilization"],
        cog_x=plan_data["cog_x"],
        cog_y=plan_data["cog_y"],
        cog_z=plan_data["cog_z"],
        cog_within_limit=plan_data["cog_within_limit"],
        cog_offset_x_ratio=plan_data["cog_offset_x_ratio"],
        cog_offset_y_ratio=plan_data["cog_offset_y_ratio"],
        score=plan_data.get("score", 0.0),
        rank=plan_data.get("rank", 0),
        recommendation=plan_data.get("recommendation", "")
    )
    db.add(db_plan)
    db.flush()

    for pc in placed_cargos:
        db_packed = models.PackedCargo(
            plan_id=db_plan.id,
            cargo_id=pc["cargo_id"],
            cargo_name=pc["cargo_name"],
            x=pc["x"],
            y=pc["y"],
            z=pc["z"],
            length=pc["length"],
            width=pc["width"],
            height=pc["height"],
            weight=pc["weight"],
            orientation=pc["orientation"],
            max_top_load=pc.get("max_top_load", 0.0),
            original_length=pc.get("original_length"),
            original_width=pc.get("original_width"),
            original_height=pc.get("original_height"),
            temperature_class=pc.get("temperature_class", "AMBIENT")
        )
        db.add(db_packed)

    if unplaced_cargos:
        for uc in unplaced_cargos:
            db_unplaced = models.UnplacedCargo(
                plan_id=db_plan.id,
                cargo_id=uc.get("cargo_id", 0),
                cargo_name=uc.get("cargo_name", ""),
                reason=uc.get("reason", "")
            )
            db.add(db_unplaced)

    db.commit()
    db.refresh(db_plan)
    return db_plan


def get_packing_plan(db: Session, plan_id: int = None, plan_no: str = None) -> models.PackingPlan:
    if plan_id:
        return db.query(models.PackingPlan).filter(models.PackingPlan.id == plan_id).first()
    if plan_no:
        return db.query(models.PackingPlan).filter(models.PackingPlan.plan_no == plan_no).first()
    return None


def get_packing_plans(db: Session, skip: int = 0, limit: int = 100) -> list:
    return db.query(models.PackingPlan).order_by(models.PackingPlan.created_at.desc()).offset(skip).limit(limit).all()


def get_packed_cargos(db: Session, plan_id: int) -> list:
    return db.query(models.PackedCargo).filter(models.PackedCargo.plan_id == plan_id).all()


def get_unplaced_cargos(db: Session, plan_id: int) -> list:
    return db.query(models.UnplacedCargo).filter(models.UnplacedCargo.plan_id == plan_id).all()


def delete_packing_plan(db: Session, plan_id: int = None, plan_no: str = None):
    plan = get_packing_plan(db, plan_id=plan_id, plan_no=plan_no)
    if plan:
        db.delete(plan)
        db.commit()
    return plan


def update_packing_plan_score(db: Session, plan_id: int, score: float, rank: int, recommendation: str):
    plan = get_packing_plan(db, plan_id=plan_id)
    if plan:
        plan.score = score
        plan.rank = rank
        plan.recommendation = recommendation
        db.commit()
        db.refresh(plan)
    return plan


def get_trailer(db: Session, trailer_id: int):
    return db.query(models.Trailer).filter(models.Trailer.id == trailer_id).first()


def get_trailers(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Trailer).offset(skip).limit(limit).all()


def create_trailer(db: Session, trailer: schemas.TrailerCreate):
    db_trailer = models.Trailer(**trailer.model_dump())
    db.add(db_trailer)
    db.commit()
    db.refresh(db_trailer)
    return db_trailer


def delete_trailer(db: Session, trailer_id: int):
    db_trailer = get_trailer(db, trailer_id)
    if db_trailer:
        db.delete(db_trailer)
        db.commit()
    return db_trailer


def create_default_trailers(db: Session):
    existing = db.query(models.Trailer).filter(models.Trailer.is_default == True).all()
    if existing:
        return

    default_trailers = [
        models.Trailer(
            name="标准平板拖车-20英尺",
            total_length=9000.0,
            platform_length=6096.0,
            platform_width=2440.0,
            front_axle_position=1500.0,
            rear_axle_position=7500.0,
            front_axle_max_load=8000.0,
            rear_axle_max_load=12000.0,
            total_max_weight=18000.0,
            is_default=True
        ),
        models.Trailer(
            name="重型平板拖车-40英尺",
            total_length=14000.0,
            platform_length=12192.0,
            platform_width=2440.0,
            front_axle_position=2000.0,
            rear_axle_position=12000.0,
            front_axle_max_load=10000.0,
            rear_axle_max_load=20000.0,
            total_max_weight=28000.0,
            is_default=True
        ),
        models.Trailer(
            name="短途配送拖车-轻量型",
            total_length=7000.0,
            platform_length=5000.0,
            platform_width=2200.0,
            front_axle_position=1200.0,
            rear_axle_position=5800.0,
            front_axle_max_load=5000.0,
            rear_axle_max_load=8000.0,
            total_max_weight=12000.0,
            is_default=True
        ),
    ]
    db.add_all(default_trailers)
    db.commit()


def generate_trailer_plan_no() -> str:
    return f"TRAILER-{uuid.uuid4().hex[:8].upper()}"


def create_trailer_load_plan(db: Session, plan_data: dict, loaded_boxes: list, unload_sequence: list = None, packing_plan_id: int = None, plan_version: int = None, plan_content_hash: str = None) -> models.TrailerLoadPlan:
    plan_no = generate_trailer_plan_no()
    db_plan = models.TrailerLoadPlan(
        plan_no=plan_no,
        packing_plan_id=packing_plan_id or plan_data.get("packing_plan_id"),
        trailer_id=plan_data["trailer_id"],
        trailer_name=plan_data["trailer_name"],
        total_boxes=plan_data["total_boxes"],
        total_weight=plan_data["total_weight"],
        front_axle_load=plan_data["front_axle_load"],
        rear_axle_load=plan_data["rear_axle_load"],
        front_axle_load_ratio=plan_data["front_axle_load_ratio"],
        rear_axle_load_ratio=plan_data["rear_axle_load_ratio"],
        axles_within_limit=plan_data["axles_within_limit"],
        left_right_balance_ratio=plan_data["left_right_balance_ratio"],
        left_right_within_limit=plan_data["left_right_within_limit"],
        cog_x=plan_data["cog_x"],
        cog_y=plan_data["cog_y"],
        score=plan_data.get("score", 0.0),
        recommendation=plan_data.get("recommendation", ""),
        plan_version=plan_version or plan_data.get("plan_version"),
        plan_content_hash=plan_content_hash or plan_data.get("plan_content_hash"),
        status="valid"
    )
    db.add(db_plan)
    db.flush()

    for lb in loaded_boxes:
        db_box = models.TrailerLoadedBox(
            plan_id=db_plan.id,
            box_id=lb["box_id"],
            box_name=lb["box_name"],
            x=lb["x"],
            y=lb["y"],
            length=lb["length"],
            width=lb["width"],
            weight=lb["weight"],
            cog_offset_x=lb["cog_offset_x"]
        )
        db.add(db_box)

    if unload_sequence:
        for step in unload_sequence:
            db_step = models.UnloadStep(
                plan_id=db_plan.id,
                step_number=step["step_number"],
                box_id=step["box_id"],
                box_name=step["box_name"],
                front_axle_load_before=step["front_axle_load_before"],
                rear_axle_load_before=step["rear_axle_load_before"],
                front_axle_load_after=step["front_axle_load_after"],
                rear_axle_load_after=step["rear_axle_load_after"],
                left_weight_before=step["left_weight_before"],
                right_weight_before=step["right_weight_before"],
                left_right_ratio_before=step["left_right_ratio_before"],
                left_right_within_limit_before=step["left_right_within_limit_before"],
                axles_within_limit_before=step["axles_within_limit_before"]
            )
            db.add(db_step)

    db.commit()
    db.refresh(db_plan)
    return db_plan


def get_trailer_load_plan(db: Session, plan_id: int = None, plan_no: str = None, trailer_plan_id: int = None):
    if trailer_plan_id:
        return db.query(models.TrailerLoadPlan).filter(models.TrailerLoadPlan.id == trailer_plan_id).first()
    if plan_id:
        return db.query(models.TrailerLoadPlan).filter(models.TrailerLoadPlan.id == plan_id).first()
    if plan_no:
        return db.query(models.TrailerLoadPlan).filter(models.TrailerLoadPlan.plan_no == plan_no).first()
    return None


def get_trailer_load_plans(db: Session, skip: int = 0, limit: int = 100) -> list:
    return db.query(models.TrailerLoadPlan).order_by(models.TrailerLoadPlan.created_at.desc()).offset(skip).limit(limit).all()


def get_trailer_loaded_boxes(db: Session, plan_id: int) -> list:
    return db.query(models.TrailerLoadedBox).filter(models.TrailerLoadedBox.plan_id == plan_id).all()


def get_unload_steps(db: Session, plan_id: int) -> list:
    return db.query(models.UnloadStep).filter(models.UnloadStep.plan_id == plan_id).order_by(models.UnloadStep.step_number).all()


def delete_trailer_load_plan(db: Session, plan_id: int = None, plan_no: str = None):
    plan = get_trailer_load_plan(db, plan_id=plan_id, plan_no=plan_no)
    if plan:
        db.delete(plan)
        db.commit()
    return plan


def create_demo_trailer_scenarios(db: Session):
    from app.packing.trailer_cog_engine import TrailerSpec, BoxSpec, optimize_box_positions, generate_unload_sequence, PlacedBox

    trailers = db.query(models.Trailer).filter(models.Trailer.is_default == True).all()
    if not trailers:
        create_default_trailers(db)
        trailers = db.query(models.Trailer).filter(models.Trailer.is_default == True).all()

    existing_plans = db.query(models.TrailerLoadPlan).all()
    if existing_plans:
        return

    demo_scenarios = [
        {
            "trailer_name": "标准平板拖车-20英尺",
            "boxes": [
                {"box_id": 1, "box_name": "设备箱A", "length": 2400, "width": 1200, "weight": 3500, "cog_offset_x": 0},
                {"box_id": 2, "box_name": "设备箱B", "length": 2000, "width": 1200, "weight": 2800, "cog_offset_x": 100},
                {"box_id": 3, "box_name": "物料箱C", "length": 1800, "width": 1000, "weight": 1500, "cog_offset_x": -50},
                {"box_id": 4, "box_name": "配件箱D", "length": 1500, "width": 1000, "weight": 1200, "cog_offset_x": 0},
                {"box_id": 5, "box_name": "重型箱E", "length": 2200, "width": 1200, "weight": 4200, "cog_offset_x": 150},
            ],
            "description": "标准五箱混装-标准拖车"
        },
        {
            "trailer_name": "重型平板拖车-40英尺",
            "boxes": [
                {"box_id": 10, "box_name": "大型集装箱1", "length": 6000, "width": 2400, "weight": 8000, "cog_offset_x": 200},
                {"box_id": 11, "box_name": "大型集装箱2", "length": 5500, "width": 2400, "weight": 7500, "cog_offset_x": -100},
            ],
            "description": "双大箱重载-重型拖车"
        },
        {
            "trailer_name": "短途配送拖车-轻量型",
            "boxes": [
                {"box_id": 20, "box_name": "快递箱1", "length": 1200, "width": 800, "weight": 500, "cog_offset_x": 0},
                {"box_id": 21, "box_name": "快递箱2", "length": 1000, "width": 800, "weight": 600, "cog_offset_x": 0},
                {"box_id": 22, "box_name": "生鲜箱", "length": 1500, "width": 1000, "weight": 800, "cog_offset_x": 50},
                {"box_id": 23, "box_name": "易碎品箱", "length": 1100, "width": 900, "weight": 400, "cog_offset_x": 0},
                {"box_id": 24, "box_name": "日用品箱", "length": 1300, "width": 1000, "weight": 700, "cog_offset_x": -30},
                {"box_id": 25, "box_name": "家电箱", "length": 1800, "width": 1000, "weight": 900, "cog_offset_x": 80},
                {"box_id": 26, "box_name": "服装箱", "length": 1400, "width": 900, "weight": 350, "cog_offset_x": 0},
                {"box_id": 27, "box_name": "食品箱", "length": 1600, "width": 1100, "weight": 650, "cog_offset_x": 20},
            ],
            "description": "多箱轻载配送-轻量拖车"
        },
    ]

    for scenario in demo_scenarios:
        trailer = db.query(models.Trailer).filter(models.Trailer.name == scenario["trailer_name"]).first()
        if not trailer:
            continue

        trailer_spec = TrailerSpec(
            total_length=trailer.total_length,
            platform_length=trailer.platform_length,
            platform_width=trailer.platform_width,
            front_axle_position=trailer.front_axle_position,
            rear_axle_position=trailer.rear_axle_position,
            front_axle_max_load=trailer.front_axle_max_load,
            rear_axle_max_load=trailer.rear_axle_max_load,
            total_max_weight=trailer.total_max_weight
        )

        box_specs = []
        for b in scenario["boxes"]:
            box_specs.append(BoxSpec(
                box_id=b["box_id"],
                box_name=b["box_name"],
                length=b["length"],
                width=b["width"],
                weight=b["weight"],
                cog_offset_x=b["cog_offset_x"]
            ))

        opt_result = optimize_box_positions(trailer_spec, box_specs)

        placed_boxes = []
        for lb in opt_result["loaded_boxes"]:
            placed_boxes.append(PlacedBox(
                box_id=lb["box_id"],
                box_name=lb["box_name"],
                x=lb["x"],
                y=lb["y"],
                length=lb["length"],
                width=lb["width"],
                weight=lb["weight"],
                cog_offset_x=lb["cog_offset_x"]
            ))

        unload_result = generate_unload_sequence(trailer_spec, placed_boxes, max_lr_ratio=0.15)

        plan_data = {
            "trailer_id": trailer.id,
            "trailer_name": trailer.name,
            "total_boxes": opt_result["total_boxes"],
            "total_weight": opt_result["total_weight"],
            "front_axle_load": opt_result["front_axle_load"],
            "rear_axle_load": opt_result["rear_axle_load"],
            "front_axle_load_ratio": opt_result["front_axle_load_ratio"],
            "rear_axle_load_ratio": opt_result["rear_axle_load_ratio"],
            "axles_within_limit": opt_result["axles_within_limit"],
            "left_right_balance_ratio": opt_result["left_right_balance_ratio"],
            "left_right_within_limit": opt_result["left_right_within_limit"],
            "cog_x": opt_result["cog_x"],
            "cog_y": opt_result["cog_y"],
            "score": opt_result["score"],
            "recommendation": f"【{scenario['description']}】{opt_result['recommendation']}"
        }

        create_trailer_load_plan(db, plan_data, opt_result["loaded_boxes"], unload_result["sequence"])


import hashlib
import json


def compute_plan_content_hash(db: Session, plan_id: int) -> str:
    plan = get_packing_plan(db, plan_id=plan_id)
    if not plan:
        return ""
    packed_cargos = get_packed_cargos(db, plan_id=plan_id)
    cargo_list = []
    for pc in sorted(packed_cargos, key=lambda x: (x.x, x.y, x.z)):
        item = {
            "cargo_id": pc.cargo_id,
            "cargo_name": pc.cargo_name,
            "x": pc.x, "y": pc.y, "z": pc.z,
            "length": pc.length, "width": pc.width, "height": pc.height,
            "weight": pc.weight, "orientation": pc.orientation,
            "max_top_load": pc.max_top_load,
        }
        for extra_field in ["can_flip", "site_code", "site_order", "unload_sequence"]:
            if hasattr(pc, extra_field):
                item[extra_field] = getattr(pc, extra_field)
        cargo_list.append(item)
    content = {
        "container_id": plan.container_id,
        "container_no": plan.container_no,
        "shipment_no": plan.shipment_no,
        "total_cargos": plan.total_cargos,
        "placed_count": plan.placed_count,
        "cog_x": plan.cog_x, "cog_y": plan.cog_y, "cog_z": plan.cog_z,
        "cargos": cargo_list,
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def bump_plan_version(db: Session, plan_id: int) -> models.PackingPlan:
    plan = get_packing_plan(db, plan_id=plan_id)
    if plan:
        old_version = plan.version or 0
        plan.version = old_version + 1
        plan.content_hash = compute_plan_content_hash(db, plan_id)
        invalidate_docs_for_outdated_plan(db, plan_id, plan.content_hash, current_version=plan.version)
        invalidate_reviews_for_outdated_plan(db, plan_id, plan.content_hash, current_version=plan.version)
        db.commit()
        db.refresh(plan)
    return plan


def update_packing_plan_meta(db: Session, plan_id: int, meta: dict):
    plan = get_packing_plan(db, plan_id=plan_id)
    if not plan:
        return None
    changed = False
    for k in ["container_no", "seal_no", "declared_weight"]:
        if k in meta and meta[k] is not None and getattr(plan, k) != meta[k]:
            setattr(plan, k, meta[k])
            changed = True
    if changed:
        bump_plan_version(db, plan_id)
        db.refresh(plan)
    return plan


def get_hazard_matrix(db: Session, class_a: int, class_b: int):
    if class_a == class_b:
        return db.query(models.HazardSegregationMatrix).filter(
            models.HazardSegregationMatrix.class_a == class_a,
            models.HazardSegregationMatrix.class_b == class_b,
            models.HazardSegregationMatrix.is_active == True
        ).first()
    return db.query(models.HazardSegregationMatrix).filter(
        ((models.HazardSegregationMatrix.class_a == class_a) & (models.HazardSegregationMatrix.class_b == class_b)) |
        ((models.HazardSegregationMatrix.class_a == class_b) & (models.HazardSegregationMatrix.class_b == class_a)),
        models.HazardSegregationMatrix.is_active == True
    ).first()


def get_all_hazard_matrix(db: Session):
    return db.query(models.HazardSegregationMatrix).filter(
        models.HazardSegregationMatrix.is_active == True
    ).order_by(models.HazardSegregationMatrix.class_a, models.HazardSegregationMatrix.class_b).all()


def create_hazard_matrix(db: Session, matrix_data: dict):
    db_matrix = models.HazardSegregationMatrix(**matrix_data)
    db.add(db_matrix)
    db.commit()
    db.refresh(db_matrix)
    return db_matrix


def generate_audit_no() -> str:
    return f"AUDIT-{uuid.uuid4().hex[:8].upper()}"


def create_compliance_audit(db: Session, audit_data: dict) -> models.ComplianceAudit:
    db_audit = models.ComplianceAudit(**audit_data)
    db.add(db_audit)
    db.commit()
    db.refresh(db_audit)
    return db_audit


def get_compliance_audit(db: Session, audit_id: int = None, audit_no: str = None):
    if audit_id:
        return db.query(models.ComplianceAudit).filter(models.ComplianceAudit.id == audit_id).first()
    if audit_no:
        return db.query(models.ComplianceAudit).filter(models.ComplianceAudit.audit_no == audit_no).first()
    return None


def get_audits_by_plan(db: Session, plan_id: int):
    return db.query(models.ComplianceAudit).filter(
        models.ComplianceAudit.plan_id == plan_id
    ).order_by(models.ComplianceAudit.audited_at.desc()).all()


def get_latest_passed_audit(db: Session, plan_id: int):
    return db.query(models.ComplianceAudit).filter(
        models.ComplianceAudit.plan_id == plan_id,
        models.ComplianceAudit.is_passed == True
    ).order_by(models.ComplianceAudit.audited_at.desc()).first()


def generate_document_no(doc_type: str) -> str:
    prefix = "PL" if doc_type == "PACKING_LIST" else ("CLC" if doc_type == "CLC" else "DOC")
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def create_customs_document(
    db: Session,
    doc_type: str,
    plan_id: int,
    plan_version: int,
    plan_content_hash: str,
    audit_id: int,
    doc_header: dict,
    doc_summary: dict,
    document_content: dict,
    document_items: list
) -> models.CustomsDocument:
    document_no = generate_document_no(doc_type)
    db_doc = models.CustomsDocument(
        document_no=document_no,
        document_type=doc_type,
        plan_id=plan_id,
        plan_version=plan_version,
        plan_content_hash=plan_content_hash,
        audit_id=audit_id,
        status="valid",
        container_no=doc_header.get("container_no"),
        seal_no=doc_header.get("seal_no"),
        total_packages=doc_summary.get("total_packages", 0),
        total_weight_kg=doc_summary.get("total_weight_kg", 0.0),
        total_volume_cbm=doc_summary.get("total_volume_cbm", 0.0),
        cog_offset_ratio=doc_summary.get("cog_offset_ratio"),
        volume_utilization=doc_summary.get("volume_utilization"),
        weight_utilization=doc_summary.get("weight_utilization"),
        document_content=document_content,
        issued_by=doc_header.get("issued_by"),
        original_customs_declaration_no=doc_header.get("original_customs_declaration_no")
    )
    db.add(db_doc)
    db.flush()

    for item in document_items:
        db_item = models.CustomsDocumentItem(
            document_id=db_doc.id,
            **item
        )
        db.add(db_item)

    db.commit()
    db.refresh(db_doc)
    return db_doc


def get_customs_document(db: Session, doc_id: int = None, document_no: str = None):
    if doc_id:
        return db.query(models.CustomsDocument).filter(models.CustomsDocument.id == doc_id).first()
    if document_no:
        return db.query(models.CustomsDocument).filter(models.CustomsDocument.document_no == document_no).first()
    return None


def get_documents_by_plan(db: Session, plan_id: int, doc_type: str = None, status: str = None):
    q = db.query(models.CustomsDocument).filter(models.CustomsDocument.plan_id == plan_id)
    if doc_type:
        q = q.filter(models.CustomsDocument.document_type == doc_type)
    if status:
        q = q.filter(models.CustomsDocument.status == status)
    return q.order_by(models.CustomsDocument.issued_at.desc()).all()


def list_customs_documents(db: Session, skip: int = 0, limit: int = 100,
                           doc_type: str = None, status: str = None):
    q = db.query(models.CustomsDocument)
    if doc_type:
        q = q.filter(models.CustomsDocument.document_type == doc_type)
    if status:
        q = q.filter(models.CustomsDocument.status == status)
    return q.order_by(models.CustomsDocument.issued_at.desc()).offset(skip).limit(limit).all()


def get_document_items(db: Session, document_id: int):
    return db.query(models.CustomsDocumentItem).filter(
        models.CustomsDocumentItem.document_id == document_id
    ).order_by(models.CustomsDocumentItem.item_no).all()


def void_customs_document(db: Session, doc_id: int, reason: str):
    from datetime import datetime
    doc = get_customs_document(db, doc_id=doc_id)
    if doc:
        doc.status = "void"
        doc.voided_at = datetime.utcnow()
        doc.void_reason = reason
        db.commit()
        db.refresh(doc)
    return doc


def invalidate_docs_for_outdated_plan(db: Session, plan_id: int, current_hash: str, current_version: int = None):
    plan = get_packing_plan(db, plan_id=plan_id)
    if plan is None:
        return
    eff_version = current_version if current_version is not None else plan.version
    docs = db.query(models.CustomsDocument).filter(
        models.CustomsDocument.plan_id == plan_id,
        models.CustomsDocument.status == "valid"
    ).all()
    for doc in docs:
        hash_mismatch = bool(doc.plan_content_hash) and doc.plan_content_hash != current_hash
        version_outdated = (eff_version is not None) and doc.plan_version < eff_version
        if hash_mismatch or version_outdated:
            doc.status = "outdated"
            reasons = []
            if hash_mismatch:
                reasons.append(f"内容哈希不一致")
            if version_outdated:
                reasons.append(f"方案版本从v{doc.plan_version}升级到v{eff_version}")
            doc.void_reason = f"原始装载方案已变更({'，'.join(reasons)})，单据自动失效"
    db.commit()


def reissue_customs_document(
    db: Session,
    old_doc_id: int,
    reason: str,
    audit_id: int,
    doc_header: dict,
    doc_summary: dict,
    document_content: dict,
    document_items: list,
    new_plan_version: int,
    new_plan_hash: str
):
    from datetime import datetime
    old_doc = get_customs_document(db, doc_id=old_doc_id)
    if not old_doc:
        return None
    new_doc = create_customs_document(
        db=db,
        doc_type=old_doc.document_type,
        plan_id=old_doc.plan_id,
        plan_version=new_plan_version,
        plan_content_hash=new_plan_hash,
        audit_id=audit_id,
        doc_header=doc_header,
        doc_summary=doc_summary,
        document_content=document_content,
        document_items=document_items
    )
    old_doc.status = "superseded"
    old_doc.voided_at = datetime.utcnow()
    old_doc.void_reason = f"作废重开: {reason}。新单据编号: {new_doc.document_no}"
    old_doc.superseded_by = new_doc.id
    db.commit()
    db.refresh(old_doc)
    db.refresh(new_doc)
    return new_doc


def create_default_hazard_matrix(db: Session):
    existing = db.query(models.HazardSegregationMatrix).filter(
        models.HazardSegregationMatrix.is_active == True
    ).all()
    if existing:
        return
    matrix_data = [
        {"class_a": 1, "class_b": 1, "min_distance_mm": 0, "segregation_level": "group", "description": "同类爆炸品可混装"},
        {"class_a": 1, "class_b": 2, "min_distance_mm": 3000, "segregation_level": "isolated", "description": "爆炸品与气体需隔离3米"},
        {"class_a": 1, "class_b": 3, "min_distance_mm": 3000, "segregation_level": "isolated", "description": "爆炸品与易燃液体需隔离3米"},
        {"class_a": 1, "class_b": 4, "min_distance_mm": 3000, "segregation_level": "isolated", "description": "爆炸品与易燃固体需隔离3米"},
        {"class_a": 1, "class_b": 5, "min_distance_mm": 4000, "segregation_level": "away_from", "description": "爆炸品与氧化剂需远离4米"},
        {"class_a": 1, "class_b": 6, "min_distance_mm": 3000, "segregation_level": "isolated", "description": "爆炸品与毒害品需隔离3米"},

        {"class_a": 2, "class_b": 2, "min_distance_mm": 0, "segregation_level": "group", "description": "同类气体可混装"},
        {"class_a": 2, "class_b": 3, "min_distance_mm": 1500, "segregation_level": "separated", "description": "气体与易燃液体分离1.5米"},
        {"class_a": 2, "class_b": 4, "min_distance_mm": 2000, "segregation_level": "separated", "description": "气体与易燃固体分离2米"},
        {"class_a": 2, "class_b": 5, "min_distance_mm": 3000, "segregation_level": "isolated", "description": "气体与氧化剂隔离3米"},
        {"class_a": 2, "class_b": 6, "min_distance_mm": 1500, "segregation_level": "separated", "description": "气体与毒害品分离1.5米"},

        {"class_a": 3, "class_b": 3, "min_distance_mm": 0, "segregation_level": "group", "description": "同类易燃液体可混装"},
        {"class_a": 3, "class_b": 4, "min_distance_mm": 2000, "segregation_level": "separated", "description": "易燃液体与易燃固体分离2米"},
        {"class_a": 3, "class_b": 5, "min_distance_mm": 3000, "segregation_level": "isolated", "description": "易燃液体与氧化剂隔离3米"},
        {"class_a": 3, "class_b": 6, "min_distance_mm": 1000, "segregation_level": "separated", "description": "易燃液体与毒害品分离1米"},

        {"class_a": 4, "class_b": 4, "min_distance_mm": 0, "segregation_level": "group", "description": "同类易燃固体可混装"},
        {"class_a": 4, "class_b": 5, "min_distance_mm": 3000, "segregation_level": "isolated", "description": "易燃固体与氧化剂隔离3米"},
        {"class_a": 4, "class_b": 6, "min_distance_mm": 1000, "segregation_level": "separated", "description": "易燃固体与毒害品分离1米"},

        {"class_a": 5, "class_b": 5, "min_distance_mm": 500, "segregation_level": "separated", "description": "氧化剂之间保持0.5米分离"},
        {"class_a": 5, "class_b": 6, "min_distance_mm": 2000, "segregation_level": "separated", "description": "氧化剂与毒害品分离2米"},

        {"class_a": 6, "class_b": 6, "min_distance_mm": 0, "segregation_level": "group", "description": "同类毒害品可混装"},
    ]
    for data in matrix_data:
        db.add(models.HazardSegregationMatrix(**data, is_active=True))
    db.commit()


def create_demo_hazard_cargos(db: Session):
    existing = db.query(models.Cargo).filter(models.Cargo.hazard_class.isnot(None)).all()
    if existing:
        return
    demo_cargos = [
        models.Cargo(
            name="烟花爆竹箱-Class1", length=600, width=400, height=400, weight=25,
            can_rotate_horizontal=True, can_flip=False, max_top_load=50, quantity=20,
            hazard_class=1, declared_name="烟花爆竹箱-Class1", declared_weight=25.0
        ),
        models.Cargo(
            name="丙烷气瓶-Class2", length=350, width=350, height=1000, weight=45,
            can_rotate_horizontal=False, can_flip=False, max_top_load=0, quantity=12,
            hazard_class=2, declared_name="丙烷气瓶-Class2", declared_weight=45.0
        ),
        models.Cargo(
            name="油漆桶-Class3", length=300, width=300, height=350, weight=20,
            can_rotate_horizontal=True, can_flip=False, max_top_load=40, quantity=30,
            hazard_class=3, declared_name="油漆桶-Class3", declared_weight=20.0
        ),
        models.Cargo(
            name="火柴箱-Class4", length=500, width=350, height=250, weight=15,
            can_rotate_horizontal=True, can_flip=True, max_top_load=30, quantity=25,
            hazard_class=4, declared_name="火柴箱-Class4", declared_weight=15.0
        ),
        models.Cargo(
            name="过氧化氢箱-Class5", length=450, width=350, height=300, weight=30,
            can_rotate_horizontal=True, can_flip=False, max_top_load=25, quantity=10,
            hazard_class=5, declared_name="过氧化氢箱-Class5", declared_weight=30.0
        ),
        models.Cargo(
            name="农药箱-Class6", length=400, width=300, height=350, weight=18,
            can_rotate_horizontal=True, can_flip=False, max_top_load=35, quantity=15,
            hazard_class=6, declared_name="农药箱-Class6", declared_weight=18.0
        ),
        models.Cargo(
            name="普通家电箱", length=800, width=600, height=500, weight=35,
            can_rotate_horizontal=True, can_flip=True, max_top_load=50, quantity=40,
            hazard_class=None, declared_name="普通家电箱", declared_weight=35.0
        ),
        models.Cargo(
            name="普通服装箱", length=600, width=400, height=300, weight=12,
            can_rotate_horizontal=True, can_flip=True, max_top_load=80, quantity=50,
            hazard_class=None, declared_name="普通服装箱", declared_weight=12.0
        ),
    ]
    db.add_all(demo_cargos)
    db.commit()


def init_plan_hash_and_version(db: Session):
    plans = db.query(models.PackingPlan).filter(
        (models.PackingPlan.content_hash == None) | (models.PackingPlan.version == None)
    ).all()
    for plan in plans:
        if plan.version is None:
            plan.version = 1
        if plan.content_hash is None:
            plan.content_hash = compute_plan_content_hash(db, plan.id)
    if plans:
        db.commit()


def create_demo_temperature_cargos(db: Session):
    existing = db.query(models.Cargo).filter(
        models.Cargo.temperature_class.in_(["FROZEN", "REFRIGERATED"])
    ).all()
    if existing:
        return
    demo_cargos = [
        models.Cargo(
            name="冷冻牛肉箱", length=600, width=400, height=300, weight=25,
            can_rotate_horizontal=True, can_flip=True, max_top_load=50, quantity=15,
            hazard_class=None, declared_name="冷冻牛肉箱", declared_weight=25.0,
            temperature_class="FROZEN"
        ),
        models.Cargo(
            name="冷冻海鲜箱", length=550, width=350, height=250, weight=18,
            can_rotate_horizontal=True, can_flip=True, max_top_load=40, quantity=12,
            hazard_class=None, declared_name="冷冻海鲜箱", declared_weight=18.0,
            temperature_class="FROZEN"
        ),
        models.Cargo(
            name="冷冻水饺箱", length=500, width=350, height=200, weight=12,
            can_rotate_horizontal=True, can_flip=True, max_top_load=60, quantity=20,
            hazard_class=None, declared_name="冷冻水饺箱", declared_weight=12.0,
            temperature_class="FROZEN"
        ),
        models.Cargo(
            name="冷藏鲜奶箱", length=450, width=300, height=350, weight=20,
            can_rotate_horizontal=True, can_flip=False, max_top_load=30, quantity=18,
            hazard_class=None, declared_name="冷藏鲜奶箱", declared_weight=20.0,
            temperature_class="REFRIGERATED"
        ),
        models.Cargo(
            name="冷藏水果箱", length=550, width=400, height=300, weight=15,
            can_rotate_horizontal=True, can_flip=False, max_top_load=25, quantity=16,
            hazard_class=None, declared_name="冷藏水果箱", declared_weight=15.0,
            temperature_class="REFRIGERATED"
        ),
        models.Cargo(
            name="冷藏蔬菜箱", length=500, width=350, height=280, weight=12,
            can_rotate_horizontal=True, can_flip=False, max_top_load=35, quantity=14,
            hazard_class=None, declared_name="冷藏蔬菜箱", declared_weight=12.0,
            temperature_class="REFRIGERATED"
        ),
        models.Cargo(
            name="冷藏药品箱", length=400, width=300, height=250, weight=10,
            can_rotate_horizontal=True, can_flip=False, max_top_load=20, quantity=10,
            hazard_class=None, declared_name="冷藏药品箱", declared_weight=10.0,
            temperature_class="REFRIGERATED"
        ),
        models.Cargo(
            name="常温家电箱", length=800, width=600, height=500, weight=35,
            can_rotate_horizontal=True, can_flip=True, max_top_load=50, quantity=8,
            hazard_class=None, declared_name="常温家电箱", declared_weight=35.0,
            temperature_class="AMBIENT"
        ),
        models.Cargo(
            name="常温服装箱", length=600, width=400, height=300, weight=12,
            can_rotate_horizontal=True, can_flip=True, max_top_load=80, quantity=25,
            hazard_class=None, declared_name="常温服装箱", declared_weight=12.0,
            temperature_class="AMBIENT"
        ),
        models.Cargo(
            name="常温日用品箱", length=500, width=350, height=300, weight=15,
            can_rotate_horizontal=True, can_flip=True, max_top_load=60, quantity=22,
            hazard_class=None, declared_name="常温日用品箱", declared_weight=15.0,
            temperature_class="AMBIENT"
        ),
        models.Cargo(
            name="常温零食箱", length=450, width=300, height=250, weight=10,
            can_rotate_horizontal=True, can_flip=True, max_top_load=70, quantity=30,
            hazard_class=None, declared_name="常温零食箱", declared_weight=10.0,
            temperature_class="AMBIENT"
        ),
        models.Cargo(
            name="常温图书箱", length=400, width=300, height=200, weight=18,
            can_rotate_horizontal=True, can_flip=True, max_top_load=100, quantity=20,
            hazard_class=None, declared_name="常温图书箱", declared_weight=18.0,
            temperature_class="AMBIENT"
        ),
    ]
    db.add_all(demo_cargos)
    db.commit()


def generate_stowage_report_no() -> str:
    return f"STOW-{uuid.uuid4().hex[:8].upper()}"


def create_stowage_report(db: Session, report_data: dict) -> models.StowageReport:
    db_report = models.StowageReport(**report_data)
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report


def get_stowage_report(db: Session, report_id: int = None, report_no: str = None):
    if report_id:
        return db.query(models.StowageReport).filter(models.StowageReport.id == report_id).first()
    if report_no:
        return db.query(models.StowageReport).filter(models.StowageReport.report_no == report_no).first()
    return None


def get_stowage_reports_by_plan(db: Session, plan_id: int):
    return db.query(models.StowageReport).filter(
        models.StowageReport.plan_id == plan_id
    ).order_by(models.StowageReport.created_at.desc()).all()


def list_stowage_reports(db: Session, skip: int = 0, limit: int = 100, plan_identifier: str = None):
    q = db.query(models.StowageReport)
    if plan_identifier:
        if plan_identifier.isdigit():
            q = q.filter(models.StowageReport.plan_id == int(plan_identifier))
        else:
            q = q.filter(models.StowageReport.plan_no == plan_identifier)
    return q.order_by(models.StowageReport.created_at.desc()).offset(skip).limit(limit).all()


def generate_review_task_no() -> str:
    return f"REV-{uuid.uuid4().hex[:8].upper()}"


def generate_confirmation_no() -> str:
    return f"CONF-{uuid.uuid4().hex[:8].upper()}"


def create_review_task(db: Session, plan_id: int, created_by: str = None, remarks: str = None) -> models.ReviewTask:
    plan = get_packing_plan(db, plan_id=plan_id)
    if not plan:
        return None

    content_hash = compute_plan_content_hash(db, plan_id)
    task_no = generate_review_task_no()

    db_task = models.ReviewTask(
        task_no=task_no,
        plan_id=plan_id,
        plan_no=plan.plan_no,
        plan_version=plan.version or 1,
        plan_content_hash=content_hash,
        status="pending",
        is_valid=True,
        created_by=created_by,
        remarks=remarks,
    )
    db.add(db_task)
    db.flush()

    packed_cargos = get_packed_cargos(db, plan_id=plan_id)
    for idx, pc in enumerate(packed_cargos):
        db_record = models.ReviewCargoRecord(
            task_id=db_task.id,
            plan_cargo_id=pc.id,
            cargo_id=pc.cargo_id,
            cargo_name=pc.cargo_name,
            review_status="pending",
            plan_x=pc.x,
            plan_y=pc.y,
            plan_z=pc.z,
            plan_orientation=pc.orientation,
            plan_load_order=idx + 1,
        )
        db.add(db_record)

    db.commit()
    db.refresh(db_task)
    return db_task


def get_review_task(db: Session, task_id: int = None, task_no: str = None):
    if task_id:
        return db.query(models.ReviewTask).filter(models.ReviewTask.id == task_id).first()
    if task_no:
        return db.query(models.ReviewTask).filter(models.ReviewTask.task_no == task_no).first()
    return None


def list_review_tasks(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    plan_no: str = None,
    status: str = None,
    only_pending: bool = False,
    only_valid: bool = True,
):
    q = db.query(models.ReviewTask)
    if plan_no:
        q = q.filter(models.ReviewTask.plan_no == plan_no)
    if status:
        q = q.filter(models.ReviewTask.status == status)
    if only_pending:
        q = q.filter(models.ReviewTask.status.in_(["pending", "in_progress"]))
    if only_valid:
        q = q.filter(models.ReviewTask.is_valid == True)
    return q.order_by(models.ReviewTask.created_at.desc()).offset(skip).limit(limit).all()


def get_review_tasks_by_plan(db: Session, plan_id: int):
    return db.query(models.ReviewTask).filter(
        models.ReviewTask.plan_id == plan_id
    ).order_by(models.ReviewTask.created_at.desc()).all()


def get_latest_review_task(db: Session, plan_id: int):
    return db.query(models.ReviewTask).filter(
        models.ReviewTask.plan_id == plan_id,
        models.ReviewTask.is_valid == True,
    ).order_by(models.ReviewTask.created_at.desc()).first()


def get_review_cargo_records(db: Session, task_id: int):
    return db.query(models.ReviewCargoRecord).filter(
        models.ReviewCargoRecord.task_id == task_id
    ).order_by(models.ReviewCargoRecord.id).all()


def get_review_cargo_record(db: Session, record_id: int):
    return db.query(models.ReviewCargoRecord).filter(
        models.ReviewCargoRecord.id == record_id
    ).first()


def _check_position_deviation(plan_x, plan_y, plan_z, actual_x, actual_y, actual_z, threshold_mm=50):
    if None in (plan_x, plan_y, plan_z, actual_x, actual_y, actual_z):
        return False, 0.0
    import math
    distance = math.sqrt(
        (plan_x - actual_x) ** 2 +
        (plan_y - actual_y) ** 2 +
        (plan_z - actual_z) ** 2
    )
    return distance > threshold_mm, distance


def _check_orientation_deviation(plan_orient, actual_orient):
    if not plan_orient or not actual_orient:
        return False
    return plan_orient != actual_orient


def _check_pressure_risk(db: Session, task_id: int, cargo_record: models.ReviewCargoRecord):
    if cargo_record.actual_z is None or cargo_record.review_status != "confirmed":
        return False, []

    plan_cargo = db.query(models.PackedCargo).filter(
        models.PackedCargo.id == cargo_record.plan_cargo_id
    ).first()
    if not plan_cargo:
        return False, []

    my_length = plan_cargo.length or 0
    my_width = plan_cargo.width or 0
    my_max_top_load = plan_cargo.max_top_load or 0
    my_weight = plan_cargo.weight or 0

    all_records = get_review_cargo_records(db, task_id)
    risks = []

    for other in all_records:
        if other.id == cargo_record.id or other.review_status != "confirmed":
            continue
        if other.actual_z is None or other.actual_x is None or other.actual_y is None:
            continue

        other_plan = db.query(models.PackedCargo).filter(
            models.PackedCargo.id == other.plan_cargo_id
        ).first()
        if not other_plan:
            continue

        other_length = other_plan.length or 0
        other_width = other_plan.width or 0
        other_max_top_load = other_plan.max_top_load or 0
        other_weight = other_plan.weight or 0

        x_overlap = not (cargo_record.actual_x + my_length <= other.actual_x or
                         other.actual_x + other_length <= cargo_record.actual_x)
        y_overlap = not (cargo_record.actual_y + my_width <= other.actual_y or
                         other.actual_y + other_width <= cargo_record.actual_y)

        if not (x_overlap and y_overlap):
            continue

        i_am_bottom = cargo_record.actual_z < other.actual_z
        i_am_top = other.actual_z < cargo_record.actual_z
        same_level = abs(cargo_record.actual_z - other.actual_z) < 10

        if i_am_bottom:
            if my_max_top_load > 0 and other_weight > my_max_top_load:
                risks.append({
                    "bottom_cargo_id": cargo_record.cargo_id,
                    "bottom_cargo_name": cargo_record.cargo_name,
                    "top_cargo_id": other.cargo_id,
                    "top_cargo_name": other.cargo_name,
                    "top_weight_kg": other_weight,
                    "max_top_load_kg": my_max_top_load,
                    "is_overload": True,
                    "actual_z_bottom": cargo_record.actual_z,
                    "actual_z_top": other.actual_z,
                })
            elif my_max_top_load <= 0 and other_weight > 0:
                risks.append({
                    "bottom_cargo_id": cargo_record.cargo_id,
                    "bottom_cargo_name": cargo_record.cargo_name,
                    "top_cargo_id": other.cargo_id,
                    "top_cargo_name": other.cargo_name,
                    "top_weight_kg": other_weight,
                    "max_top_load_kg": 0,
                    "is_overload": True,
                    "actual_z_bottom": cargo_record.actual_z,
                    "actual_z_top": other.actual_z,
                    "note": "底货未设置承压上限，上方有重物压叠",
                })

        if i_am_top:
            if other_max_top_load > 0 and my_weight > other_max_top_load:
                risks.append({
                    "bottom_cargo_id": other.cargo_id,
                    "bottom_cargo_name": other.cargo_name,
                    "top_cargo_id": cargo_record.cargo_id,
                    "top_cargo_name": cargo_record.cargo_name,
                    "top_weight_kg": my_weight,
                    "max_top_load_kg": other_max_top_load,
                    "is_overload": True,
                    "actual_z_bottom": other.actual_z,
                    "actual_z_top": cargo_record.actual_z,
                })
            elif other_max_top_load <= 0 and my_weight > 0:
                risks.append({
                    "bottom_cargo_id": other.cargo_id,
                    "bottom_cargo_name": other.cargo_name,
                    "top_cargo_id": cargo_record.cargo_id,
                    "top_cargo_name": cargo_record.cargo_name,
                    "top_weight_kg": my_weight,
                    "max_top_load_kg": 0,
                    "is_overload": True,
                    "actual_z_bottom": other.actual_z,
                    "actual_z_top": cargo_record.actual_z,
                    "note": "底货未设置承压上限，上方有重物压叠",
                })

    return len(risks) > 0, risks


def _check_temperature_violation(db: Session, task_id: int, cargo_record: models.ReviewCargoRecord):
    if cargo_record.review_status != "confirmed":
        return False, []

    plan_cargo = db.query(models.PackedCargo).filter(
        models.PackedCargo.id == cargo_record.plan_cargo_id
    ).first()
    if not plan_cargo:
        return False, []

    my_temp = (plan_cargo.temperature_class or "AMBIENT").upper()
    my_length = plan_cargo.length or 0
    my_width = plan_cargo.width or 0

    TEMP_PRIORITY = {"FROZEN": 3, "REFRIGERATED": 2, "AMBIENT": 1}
    my_priority = TEMP_PRIORITY.get(my_temp, 0)

    all_records = get_review_cargo_records(db, task_id)
    violations = []

    for other in all_records:
        if other.id == cargo_record.id or other.review_status != "confirmed":
            continue
        if other.actual_x is None or other.actual_y is None or other.actual_z is None:
            continue
        if cargo_record.actual_x is None or cargo_record.actual_y is None or cargo_record.actual_z is None:
            continue

        other_plan = db.query(models.PackedCargo).filter(
            models.PackedCargo.id == other.plan_cargo_id
        ).first()
        if not other_plan:
            continue

        other_temp = (other_plan.temperature_class or "AMBIENT").upper()
        other_priority = TEMP_PRIORITY.get(other_temp, 0)

        if my_temp == other_temp:
            continue

        x_overlap = not (cargo_record.actual_x + my_length <= other.actual_x or
                         other.actual_x + (other_plan.length or 0) <= cargo_record.actual_x)
        y_overlap = not (cargo_record.actual_y + my_width <= other.actual_y or
                         other.actual_y + (other_plan.width or 0) <= cargo_record.actual_y)
        z_close = abs(cargo_record.actual_z - other.actual_z) < max(plan_cargo.height or 0, other_plan.height or 0) + 100

        if x_overlap and y_overlap and z_close:
            high_temp_name = my_temp if my_priority < other_priority else other_temp
            low_temp_name = my_temp if my_priority > other_priority else other_temp
            violations.append({
                "cargo_id": cargo_record.cargo_id,
                "cargo_name": cargo_record.cargo_name,
                "cargo_temperature": my_temp,
                "other_cargo_id": other.cargo_id,
                "other_cargo_name": other.cargo_name,
                "other_temperature": other_temp,
                "high_temp_class": high_temp_name,
                "low_temp_class": low_temp_name,
                "issue": f"{high_temp_name}级货物与{low_temp_name}级货物空间重叠，可能导致温控隔离失效",
            })

    return len(violations) > 0, violations


def update_cargo_review_record(
    db: Session,
    task_id: int,
    record_data: dict,
    reviewed_by: str = None,
) -> models.ReviewCargoRecord:
    from datetime import datetime

    task = get_review_task(db, task_id=task_id)
    if not task or not task.is_valid:
        return None

    plan_cargo_id = record_data.get("plan_cargo_id")
    if plan_cargo_id:
        record = db.query(models.ReviewCargoRecord).filter(
            models.ReviewCargoRecord.task_id == task_id,
            models.ReviewCargoRecord.plan_cargo_id == plan_cargo_id,
        ).first()
    else:
        record = None

    if record is None and record_data.get("review_status") == "extra":
        record = models.ReviewCargoRecord(
            task_id=task_id,
            cargo_id=record_data["cargo_id"],
            cargo_name=record_data["cargo_name"],
            review_status="extra",
        )
        db.add(record)
        db.flush()

    if record is None:
        return None

    for field in ["actual_x", "actual_y", "actual_z", "actual_orientation", "actual_load_order", "remarks"]:
        if field in record_data and record_data[field] is not None:
            setattr(record, field, record_data[field])

    if "loaded_at" in record_data and record_data["loaded_at"]:
        record.loaded_at = datetime.fromisoformat(record_data["loaded_at"].replace('Z', '+00:00'))

    if "review_status" in record_data:
        record.review_status = record_data["review_status"]

    record.reviewed_by = reviewed_by or record_data.get("reviewed_by")
    record.reviewed_at = datetime.utcnow()

    if task.status == "pending":
        task.status = "in_progress"
        task.started_at = datetime.utcnow()

    db.query(models.ReviewDiscrepancy).filter(
        models.ReviewDiscrepancy.cargo_record_id == record.id
    ).delete()

    discrepancies = []

    if record.review_status == "missing":
        disc = models.ReviewDiscrepancy(
            task_id=task_id,
            cargo_record_id=record.id,
            discrepancy_type="missing",
            severity="blocking",
            description=f"货物 [{record.cargo_name}] 漏装",
            details={"cargo_id": record.cargo_id, "cargo_name": record.cargo_name},
        )
        discrepancies.append(disc)

    elif record.review_status == "extra":
        disc = models.ReviewDiscrepancy(
            task_id=task_id,
            cargo_record_id=record.id,
            discrepancy_type="extra",
            severity="blocking",
            description=f"发现多装货物 [{record.cargo_name}]",
            details={"cargo_id": record.cargo_id, "cargo_name": record.cargo_name},
        )
        discrepancies.append(disc)

    elif record.review_status == "confirmed":
        has_pos_dev, pos_distance = _check_position_deviation(
            record.plan_x, record.plan_y, record.plan_z,
            record.actual_x, record.actual_y, record.actual_z
        )
        if has_pos_dev:
            severity = "blocking" if pos_distance > 200 else "releasable"
            disc = models.ReviewDiscrepancy(
                task_id=task_id,
                cargo_record_id=record.id,
                discrepancy_type="position",
                severity=severity,
                description=f"货物 [{record.cargo_name}] 位置偏差 {pos_distance:.0f}mm",
                details={
                    "plan": {"x": record.plan_x, "y": record.plan_y, "z": record.plan_z},
                    "actual": {"x": record.actual_x, "y": record.actual_y, "z": record.actual_z},
                    "distance_mm": pos_distance,
                },
            )
            discrepancies.append(disc)

        has_orient_dev = _check_orientation_deviation(record.plan_orientation, record.actual_orientation)
        if has_orient_dev:
            disc = models.ReviewDiscrepancy(
                task_id=task_id,
                cargo_record_id=record.id,
                discrepancy_type="orientation",
                severity="releasable",
                description=f"货物 [{record.cargo_name}] 朝向不一致",
                details={
                    "plan_orientation": record.plan_orientation,
                    "actual_orientation": record.actual_orientation,
                },
            )
            discrepancies.append(disc)

        has_pressure, pressure_risks = _check_pressure_risk(db, task_id, record)
        if has_pressure:
            for risk in pressure_risks:
                disc = models.ReviewDiscrepancy(
                    task_id=task_id,
                    cargo_record_id=record.id,
                    discrepancy_type="pressure_risk",
                    severity="blocking",
                    description=f"承压风险: [{risk['top_cargo_name']}]({risk['top_weight_kg']}kg)压在[{risk['bottom_cargo_name']}]上方(承压上限{risk['max_top_load_kg']}kg)",
                    details=risk,
                )
                discrepancies.append(disc)

        has_temp_violation, temp_violations = _check_temperature_violation(db, task_id, record)
        if has_temp_violation:
            for violation in temp_violations:
                disc = models.ReviewDiscrepancy(
                    task_id=task_id,
                    cargo_record_id=record.id,
                    discrepancy_type="temperature_violation",
                    severity="blocking",
                    description=f"温控隔离失效: [{violation['cargo_name']}]({violation['cargo_temperature']})与[{violation['other_cargo_name']}]({violation['other_temperature']})空间重叠",
                    details=violation,
                )
                discrepancies.append(disc)

    for disc in discrepancies:
        db.add(disc)

    db.commit()
    db.refresh(record)
    return record


def get_review_discrepancies(db: Session, task_id: int, severity: str = None, only_unresolved: bool = False):
    q = db.query(models.ReviewDiscrepancy).filter(models.ReviewDiscrepancy.task_id == task_id)
    if severity:
        q = q.filter(models.ReviewDiscrepancy.severity == severity)
    if only_unresolved:
        q = q.filter(
            (models.ReviewDiscrepancy.is_resolved == False) &
            (models.ReviewDiscrepancy.is_waived == False)
        )
    return q.order_by(models.ReviewDiscrepancy.id).all()


def get_discrepancy(db: Session, disc_id: int):
    return db.query(models.ReviewDiscrepancy).filter(
        models.ReviewDiscrepancy.id == disc_id
    ).first()


def waive_discrepancy(db: Session, disc_id: int, waive_reason: str, waived_by: str = None):
    from datetime import datetime
    disc = get_discrepancy(db, disc_id)
    if not disc:
        return None
    if disc.severity == "blocking":
        raise ValueError("阻断类差异不允许直接放行")
    disc.is_waived = True
    disc.waived_by = waived_by
    disc.waived_at = datetime.utcnow()
    disc.waive_reason = waive_reason
    db.commit()
    db.refresh(disc)
    return disc


def resolve_discrepancy(db: Session, disc_id: int, resolution_note: str, resolved_by: str = None):
    from datetime import datetime
    disc = get_discrepancy(db, disc_id)
    if not disc:
        return None
    disc.is_resolved = True
    disc.resolved_by = resolved_by
    disc.resolved_at = datetime.utcnow()
    disc.resolution_note = resolution_note
    db.commit()
    db.refresh(disc)
    return disc


def get_review_task_stats(db: Session, task_id: int) -> dict:
    records = get_review_cargo_records(db, task_id)
    discrepancies = get_review_discrepancies(db, task_id)

    total = len(records)
    reviewed = sum(1 for r in records if r.review_status != "pending")
    disc_count = len(discrepancies)
    blocking_count = sum(1 for d in discrepancies if d.severity == "blocking" and not d.is_resolved and not d.is_waived)

    return {
        "total_cargos": total,
        "reviewed_count": reviewed,
        "discrepancy_count": disc_count,
        "blocking_count": blocking_count,
    }


def can_complete_review(db: Session, task_id: int) -> tuple:
    records = get_review_cargo_records(db, task_id)
    pending = [r for r in records if r.review_status == "pending"]
    if pending:
        return False, pending

    discrepancies = get_review_discrepancies(db, task_id, only_unresolved=True)
    blocking_unresolved = [d for d in discrepancies if d.severity == "blocking"]
    if blocking_unresolved:
        return False, blocking_unresolved

    return True, []


def complete_review_task(db: Session, task_id: int) -> models.ReviewTask:
    from datetime import datetime
    task = get_review_task(db, task_id=task_id)
    if not task or not task.is_valid:
        return None

    records = get_review_cargo_records(db, task_id)
    pending = [r for r in records if r.review_status == "pending"]
    if pending:
        raise ValueError(f"仍有 {len(pending)} 件货物未复核，无法完成复核")

    can_complete, blockers = can_complete_review(db, task_id)
    if not can_complete:
        blocking_discs = [b for b in blockers if hasattr(b, 'severity') and b.severity == 'blocking']
        if blocking_discs:
            raise ValueError(f"仍有 {len(blocking_discs)} 项阻断差异未处理，无法完成复核")
        raise ValueError(f"存在未处理项，无法完成复核")

    task.status = "completed"
    task.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(task)

    generate_loading_confirmation(db, task_id)
    return task


def generate_loading_confirmation(db: Session, task_id: int) -> models.LoadingConfirmation:
    from datetime import datetime
    task = get_review_task(db, task_id=task_id)
    if not task:
        return None

    records = get_review_cargo_records(db, task_id)
    discrepancies = get_review_discrepancies(db, task_id)

    planned_count = sum(1 for r in records if r.plan_cargo_id is not None)
    actual_count = sum(1 for r in records if r.review_status in ("confirmed", "extra"))
    blocking_count = sum(1 for d in discrepancies if d.severity == "blocking")
    releasable_count = sum(1 for d in discrepancies if d.severity == "releasable")

    has_blocking_unresolved = any(
        d.severity == "blocking" and not d.is_resolved and not d.is_waived
        for d in discrepancies
    )
    is_released = not has_blocking_unresolved

    summary = {
        "planned_count": planned_count,
        "actual_count": actual_count,
        "missing_count": sum(1 for r in records if r.review_status == "missing"),
        "extra_count": sum(1 for r in records if r.review_status == "extra"),
        "position_deviation_count": sum(1 for d in discrepancies if d.discrepancy_type == "position"),
        "orientation_deviation_count": sum(1 for d in discrepancies if d.discrepancy_type == "orientation"),
        "pressure_risk_count": sum(1 for d in discrepancies if d.discrepancy_type == "pressure_risk"),
        "temperature_violation_count": sum(1 for d in discrepancies if d.discrepancy_type == "temperature_violation"),
    }

    confirmation_no = generate_confirmation_no()
    db_conf = models.LoadingConfirmation(
        confirmation_no=confirmation_no,
        task_id=task_id,
        plan_id=task.plan_id,
        plan_no=task.plan_no,
        plan_version=task.plan_version,
        plan_content_hash=task.plan_content_hash,
        status="confirmed" if is_released else "draft",
        is_valid=True,
        total_planned=planned_count,
        total_actual=actual_count,
        total_discrepancies=len(discrepancies),
        blocking_count=blocking_count,
        releasable_count=releasable_count,
        is_released=is_released,
        released_by=task.created_by if is_released else None,
        released_at=datetime.utcnow() if is_released else None,
        release_reason="所有阻断差异已处理完毕，复核通过" if is_released else None,
        summary_data=summary,
        confirmed_at=datetime.utcnow() if is_released else None,
    )
    db.add(db_conf)
    db.commit()
    db.refresh(db_conf)
    return db_conf


def release_confirmation(db: Session, task_id: int, released_by: str, release_reason: str) -> models.LoadingConfirmation:
    from datetime import datetime
    task = get_review_task(db, task_id=task_id)
    if not task:
        return None

    can_complete, blocking = can_complete_review(db, task_id)
    if not can_complete:
        raise ValueError(f"仍有 {len(blocking)} 项阻断差异未处理，无法放行")

    conf = db.query(models.LoadingConfirmation).filter(
        models.LoadingConfirmation.task_id == task_id
    ).order_by(models.LoadingConfirmation.created_at.desc()).first()

    if not conf:
        conf = generate_loading_confirmation(db, task_id)

    conf.is_released = True
    conf.released_by = released_by
    conf.released_at = datetime.utcnow()
    conf.release_reason = release_reason
    conf.status = "confirmed"
    conf.confirmed_at = datetime.utcnow()

    if task.status != "completed":
        task.status = "completed"
        task.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(conf)
    return conf


def get_loading_confirmation(db: Session, conf_id: int = None, confirmation_no: str = None):
    if conf_id:
        return db.query(models.LoadingConfirmation).filter(models.LoadingConfirmation.id == conf_id).first()
    if confirmation_no:
        return db.query(models.LoadingConfirmation).filter(models.LoadingConfirmation.confirmation_no == confirmation_no).first()
    return None


def get_latest_confirmation_by_plan(db: Session, plan_id: int):
    return db.query(models.LoadingConfirmation).filter(
        models.LoadingConfirmation.plan_id == plan_id,
        models.LoadingConfirmation.is_valid == True,
    ).order_by(models.LoadingConfirmation.created_at.desc()).first()


def list_loading_confirmations(db: Session, skip: int = 0, limit: int = 100, plan_no: str = None):
    q = db.query(models.LoadingConfirmation)
    if plan_no:
        q = q.filter(models.LoadingConfirmation.plan_no == plan_no)
    return q.order_by(models.LoadingConfirmation.created_at.desc()).offset(skip).limit(limit).all()


def invalidate_reviews_for_outdated_plan(db: Session, plan_id: int, current_hash: str, current_version: int = None):
    plan = get_packing_plan(db, plan_id=plan_id)
    if plan is None:
        return

    eff_version = current_version if current_version is not None else plan.version

    tasks = db.query(models.ReviewTask).filter(
        models.ReviewTask.plan_id == plan_id,
        models.ReviewTask.is_valid == True,
    ).all()

    for task in tasks:
        hash_mismatch = bool(task.plan_content_hash) and task.plan_content_hash != current_hash
        version_outdated = (eff_version is not None) and task.plan_version < eff_version
        if hash_mismatch or version_outdated:
            task.is_valid = False
            reasons = []
            if hash_mismatch:
                reasons.append("内容哈希不一致")
            if version_outdated:
                reasons.append(f"方案版本从v{task.plan_version}升级到v{eff_version}")
            task.invalid_reason = f"原始装载方案已变更({'，'.join(reasons)})，复核结果自动失效"

            confirmations = db.query(models.LoadingConfirmation).filter(
                models.LoadingConfirmation.task_id == task.id,
                models.LoadingConfirmation.is_valid == True,
            ).all()
            for conf in confirmations:
                conf.is_valid = False
                conf.status = "void"

    db.commit()


def create_demo_review_record(db: Session):
    existing = db.query(models.ReviewTask).filter(
        models.ReviewTask.is_valid == True
    ).first()
    if existing:
        return

    plans = db.query(models.PackingPlan).all()
    if not plans:
        containers = db.query(models.Container).filter(models.Container.is_default == True).all()
        if not containers:
            create_default_containers(db)
            containers = db.query(models.Container).filter(models.Container.is_default == True).all()

        cargos = db.query(models.Cargo).limit(3).all()
        if len(cargos) < 3:
            create_demo_temperature_cargos(db)
            cargos = db.query(models.Cargo).limit(5).all()

        if containers and cargos:
            from app.packing.algorithm import pack_boxes, Box
            container = containers[0]
            boxes = []
            for cargo in cargos[:3]:
                raw_temp = getattr(cargo, 'temperature_class', 'AMBIENT') or 'AMBIENT'
                temp_class = raw_temp.value if hasattr(raw_temp, 'value') else raw_temp
                qty = min(cargo.quantity, 3)
                for i in range(qty):
                    boxes.append(Box(
                        cargo_id=cargo.id,
                        cargo_name=cargo.name,
                        length=cargo.length,
                        width=cargo.width,
                        height=cargo.height,
                        weight=cargo.weight,
                        can_rotate_horizontal=cargo.can_rotate_horizontal,
                        can_flip=cargo.can_flip,
                        max_top_load=cargo.max_top_load,
                        temperature_class=temp_class
                    ))

            result = pack_boxes(
                container_length=container.length,
                container_width=container.width,
                container_height=container.height,
                container_max_weight=container.max_weight,
                boxes=boxes
            )

            plan_data = {
                "container_id": container.id,
                "container_name": container.name,
                "total_cargos": len(boxes),
                "placed_count": len(result["placed_cargos"]),
                "unplaced_count": len(result["unplaced_cargos"]),
                "total_weight": result["total_weight"],
                "volume_utilization": result["volume_utilization"],
                "cog_x": result["center_of_gravity"]["x"],
                "cog_y": result["center_of_gravity"]["y"],
                "cog_z": result["center_of_gravity"]["z"],
                "cog_within_limit": result["cog_within_limit"],
                "cog_offset_x_ratio": result["cog_offset_x_ratio"],
                "cog_offset_y_ratio": result["cog_offset_y_ratio"],
                "score": 0.0,
                "rank": 0,
                "recommendation": "演示方案",
            }
            create_packing_plan(db, plan_data, result["placed_cargos"], result["unplaced_cargos"])
            plans = db.query(models.PackingPlan).all()

    if not plans:
        return

    plan = plans[0]
    packed_cargos = get_packed_cargos(db, plan_id=plan.id)
    if not packed_cargos:
        return

    from datetime import datetime, timedelta

    task = create_review_task(db, plan.id, created_by="demo_user", remarks="演示复核记录-轻微位置偏差已放行")
    if not task:
        return

    task.status = "in_progress"
    task.started_at = datetime.utcnow() - timedelta(hours=2)
    db.commit()

    records = get_review_cargo_records(db, task.id)
    for idx, record in enumerate(records):
        record.review_status = "confirmed"
        record.reviewed_by = "demo_reviewer"
        record.reviewed_at = datetime.utcnow() - timedelta(hours=1, minutes=30) + timedelta(minutes=idx * 5)
        record.loaded_at = datetime.utcnow() - timedelta(hours=3) + timedelta(minutes=idx * 8)
        record.actual_load_order = idx + 1

        if idx == 2:
            offset = 80
            record.actual_x = record.plan_x + offset
            record.actual_y = record.plan_y
            record.actual_z = record.plan_z
            record.actual_orientation = record.plan_orientation
            record.remarks = "现场操作时空间不足，轻微偏移"
        else:
            record.actual_x = record.plan_x
            record.actual_y = record.plan_y
            record.actual_z = record.plan_z
            record.actual_orientation = record.plan_orientation

    db.commit()

    for record in records:
        update_cargo_review_record(db, task.id, {
            "plan_cargo_id": record.plan_cargo_id,
            "cargo_id": record.cargo_id,
            "cargo_name": record.cargo_name,
            "actual_x": record.actual_x,
            "actual_y": record.actual_y,
            "actual_z": record.actual_z,
            "actual_orientation": record.actual_orientation,
            "actual_load_order": record.actual_load_order,
            "loaded_at": record.loaded_at.isoformat() if record.loaded_at else None,
            "review_status": "confirmed",
            "reviewed_by": "demo_reviewer",
            "remarks": record.remarks,
        }, reviewed_by="demo_reviewer")

    discrepancies = get_review_discrepancies(db, task.id)
    for disc in discrepancies:
        if disc.severity == "releasable":
            waive_discrepancy(
                db, disc.id,
                waive_reason="偏移量较小，不影响整体装载安全，现场确认可以接受",
                waived_by="demo_supervisor"
            )

    complete_review_task(db, task.id)
    db.refresh(task)


def generate_unloading_route_no() -> str:
    return f"ROUTE-{uuid.uuid4().hex[:8].upper()}"


def generate_simulation_no() -> str:
    return f"SIM-{uuid.uuid4().hex[:8].upper()}"


def get_unloading_route(db: Session, route_id: int = None, route_no: str = None):
    if route_id:
        return db.query(models.UnloadingRoute).filter(models.UnloadingRoute.id == route_id).first()
    if route_no:
        return db.query(models.UnloadingRoute).filter(models.UnloadingRoute.route_no == route_no).first()
    return None


def get_unloading_routes(db: Session, plan_id: int = None, skip: int = 0, limit: int = 100) -> list:
    q = db.query(models.UnloadingRoute)
    if plan_id:
        q = q.filter(models.UnloadingRoute.plan_id == plan_id)
    return q.order_by(models.UnloadingRoute.created_at.desc()).offset(skip).limit(limit).all()


def create_unloading_route(
    db: Session,
    plan_id: int,
    plan_no: str,
    name: str,
    description: str = None,
    created_by: str = None,
    stops: list = None,
    cargo_assignments: list = None
) -> models.UnloadingRoute:
    route_no = generate_unloading_route_no()
    db_route = models.UnloadingRoute(
        route_no=route_no,
        plan_id=plan_id,
        plan_no=plan_no,
        name=name,
        description=description,
        created_by=created_by
    )
    db.add(db_route)
    db.flush()

    stop_id_map = {}
    if stops:
        sorted_stops = sorted(stops, key=lambda s: s["stop_order"])
        for stop_data in sorted_stops:
            db_stop = models.UnloadingRouteStop(
                route_id=db_route.id,
                stop_order=stop_data["stop_order"],
                stop_name=stop_data["stop_name"],
                stop_code=stop_data.get("stop_code"),
                contact_person=stop_data.get("contact_person"),
                contact_phone=stop_data.get("contact_phone"),
                address=stop_data.get("address")
            )
            db.add(db_stop)
            db.flush()
            stop_id_map[stop_data["stop_order"]] = db_stop.id

    if cargo_assignments:
        for assignment_data in cargo_assignments:
            stop_order = assignment_data["stop_order"]
            stop_id = stop_id_map.get(stop_order)
            if stop_id is None:
                continue
            db_assignment = models.UnloadingCargoAssignment(
                route_id=db_route.id,
                packed_cargo_id=assignment_data["packed_cargo_id"],
                cargo_id=assignment_data["cargo_id"],
                cargo_name=assignment_data["cargo_name"],
                stop_id=stop_id,
                stop_order=stop_order,
                unload_order=assignment_data["unload_order"]
            )
            db.add(db_assignment)

    db.commit()
    db.refresh(db_route)
    return db_route


def update_unloading_route(
    db: Session,
    route_id: int,
    name: str = None,
    description: str = None,
    stops: list = None,
    cargo_assignments: list = None
) -> models.UnloadingRoute:
    route = get_unloading_route(db, route_id=route_id)
    if not route:
        return None

    if name is not None:
        route.name = name
    if description is not None:
        route.description = description
    route.updated_at = datetime.utcnow()

    if stops is not None:
        db.query(models.UnloadingRouteStop).filter(
            models.UnloadingRouteStop.route_id == route_id
        ).delete()

        stop_id_map = {}
        sorted_stops = sorted(stops, key=lambda s: s["stop_order"])
        for stop_data in sorted_stops:
            db_stop = models.UnloadingRouteStop(
                route_id=route_id,
                stop_order=stop_data["stop_order"],
                stop_name=stop_data["stop_name"],
                stop_code=stop_data.get("stop_code"),
                contact_person=stop_data.get("contact_person"),
                contact_phone=stop_data.get("contact_phone"),
                address=stop_data.get("address")
            )
            db.add(db_stop)
            db.flush()
            stop_id_map[stop_data["stop_order"]] = db_stop.id

        if cargo_assignments is not None:
            db.query(models.UnloadingCargoAssignment).filter(
                models.UnloadingCargoAssignment.route_id == route_id
            ).delete()

            for assignment_data in cargo_assignments:
                stop_order = assignment_data["stop_order"]
                stop_id = stop_id_map.get(stop_order)
                if stop_id is None:
                    continue
                db_assignment = models.UnloadingCargoAssignment(
                    route_id=route_id,
                    packed_cargo_id=assignment_data["packed_cargo_id"],
                    cargo_id=assignment_data["cargo_id"],
                    cargo_name=assignment_data["cargo_name"],
                    stop_id=stop_id,
                    stop_order=stop_order,
                    unload_order=assignment_data["unload_order"]
                )
                db.add(db_assignment)

    db.commit()
    db.refresh(route)
    return route


def delete_unloading_route(db: Session, route_id: int = None, route_no: str = None):
    route = get_unloading_route(db, route_id=route_id, route_no=route_no)
    if route:
        db.delete(route)
        db.commit()
    return route


def get_route_stops(db: Session, route_id: int) -> list:
    return db.query(models.UnloadingRouteStop).filter(
        models.UnloadingRouteStop.route_id == route_id
    ).order_by(models.UnloadingRouteStop.stop_order).all()


def get_route_cargo_assignments(db: Session, route_id: int) -> list:
    return db.query(models.UnloadingCargoAssignment).filter(
        models.UnloadingCargoAssignment.route_id == route_id
    ).all()


def get_unloading_simulation(db: Session, simulation_id: int = None, simulation_no: str = None):
    if simulation_id:
        return db.query(models.UnloadingSimulation).filter(models.UnloadingSimulation.id == simulation_id).first()
    if simulation_no:
        return db.query(models.UnloadingSimulation).filter(models.UnloadingSimulation.simulation_no == simulation_no).first()
    return None


def get_unloading_simulations(db: Session, route_id: int = None, skip: int = 0, limit: int = 100) -> list:
    q = db.query(models.UnloadingSimulation)
    if route_id:
        q = q.filter(models.UnloadingSimulation.route_id == route_id)
    return q.order_by(models.UnloadingSimulation.created_at.desc()).offset(skip).limit(limit).all()


def get_latest_simulation_by_route(db: Session, route_id: int):
    return db.query(models.UnloadingSimulation).filter(
        models.UnloadingSimulation.route_id == route_id
    ).order_by(models.UnloadingSimulation.created_at.desc()).first()


def get_simulation_stop_results(db: Session, simulation_id: int) -> list:
    return db.query(models.UnloadingStopResult).filter(
        models.UnloadingStopResult.simulation_id == simulation_id
    ).order_by(models.UnloadingStopResult.stop_order).all()


def create_unloading_simulation(
    db: Session,
    route: models.UnloadingRoute,
    simulation_result
) -> models.UnloadingSimulation:
    from app.unloading_simulation_engine import SimulationResult

    simulation_no = generate_simulation_no()

    fresh_stops = db.query(models.UnloadingRouteStop).filter(
        models.UnloadingRouteStop.route_id == route.id
    ).order_by(models.UnloadingRouteStop.stop_order).all()
    stop_order_to_id = {s.stop_order: s.id for s in fresh_stops}

    worst_stop_id = None
    if simulation_result.worst_stop_order is not None:
        worst_stop_id = stop_order_to_id.get(simulation_result.worst_stop_order)

    deadlock_stop_id = None
    if simulation_result.deadlock_stop_order is not None:
        deadlock_stop_id = stop_order_to_id.get(simulation_result.deadlock_stop_order)

    status = "deadlock" if simulation_result.has_deadlock else "completed"

    db_simulation = models.UnloadingSimulation(
        simulation_no=simulation_no,
        route_id=route.id,
        route_no=route.route_no,
        status=status,
        total_stops=simulation_result.total_stops,
        total_cargos=simulation_result.total_cargos,
        total_rehandle_count=simulation_result.total_rehandle_count,
        worst_stop_id=worst_stop_id,
        worst_stop_order=simulation_result.worst_stop_order,
        worst_stop_rehandle_count=simulation_result.worst_stop_rehandle_count,
        has_deadlock=simulation_result.has_deadlock,
        deadlock_stop_id=deadlock_stop_id,
        deadlock_stop_order=simulation_result.deadlock_stop_order,
        deadlock_cargo_ids=simulation_result.deadlock_cargo_ids,
        poorly_stacked_cargo_ids=simulation_result.poorly_stacked_cargo_ids,
        simulation_data={}
    )
    db.add(db_simulation)
    db.flush()

    for stop_result in simulation_result.stop_results:
        moves_data = []
        for move in stop_result.moves:
            moves_data.append({
                "move_type": move.move_type,
                "packed_cargo_id": move.packed_cargo_id,
                "cargo_id": move.cargo_id,
                "cargo_name": move.cargo_name,
                "stop_order": move.stop_order,
                "move_sequence": move.move_sequence,
                "reason": move.reason,
                "cargo_state_snapshot": move.cargo_state_snapshot
            })

        db_stop_result = models.UnloadingStopResult(
            simulation_id=db_simulation.id,
            stop_id=stop_order_to_id.get(stop_result.stop_order, stop_result.stop_id),
            stop_order=stop_result.stop_order,
            stop_name=stop_result.stop_name,
            rehandle_count=stop_result.rehandle_count,
            unload_count=stop_result.unload_count,
            remaining_count=stop_result.remaining_count,
            has_deadlock=stop_result.has_deadlock,
            deadlock_cargo_ids=stop_result.deadlock_cargo_ids,
            moves=moves_data,
            remaining_cargos_state=stop_result.remaining_cargos_state
        )
        db.add(db_stop_result)

    db.commit()
    db.refresh(db_simulation)
    return db_simulation


def create_demo_unloading_routes(db: Session):
    existing_routes = db.query(models.UnloadingRoute).all()
    if existing_routes:
        return

    plans = db.query(models.PackingPlan).all()
    if not plans:
        create_demo_review_record(db)
        plans = db.query(models.PackingPlan).all()

    if not plans:
        return

    plan = plans[0]
    packed_cargos = get_packed_cargos(db, plan_id=plan.id)
    if not packed_cargos or len(packed_cargos) < 3:
        return

    stops_data = [
        {"stop_order": 1, "stop_name": "北京配送中心", "stop_code": "BJ-001", "contact_person": "张经理", "contact_phone": "13800138001", "address": "北京市朝阳区建国路88号"},
        {"stop_order": 2, "stop_name": "天津分拨中心", "stop_code": "TJ-002", "contact_person": "李主管", "contact_phone": "13800138002", "address": "天津市滨海新区天津港"},
        {"stop_order": 3, "stop_name": "济南仓库", "stop_code": "JN-003", "contact_person": "王组长", "contact_phone": "13800138003", "address": "济南市历城区工业北路"},
    ]

    import math
    cargo_count = len(packed_cargos)
    assignments_data = []
    for idx, pc in enumerate(packed_cargos):
        stop_order = (idx % 3) + 1
        unload_order = (idx // 3) + 1
        assignments_data.append({
            "packed_cargo_id": pc.id,
            "cargo_id": pc.cargo_id,
            "cargo_name": pc.cargo_name,
            "stop_order": stop_order,
            "unload_order": unload_order
        })

    route1 = create_unloading_route(
        db,
        plan_id=plan.id,
        plan_no=plan.plan_no,
        name="华北配送路线-A线",
        description="北京-天津-济南常规配送路线，按城市顺序卸货",
        created_by="demo_user",
        stops=stops_data,
        cargo_assignments=assignments_data
    )

    stops_data2 = [
        {"stop_order": 1, "stop_name": "济南仓库", "stop_code": "JN-003", "contact_person": "王组长", "contact_phone": "13800138003", "address": "济南市历城区工业北路"},
        {"stop_order": 2, "stop_name": "天津分拨中心", "stop_code": "TJ-002", "contact_person": "李主管", "contact_phone": "13800138002", "address": "天津市滨海新区天津港"},
        {"stop_order": 3, "stop_name": "北京配送中心", "stop_code": "BJ-001", "contact_person": "张经理", "contact_phone": "13800138001", "address": "北京市朝阳区建国路88号"},
    ]

    assignments_data2 = []
    for idx, pc in enumerate(packed_cargos):
        stop_order = 3 - (idx % 3)
        unload_order = (idx // 3) + 1
        assignments_data2.append({
            "packed_cargo_id": pc.id,
            "cargo_id": pc.cargo_id,
            "cargo_name": pc.cargo_name,
            "stop_order": stop_order,
            "unload_order": unload_order
        })

    route2 = create_unloading_route(
        db,
        plan_id=plan.id,
        plan_no=plan.plan_no,
        name="华北配送路线-B线",
        description="济南-天津-北京反向配送路线，优化行驶里程",
        created_by="demo_user",
        stops=stops_data2,
        cargo_assignments=assignments_data2
    )

    from app.unloading_simulation_engine import run_unloading_simulation

    stops_list1 = []
    for s in route1.stops:
        stops_list1.append({
            "id": s.id,
            "stop_order": s.stop_order,
            "stop_name": s.stop_name,
            "stop_code": s.stop_code
        })

    assignments_list1 = []
    for a in route1.cargo_assignments:
        assignments_list1.append({
            "packed_cargo_id": a.packed_cargo_id,
            "stop_order": a.stop_order,
            "unload_order": a.unload_order
        })

    packed_cargos_list = []
    for pc in packed_cargos:
        packed_cargos_list.append({
            "id": pc.id,
            "cargo_id": pc.cargo_id,
            "cargo_name": pc.cargo_name,
            "x": pc.x,
            "y": pc.y,
            "z": pc.z,
            "length": pc.length,
            "width": pc.width,
            "height": pc.height,
            "weight": pc.weight
        })

    sim_result1 = run_unloading_simulation(packed_cargos_list, stops_list1, assignments_list1)
    create_unloading_simulation(db, route1, sim_result1)

    stops_list2 = []
    for s in route2.stops:
        stops_list2.append({
            "id": s.id,
            "stop_order": s.stop_order,
            "stop_name": s.stop_name,
            "stop_code": s.stop_code
        })

    assignments_list2 = []
    for a in route2.cargo_assignments:
        assignments_list2.append({
            "packed_cargo_id": a.packed_cargo_id,
            "stop_order": a.stop_order,
            "unload_order": a.unload_order
        })

    sim_result2 = run_unloading_simulation(packed_cargos_list, stops_list2, assignments_list2)
    create_unloading_simulation(db, route2, sim_result2)


def generate_draft_no() -> str:
    return f"CHG-{uuid.uuid4().hex[:8].upper()}"


def generate_analysis_no() -> str:
    return f"ANA-{uuid.uuid4().hex[:8].upper()}"


def generate_snapshot_no() -> str:
    return f"SNP-{uuid.uuid4().hex[:8].upper()}"


def _determine_change_type(proposed_changes: dict) -> str:
    change_types = set()
    if proposed_changes.get("cargo_changes"):
        change_types.add("cargo_info")
    if proposed_changes.get("site_changes"):
        change_types.add("site_assign")
    if proposed_changes.get("plan_meta_changes"):
        change_types.add("plan_meta")

    if len(change_types) == 0:
        return "plan_meta"
    elif len(change_types) == 1:
        return list(change_types)[0]
    else:
        return "mixed"


IMPACT_RULES = {
    "stowage_report": {
        "affected_by": ["cargo_info"],
        "fields": ["length", "width", "height", "weight", "max_top_load", "can_flip"],
        "decision_on_change": "rerun",
        "decision_on_other": "keep",
        "reason_rerun": "货物尺寸、重量或承压属性变更，堆码分析结果已失效，需重新生成",
        "reason_keep": "变更不涉及货物物理属性，堆码报告可继续沿用"
    },
    "compliance_audit": {
        "affected_by": ["cargo_info", "plan_meta"],
        "fields": ["hazard_class", "temperature_class", "declared_name", "declared_weight", "declared_weight"],
        "decision_on_change": "rerun",
        "decision_on_other": "keep",
        "reason_rerun": "危险品等级、温控等级或申报信息变更，合规校验结果已失效，需重新审核",
        "reason_keep": "变更不涉及合规校验相关字段，审核结果可继续沿用"
    },
    "review_task": {
        "affected_by": ["cargo_info", "site_assign", "plan_meta"],
        "fields": ["*"],
        "decision_on_change": "invalidate",
        "decision_on_other": "invalidate",
        "reason_rerun": "",
        "reason_invalidate": "方案已变更，现场装箱复核基于旧版本方案执行，复核结果自动失效",
        "reason_keep": ""
    },
    "unloading_route": {
        "affected_by": ["site_assign"],
        "fields": ["stop_order", "unload_order"],
        "decision_on_change": "rerun",
        "decision_on_other": "keep",
        "reason_rerun": "站点分配或卸货顺序变更，路线规划已失效，需重新规划",
        "reason_keep": "变更不涉及站点分配，路线规划可继续沿用"
    },
    "unloading_simulation": {
        "affected_by": ["cargo_info", "site_assign"],
        "fields": ["length", "width", "height", "weight", "stop_order", "unload_order"],
        "decision_on_change": "rerun",
        "decision_on_other": "keep",
        "reason_rerun": "货物属性或站点分配变更，卸货推演结果已失效，需重新推演",
        "reason_keep": "变更不涉及货物属性或站点分配，推演结果可继续沿用"
    },
    "trailer_load": {
        "affected_by": ["cargo_info"],
        "fields": ["length", "width", "weight", "cog_offset_x"],
        "decision_on_change": "rerun",
        "decision_on_other": "keep",
        "reason_rerun": "货物尺寸或重量变更，拖车配载和重心计算结果已失效，需重新计算",
        "reason_keep": "变更不涉及拖车配载相关字段，配载方案可继续沿用"
    },
    "customs_document": {
        "affected_by": ["cargo_info", "plan_meta"],
        "fields": ["declared_name", "declared_weight", "hazard_class", "container_no", "seal_no", "declared_weight"],
        "decision_on_change": "invalidate",
        "decision_on_other": "keep",
        "reason_invalidate": "申报信息、箱号或铅封号变更，海关单据内容已失效，需作废重开",
        "reason_keep": "变更不涉及海关申报相关字段，单据可继续沿用"
    }
}


def _analyze_single_result_impact(
    result_type: str,
    result_obj,
    proposed_changes: dict,
    plan_version: int
) -> dict:
    rules = IMPACT_RULES.get(result_type, {})
    if not rules:
        return {
            "impact_decision": "keep",
            "impact_reason": "未知结果类型，默认可沿用",
            "affected_fields": []
        }

    result_version = getattr(result_obj, "plan_version", None)
    if result_version is not None and result_version < plan_version:
        return {
            "impact_decision": rules["decision_on_change"],
            "impact_reason": f"该结果基于方案v{result_version}生成，当前已升级到v{plan_version}，" +
                            (rules.get("reason_rerun", "") or rules.get("reason_invalidate", "")),
            "affected_fields": ["version"]
        }

    change_types = set()
    affected_fields = []

    cargo_changes = proposed_changes.get("cargo_changes", [])
    if cargo_changes:
        change_types.add("cargo_info")
        for cc in cargo_changes:
            field_name = cc.get("field_name", "")
            if field_name in rules["fields"] or "*" in rules["fields"]:
                affected_fields.append(field_name)

    site_changes = proposed_changes.get("site_changes", [])
    if site_changes:
        change_types.add("site_assign")
        if "stop_order" in rules["fields"] or "*" in rules["fields"]:
            affected_fields.extend(["stop_order", "unload_order"])

    meta_changes = proposed_changes.get("plan_meta_changes", [])
    if meta_changes:
        change_types.add("plan_meta")
        for mc in meta_changes:
            field_name = mc.get("field_name", "")
            if field_name in rules["fields"] or "*" in rules["fields"]:
                affected_fields.append(field_name)

    has_impact = bool(change_types & set(rules["affected_by"])) and bool(affected_fields)

    if has_impact:
        if rules["decision_on_change"] == "rerun":
            reason = rules["reason_rerun"]
        elif rules["decision_on_change"] == "invalidate":
            reason = rules["reason_invalidate"]
        else:
            reason = rules["reason_keep"]
        return {
            "impact_decision": rules["decision_on_change"],
            "impact_reason": reason + f"。受影响字段: {', '.join(sorted(set(affected_fields)))}",
            "affected_fields": sorted(set(affected_fields))
        }
    else:
        return {
            "impact_decision": "keep",
            "impact_reason": rules["reason_keep"],
            "affected_fields": []
        }


def create_change_draft(
    db: Session,
    plan_id: int,
    change_type: str,
    change_description: str = None,
    proposed_changes: dict = None,
    created_by: str = None,
    remarks: str = None
) -> models.ChangeDraft:
    plan = get_packing_plan(db, plan_id=plan_id)
    if not plan:
        raise ValueError("方案不存在")

    draft_no = generate_draft_no()
    content_hash = compute_plan_content_hash(db, plan_id)

    db_draft = models.ChangeDraft(
        draft_no=draft_no,
        plan_id=plan_id,
        plan_no=plan.plan_no,
        base_version=plan.version or 1,
        base_content_hash=content_hash,
        status="draft",
        change_type=change_type,
        change_description=change_description,
        proposed_changes=proposed_changes or {},
        created_by=created_by,
        remarks=remarks
    )
    db.add(db_draft)
    db.commit()
    db.refresh(db_draft)
    return db_draft


def get_change_draft(db: Session, draft_id: int = None, draft_no: str = None):
    if draft_id:
        return db.query(models.ChangeDraft).filter(models.ChangeDraft.id == draft_id).first()
    if draft_no:
        return db.query(models.ChangeDraft).filter(models.ChangeDraft.draft_no == draft_no).first()
    return None


def list_change_drafts(
    db: Session,
    plan_identifier: str = None,
    status: str = None,
    skip: int = 0,
    limit: int = 100
):
    q = db.query(models.ChangeDraft)
    if plan_identifier:
        if plan_identifier.isdigit():
            q = q.filter(models.ChangeDraft.plan_id == int(plan_identifier))
        else:
            q = q.filter(models.ChangeDraft.plan_no == plan_identifier)
    if status:
        q = q.filter(models.ChangeDraft.status == status)
    return q.order_by(models.ChangeDraft.created_at.desc()).offset(skip).limit(limit).all()


def update_change_draft(
    db: Session,
    draft_id: int,
    update_data: dict
):
    draft = get_change_draft(db, draft_id=draft_id)
    if not draft:
        return None
    if draft.status != "draft":
        raise ValueError(f"草案状态为{draft.status}，不允许修改")

    if "proposed_changes" in update_data:
        update_data["change_type"] = _determine_change_type(update_data["proposed_changes"])

    for key, value in update_data.items():
        if hasattr(draft, key) and value is not None:
            setattr(draft, key, value)

    db.commit()
    db.refresh(draft)
    return draft


def cancel_change_draft(db: Session, draft_id: int):
    draft = get_change_draft(db, draft_id=draft_id)
    if not draft:
        return None
    if draft.status in ("applied", "cancelled"):
        raise ValueError(f"草案状态为{draft.status}，不允许取消")
    draft.status = "cancelled"
    db.commit()
    db.refresh(draft)
    return draft


def _collect_downstream_results(db: Session, plan_id: int, plan_version: int) -> list:
    results = []

    stowage_reports = db.query(models.StowageReport).filter(
        models.StowageReport.plan_id == plan_id
    ).all()
    for r in stowage_reports:
        results.append({
            "type": "stowage_report",
            "obj": r,
            "id": r.id,
            "no": r.report_no,
            "version": r.plan_version
        })

    audits = db.query(models.ComplianceAudit).filter(
        models.ComplianceAudit.plan_id == plan_id
    ).all()
    for r in audits:
        results.append({
            "type": "compliance_audit",
            "obj": r,
            "id": r.id,
            "no": r.audit_no,
            "version": r.plan_version
        })

    review_tasks = db.query(models.ReviewTask).filter(
        models.ReviewTask.plan_id == plan_id,
        models.ReviewTask.is_valid == True
    ).all()
    for r in review_tasks:
        results.append({
            "type": "review_task",
            "obj": r,
            "id": r.id,
            "no": r.task_no,
            "version": r.plan_version
        })

    routes = db.query(models.UnloadingRoute).filter(
        models.UnloadingRoute.plan_id == plan_id
    ).all()
    for r in routes:
        results.append({
            "type": "unloading_route",
            "obj": r,
            "id": r.id,
            "no": r.route_no,
            "version": plan_version
        })

    for route in routes:
        simulations = db.query(models.UnloadingSimulation).filter(
            models.UnloadingSimulation.route_id == route.id
        ).all()
        for s in simulations:
            results.append({
                "type": "unloading_simulation",
                "obj": s,
                "id": s.id,
                "no": s.simulation_no,
                "version": plan_version,
                "route_id": route.id
            })

    trailer_plans = db.query(models.TrailerLoadPlan).filter(
        models.TrailerLoadPlan.packing_plan_id == plan_id,
        models.TrailerLoadPlan.status == "valid"
    ).all()
    for r in trailer_plans:
        results.append({
            "type": "trailer_load",
            "obj": r,
            "id": r.id,
            "no": r.plan_no,
            "version": r.plan_version or plan_version
        })

    documents = db.query(models.CustomsDocument).filter(
        models.CustomsDocument.plan_id == plan_id,
        models.CustomsDocument.status == "valid"
    ).all()
    for r in documents:
        results.append({
            "type": "customs_document",
            "obj": r,
            "id": r.id,
            "no": r.document_no,
            "version": r.plan_version
        })

    return results


def _build_plan_snapshot_data(db: Session, plan_id: int) -> dict:
    plan = get_packing_plan(db, plan_id=plan_id)
    if not plan:
        return {}

    packed_cargos = get_packed_cargos(db, plan_id=plan_id)
    cargo_list = []
    for pc in packed_cargos:
        cargo_list.append({
            "packed_cargo_id": pc.id,
            "cargo_id": pc.cargo_id,
            "cargo_name": pc.cargo_name,
            "x": pc.x,
            "y": pc.y,
            "z": pc.z,
            "length": pc.length,
            "width": pc.width,
            "height": pc.height,
            "weight": pc.weight,
            "orientation": pc.orientation,
            "max_top_load": pc.max_top_load,
            "temperature_class": pc.temperature_class
        })

    return {
        "plan": {
            "id": plan.id,
            "plan_no": plan.plan_no,
            "version": plan.version,
            "container_id": plan.container_id,
            "container_name": plan.container_name,
            "container_no": plan.container_no,
            "seal_no": plan.seal_no,
            "declared_weight": plan.declared_weight,
            "total_cargos": plan.total_cargos,
            "placed_count": plan.placed_count,
            "total_weight": plan.total_weight,
            "volume_utilization": plan.volume_utilization,
            "cog_x": plan.cog_x,
            "cog_y": plan.cog_y,
            "cog_z": plan.cog_z,
            "content_hash": plan.content_hash
        },
        "packed_cargos": cargo_list
    }


def _calculate_field_diffs(before_data: dict, after_data: dict, proposed_changes: dict) -> tuple:
    field_diffs = []
    cargo_diffs = []

    plan_before = before_data.get("plan", {})
    plan_after = after_data.get("plan", {})

    meta_changes = proposed_changes.get("plan_meta_changes", [])
    for mc in meta_changes:
        field_name = mc["field_name"]
        field_diffs.append({
            "field_name": field_name,
            "old_value": mc["old_value"],
            "new_value": mc["new_value"],
            "change_type": "plan_meta"
        })

    cargo_changes = proposed_changes.get("cargo_changes", [])
    cargo_change_map = {}
    for cc in cargo_changes:
        cargo_id = cc["cargo_id"]
        if cargo_id not in cargo_change_map:
            cargo_change_map[cargo_id] = []
        cargo_change_map[cargo_id].append(cc)

    cargos_before = {c["packed_cargo_id"]: c for c in before_data.get("packed_cargos", [])}
    cargos_after = {c["packed_cargo_id"]: c for c in after_data.get("packed_cargos", [])}

    for cargo_id, changes in cargo_change_map.items():
        cargo_name = ""
        field_diffs_for_cargo = []
        for pc in cargos_before.values():
            if pc["cargo_id"] == cargo_id:
                cargo_name = pc["cargo_name"]
                break

        for cc in changes:
            field_diffs_for_cargo.append({
                "field_name": cc["field_name"],
                "old_value": cc["old_value"],
                "new_value": cc["new_value"],
                "change_type": "cargo_info"
            })

        if field_diffs_for_cargo:
            cargo_diffs.append({
                "cargo_id": cargo_id,
                "cargo_name": cargo_name,
                "field_diffs": field_diffs_for_cargo
            })

    site_changes = proposed_changes.get("site_changes", [])
    if site_changes:
        field_diffs.append({
            "field_name": "site_assignment",
            "old_value": f"{len(site_changes)}条站点分配记录",
            "new_value": f"{len(site_changes)}条站点分配记录已更新",
            "change_type": "site_assign"
        })

    return field_diffs, cargo_diffs


def run_impact_analysis(db: Session, draft_id: int) -> models.ChangeImpactAnalysis:
    from datetime import datetime

    draft = get_change_draft(db, draft_id=draft_id)
    if not draft:
        raise ValueError("变更草案不存在")
    if draft.status not in ("draft", "analyzed"):
        raise ValueError(f"草案状态为{draft.status}，不允许执行分析")

    plan = get_packing_plan(db, plan_id=draft.plan_id)
    if not plan:
        raise ValueError("关联方案不存在")

    current_version = plan.version or 1
    new_version = current_version + 1

    if draft.base_version != current_version:
        raise ValueError(
            f"草案基于方案v{draft.base_version}创建，但当前方案已升级到v{current_version}，"
            "请基于最新版本重新创建变更草案"
        )

    current_hash = compute_plan_content_hash(db, plan.id)
    if draft.base_content_hash != current_hash:
        raise ValueError(
            "方案内容已被其他操作修改，请基于最新版本重新创建变更草案"
        )

    draft.status = "analyzing"
    db.commit()

    proposed_changes = draft.proposed_changes or {}
    downstream_results = _collect_downstream_results(db, plan.id, current_version)

    analysis_no = generate_analysis_no()
    db_analysis = models.ChangeImpactAnalysis(
        analysis_no=analysis_no,
        draft_id=draft.id,
        plan_id=plan.id,
        plan_no=plan.plan_no,
        base_version=current_version,
        new_version=new_version,
        total_affected_count=0,
        need_rerun_count=0,
        can_keep_count=0,
        must_invalidate_count=0
    )
    db.add(db_analysis)
    db.flush()

    impact_items = []
    need_rerun = 0
    can_keep = 0
    must_invalidate = 0

    for result in downstream_results:
        analysis_result = _analyze_single_result_impact(
            result["type"],
            result["obj"],
            proposed_changes,
            current_version
        )

        decision = analysis_result["impact_decision"]
        if decision == "rerun":
            need_rerun += 1
        elif decision == "invalidate":
            must_invalidate += 1
        else:
            can_keep += 1

        db_item = models.ChangeImpactItem(
            analysis_id=db_analysis.id,
            result_type=result["type"],
            result_id=result["id"],
            result_no=result["no"],
            result_version=result["version"],
            impact_decision=decision,
            impact_reason=analysis_result["impact_reason"],
            affected_fields=analysis_result["affected_fields"]
        )
        impact_items.append(db_item)
        db.add(db_item)

    total_affected = need_rerun + must_invalidate

    db_analysis.total_affected_count = total_affected
    db_analysis.need_rerun_count = need_rerun
    db_analysis.can_keep_count = can_keep
    db_analysis.must_invalidate_count = must_invalidate

    summary_parts = []
    if total_affected == 0:
        summary_parts.append("本次变更不影响任何下游结果，所有历史结果均可继续沿用。")
    else:
        if can_keep > 0:
            summary_parts.append(f"{can_keep}项结果可继续沿用")
        if need_rerun > 0:
            summary_parts.append(f"{need_rerun}项结果需要重新生成")
        if must_invalidate > 0:
            summary_parts.append(f"{must_invalidate}项结果需要直接失效")
    db_analysis.analysis_summary = "；".join(summary_parts)

    before_data = _build_plan_snapshot_data(db, plan.id)

    after_data = json.loads(json.dumps(before_data))
    cargo_changes = proposed_changes.get("cargo_changes", [])
    for cc in cargo_changes:
        for pc in after_data["packed_cargos"]:
            if pc["cargo_id"] == cc["cargo_id"]:
                field_name = cc["field_name"]
                if field_name in pc:
                    pc[field_name] = cc["new_value"]

    meta_changes = proposed_changes.get("plan_meta_changes", [])
    for mc in meta_changes:
        field_name = mc["field_name"]
        if field_name in after_data["plan"]:
            after_data["plan"][field_name] = mc["new_value"]

    after_data["plan"]["version"] = new_version

    field_diffs, cargo_diffs = _calculate_field_diffs(before_data, after_data, proposed_changes)

    snapshot_no = generate_snapshot_no()
    db_snapshot = models.ChangeDiffSnapshot(
        snapshot_no=snapshot_no,
        analysis_id=db_analysis.id,
        plan_id=plan.id,
        plan_no=plan.plan_no,
        base_version=current_version,
        new_version=new_version,
        before_data=before_data,
        after_data=after_data,
        field_diffs=field_diffs,
        cargo_diffs=cargo_diffs
    )
    db.add(db_snapshot)

    draft.status = "analyzed"
    draft.analyzed_at = datetime.utcnow()

    db.commit()
    db.refresh(db_analysis)
    db.refresh(draft)

    return db_analysis


def apply_change(db: Session, draft_id: int, applied_by: str = None, remarks: str = None) -> models.PackingPlan:
    from datetime import datetime

    draft = get_change_draft(db, draft_id=draft_id)
    if not draft:
        raise ValueError("变更草案不存在")
    if draft.status != "analyzed":
        raise ValueError(f"草案状态为{draft.status}，请先执行影响分析")

    plan = get_packing_plan(db, plan_id=draft.plan_id)
    if not plan:
        raise ValueError("关联方案不存在")

    current_version = plan.version or 1
    if draft.base_version != current_version:
        raise ValueError(
            f"草案基于方案v{draft.base_version}创建，但当前方案已升级到v{current_version}，"
            "请基于最新版本重新创建变更草案"
        )

    analysis = db.query(models.ChangeImpactAnalysis).filter(
        models.ChangeImpactAnalysis.draft_id == draft.id
    ).first()
    if not analysis:
        raise ValueError("未找到影响分析结果，请先执行影响分析")

    proposed_changes = draft.proposed_changes or {}

    cargo_changes = proposed_changes.get("cargo_changes", [])
    for cc in cargo_changes:
        cargo_id = cc["cargo_id"]
        field_name = cc["field_name"]
        new_value = cc["new_value"]

        packed_cargos = db.query(models.PackedCargo).filter(
            models.PackedCargo.plan_id == plan.id,
            models.PackedCargo.cargo_id == cargo_id
        ).all()
        for pc in packed_cargos:
            if hasattr(pc, field_name):
                setattr(pc, field_name, new_value)

        cargo = get_cargo(db, cargo_id=cargo_id)
        if cargo and hasattr(cargo, field_name):
            setattr(cargo, field_name, new_value)

    meta_changes = proposed_changes.get("plan_meta_changes", [])
    for mc in meta_changes:
        field_name = mc["field_name"]
        new_value = mc["new_value"]
        if hasattr(plan, field_name):
            setattr(plan, field_name, new_value)

    site_changes = proposed_changes.get("site_changes", [])
    if site_changes:
        routes = db.query(models.UnloadingRoute).filter(
            models.UnloadingRoute.plan_id == plan.id
        ).all()
        for route in routes:
            for sc in site_changes:
                packed_cargo_id = sc.get("packed_cargo_id") or sc.get("cargo_id")
                new_site_order = sc.get("new_stop_order") or sc.get("new_site_order") or sc.get("site_order")
                new_unload_sequence = sc.get("new_unload_order") or sc.get("unload_sequence")
                new_site_code = sc.get("new_site_code") or sc.get("site_code")

                assignments = db.query(models.UnloadingCargoAssignment).filter(
                    models.UnloadingCargoAssignment.route_id == route.id,
                    (models.UnloadingCargoAssignment.packed_cargo_id == packed_cargo_id) |
                    (models.UnloadingCargoAssignment.cargo_id == packed_cargo_id)
                ).all()
                for assign in assignments:
                    if new_site_order is not None:
                        assign.stop_order = new_site_order
                    if new_unload_sequence is not None:
                        assign.unload_order = new_unload_sequence

                packed_cargos = db.query(models.PackedCargo).filter(
                    models.PackedCargo.plan_id == plan.id,
                    (models.PackedCargo.id == packed_cargo_id) |
                    (models.PackedCargo.cargo_id == packed_cargo_id)
                ).all()
                for pc in packed_cargos:
                    if new_site_order is not None:
                        pc.site_order = new_site_order
                    if new_unload_sequence is not None:
                        pc.unload_sequence = new_unload_sequence
                    if new_site_code is not None:
                        pc.site_code = new_site_code

    bump_plan_version(db, plan.id)
    db.refresh(plan)

    impact_items = db.query(models.ChangeImpactItem).filter(
        models.ChangeImpactItem.analysis_id == analysis.id
    ).all()

    for item in impact_items:
        decision = item.impact_decision
        result_type = item.result_type
        result_id = item.result_id
        version_change_note = f"方案变更(v{current_version}→v{plan.version})：{item.impact_reason}"

        if decision == "invalidate":
            if result_type == "review_task":
                task = db.query(models.ReviewTask).filter(
                    models.ReviewTask.id == result_id
                ).first()
                if task:
                    task.is_valid = False
                    task.invalid_reason = version_change_note

                confirmations = db.query(models.LoadingConfirmation).filter(
                    models.LoadingConfirmation.task_id == result_id
                ).all()
                for conf in confirmations:
                    conf.is_valid = False
                    conf.status = "void"

            elif result_type == "customs_document":
                doc = db.query(models.CustomsDocument).filter(
                    models.CustomsDocument.id == result_id
                ).first()
                if doc:
                    doc.status = "outdated"
                    doc.void_reason = version_change_note
                    doc.voided_at = datetime.utcnow()

            elif result_type == "stowage_report":
                report = db.query(models.StowageReport).filter(
                    models.StowageReport.id == result_id
                ).first()
                if report:
                    report.status = "void"
                    report.void_reason = version_change_note

            elif result_type == "compliance_audit":
                audit = db.query(models.ComplianceAudit).filter(
                    models.ComplianceAudit.id == result_id
                ).first()
                if audit:
                    audit.status = "void"
                    audit.void_reason = version_change_note

            elif result_type == "trailer_load":
                trailer = db.query(models.TrailerLoadPlan).filter(
                    models.TrailerLoadPlan.id == result_id
                ).first()
                if trailer:
                    trailer.status = "void"

        elif decision == "rerun":
            if result_type == "compliance_audit":
                audit = db.query(models.ComplianceAudit).filter(
                    models.ComplianceAudit.id == result_id
                ).first()
                if audit:
                    audit.status = "outdated"
                    audit.void_reason = version_change_note

            elif result_type == "stowage_report":
                report = db.query(models.StowageReport).filter(
                    models.StowageReport.id == result_id
                ).first()
                if report:
                    report.status = "outdated"
                    report.void_reason = version_change_note

            elif result_type == "unloading_route":
                route = db.query(models.UnloadingRoute).filter(
                    models.UnloadingRoute.id == result_id
                ).first()
                if route and hasattr(route, 'status'):
                    route.status = "outdated"
                simulations = db.query(models.UnloadingSimulation).filter(
                    models.UnloadingSimulation.route_id == result_id
                ).all()
                for sim in simulations:
                    if hasattr(sim, 'status'):
                        sim.status = "outdated"

            elif result_type == "trailer_load":
                trailer = db.query(models.TrailerLoadPlan).filter(
                    models.TrailerLoadPlan.id == result_id
                ).first()
                if trailer:
                    trailer.status = "outdated"

            elif result_type == "customs_document":
                doc = db.query(models.CustomsDocument).filter(
                    models.CustomsDocument.id == result_id
                ).first()
                if doc:
                    doc.status = "outdated"
                    doc.void_reason = version_change_note
                    doc.voided_at = datetime.utcnow()

    draft.status = "applied"
    draft.applied_at = datetime.utcnow()
    draft.applied_by = applied_by
    if remarks:
        draft.remarks = (draft.remarks or "") + f"\n应用备注: {remarks}"

    db.commit()
    db.refresh(plan)
    db.refresh(draft)

    return plan


def get_impact_analysis(db: Session, analysis_id: int = None, analysis_no: str = None):
    if analysis_id:
        return db.query(models.ChangeImpactAnalysis).filter(
            models.ChangeImpactAnalysis.id == analysis_id
        ).first()
    if analysis_no:
        return db.query(models.ChangeImpactAnalysis).filter(
            models.ChangeImpactAnalysis.analysis_no == analysis_no
        ).first()
    return None


def get_impact_analyses_by_plan(db: Session, plan_identifier: str, skip: int = 0, limit: int = 100):
    q = db.query(models.ChangeImpactAnalysis)
    if plan_identifier.isdigit():
        q = q.filter(models.ChangeImpactAnalysis.plan_id == int(plan_identifier))
    else:
        q = q.filter(models.ChangeImpactAnalysis.plan_no == plan_identifier)
    return q.order_by(models.ChangeImpactAnalysis.created_at.desc()).offset(skip).limit(limit).all()


def get_impact_items_by_analysis(db: Session, analysis_id: int):
    return db.query(models.ChangeImpactItem).filter(
        models.ChangeImpactItem.analysis_id == analysis_id
    ).all()


def get_diff_snapshot(db: Session, snapshot_id: int = None, snapshot_no: str = None):
    if snapshot_id:
        return db.query(models.ChangeDiffSnapshot).filter(
            models.ChangeDiffSnapshot.id == snapshot_id
        ).first()
    if snapshot_no:
        return db.query(models.ChangeDiffSnapshot).filter(
            models.ChangeDiffSnapshot.snapshot_no == snapshot_no
        ).first()
    return None


def get_change_history(db: Session, plan_identifier: str, skip: int = 0, limit: int = 100):
    drafts = list_change_drafts(db, plan_identifier=plan_identifier, skip=skip, limit=limit)
    result = []
    for draft in drafts:
        item = {
            "draft_id": draft.id,
            "draft_no": draft.draft_no,
            "plan_id": draft.plan_id,
            "plan_no": draft.plan_no,
            "base_version": draft.base_version,
            "change_type": draft.change_type,
            "change_description": draft.change_description,
            "status": draft.status,
            "created_by": draft.created_by,
            "created_at": draft.created_at.isoformat() if draft.created_at else None,
            "analyzed_at": draft.analyzed_at.isoformat() if draft.analyzed_at else None,
            "applied_at": draft.applied_at.isoformat() if draft.applied_at else None,
            "applied_by": draft.applied_by,
            "remarks": draft.remarks,
            "impact_analysis": None
        }

        if draft.status in ("analyzed", "applied"):
            analysis = db.query(models.ChangeImpactAnalysis).filter(
                models.ChangeImpactAnalysis.draft_id == draft.id
            ).first()
            if analysis:
                item["analysis_no"] = analysis.analysis_no
                item["new_version"] = analysis.new_version
                item["impact_analysis"] = {
                    "analysis_id": analysis.id,
                    "analysis_no": analysis.analysis_no,
                    "new_version": analysis.new_version,
                    "total_affected_count": analysis.total_affected_count,
                    "need_rerun_count": analysis.need_rerun_count,
                    "can_keep_count": analysis.can_keep_count,
                    "must_invalidate_count": analysis.must_invalidate_count,
                    "analysis_summary": analysis.analysis_summary
                }

        result.append(item)
    return result


def generate_publication_no() -> str:
    return f"PUB-{uuid.uuid4().hex[:8].upper()}"


def generate_dispatch_no() -> str:
    return f"DISP-{uuid.uuid4().hex[:8].upper()}"


def run_gate_check(db: Session, plan_id: int) -> dict:
    plan = get_packing_plan(db, plan_id=plan_id)
    if not plan:
        return {"can_publish": False, "checks": [{"check_name": "方案存在性", "passed": False, "detail": "方案不存在"}], "summary": "方案不存在"}

    checks = []
    current_hash = compute_plan_content_hash(db, plan_id)

    latest_audit = get_latest_passed_audit(db, plan_id)
    if latest_audit and latest_audit.status == "valid" and latest_audit.plan_content_hash == current_hash:
        checks.append({"check_name": "合规审核通过", "passed": True, "detail": f"审核编号 {latest_audit.audit_no}，已通过且为当前版本"})
    else:
        reasons = []
        if not latest_audit:
            reasons.append("无通过的审核记录")
        else:
            if latest_audit.status != "valid":
                reasons.append(f"审核状态为 {latest_audit.status}")
            if latest_audit.plan_content_hash != current_hash:
                reasons.append("审核基于旧版本方案")
            if not latest_audit.is_passed:
                reasons.append("审核未通过")
        checks.append({"check_name": "合规审核通过", "passed": False, "detail": "；".join(reasons)})

    latest_review = get_latest_review_task(db, plan_id)
    latest_confirmation = get_latest_confirmation_by_plan(db, plan_id)
    if latest_review and latest_review.is_valid and latest_review.status == "completed" and latest_confirmation and latest_confirmation.is_valid and latest_confirmation.is_released:
        disc_unresolved = get_review_discrepancies(db, latest_review.id, severity="blocking", only_unresolved=True)
        if disc_unresolved:
            checks.append({"check_name": "装箱复核放行", "passed": False, "detail": f"仍有 {len(disc_unresolved)} 项阻断差异未处理"})
        else:
            checks.append({"check_name": "装箱复核放行", "passed": True, "detail": f"确认单 {latest_confirmation.confirmation_no} 已放行"})
    else:
        reasons = []
        if not latest_review or not latest_review.is_valid:
            reasons.append("无有效的复核任务")
        elif latest_review.status != "completed":
            reasons.append(f"复核状态为 {latest_review.status}")
        if not latest_confirmation or not latest_confirmation.is_valid:
            reasons.append("无有效的确认单")
        elif not latest_confirmation.is_released:
            reasons.append("确认单未放行")
        checks.append({"check_name": "装箱复核放行", "passed": False, "detail": "；".join(reasons)})

    routes = db.query(models.UnloadingRoute).filter(models.UnloadingRoute.plan_id == plan_id).all()
    if not routes:
        checks.append({"check_name": "路线推演", "passed": True, "detail": "无关联路线，跳过检查"})
    else:
        route_ok = True
        route_details = []
        for route in routes:
            latest_sim = get_latest_simulation_by_route(db, route.id)
            if not latest_sim:
                route_ok = False
                route_details.append(f"路线 {route.route_no} 无推演结果")
            elif latest_sim.has_deadlock:
                route_ok = False
                route_details.append(f"路线 {route.route_no} 推演存在死局")
        if route_ok:
            checks.append({"check_name": "路线推演", "passed": True, "detail": f"共 {len(routes)} 条路线推演有效"})
        else:
            checks.append({"check_name": "路线推演", "passed": False, "detail": "；".join(route_details)})

    trailer_plans = db.query(models.TrailerLoadPlan).filter(
        models.TrailerLoadPlan.packing_plan_id == plan_id,
        models.TrailerLoadPlan.status == "valid"
    ).all()
    if not trailer_plans:
        checks.append({"check_name": "拖车装载", "passed": True, "detail": "无关联拖车方案，跳过检查"})
    else:
        trailer_ok = True
        trailer_details = []
        for tp in trailer_plans:
            if tp.plan_content_hash and tp.plan_content_hash != current_hash:
                trailer_ok = False
                trailer_details.append(f"拖车方案 {tp.plan_no} 基于旧版本")
            if tp.plan_version and tp.plan_version < (plan.version or 1):
                trailer_ok = False
                trailer_details.append(f"拖车方案 {tp.plan_no} 版本过期(v{tp.plan_version})")
        if trailer_ok:
            checks.append({"check_name": "拖车装载", "passed": True, "detail": f"共 {len(trailer_plans)} 个拖车方案为当前版本"})
        else:
            checks.append({"check_name": "拖车装载", "passed": False, "detail": "；".join(trailer_details)})

    docs = db.query(models.CustomsDocument).filter(
        models.CustomsDocument.plan_id == plan_id,
        models.CustomsDocument.status == "valid"
    ).all()
    if not docs:
        checks.append({"check_name": "海关单据", "passed": True, "detail": "无有效单据，跳过检查"})
    else:
        doc_ok = True
        doc_details = []
        for doc in docs:
            if doc.plan_content_hash and doc.plan_content_hash != current_hash:
                doc_ok = False
                doc_details.append(f"单据 {doc.document_no} 基于旧版本")
            if doc.plan_version and doc.plan_version < (plan.version or 1):
                doc_ok = False
                doc_details.append(f"单据 {doc.document_no} 版本过期(v{doc.plan_version})")
        if doc_ok:
            checks.append({"check_name": "海关单据", "passed": True, "detail": f"共 {len(docs)} 份单据为当前版本"})
        else:
            checks.append({"check_name": "海关单据", "passed": False, "detail": "；".join(doc_details)})

    can_publish = all(c["passed"] for c in checks)
    failed_checks = [c["check_name"] for c in checks if not c["passed"]]
    summary = "所有闸口检查通过，允许发布" if can_publish else f"以下检查未通过: {', '.join(failed_checks)}"

    return {"can_publish": can_publish, "checks": checks, "summary": summary}


def create_publication(
    db: Session,
    plan_id: int,
    route_id: int = None,
    simulation_id: int = None,
    trailer_plan_id: int = None,
    published_by: str = None
) -> models.PublicationRecord:
    plan = get_packing_plan(db, plan_id=plan_id)
    if not plan:
        raise ValueError("方案不存在")

    current_hash = compute_plan_content_hash(db, plan_id)
    gate_result = run_gate_check(db, plan_id)
    if not gate_result["can_publish"]:
        raise ValueError(f"闸口检查未通过: {gate_result['summary']}")

    publication_no = generate_publication_no()

    latest_audit = get_latest_passed_audit(db, plan_id)
    latest_confirmation = get_latest_confirmation_by_plan(db, plan_id)

    route_obj = None
    simulation_obj = None
    if route_id:
        route_obj = get_unloading_route(db, route_id=route_id)
        if not route_obj:
            raise ValueError(f"路线 {route_id} 不存在")
        if route_obj.plan_id != plan_id:
            raise ValueError(f"路线 {route_id} 不属于当前方案，串单风险")
    else:
        routes = db.query(models.UnloadingRoute).filter(models.UnloadingRoute.plan_id == plan_id).all()
        if routes:
            route_obj = routes[0]

    if simulation_id:
        simulation_obj = get_unloading_simulation(db, simulation_id=simulation_id)
        if not simulation_obj:
            raise ValueError(f"路线推演 {simulation_id} 不存在")
        route_of_sim = None
        if simulation_obj.route_id:
            route_of_sim = get_unloading_route(db, route_id=simulation_obj.route_id)
        if not route_of_sim or route_of_sim.plan_id != plan_id:
            raise ValueError(f"路线推演 {simulation_id} 不属于当前方案，串单风险")
    elif route_obj:
        simulation_obj = get_latest_simulation_by_route(db, route_obj.id)

    trailer_obj = None
    if trailer_plan_id:
        trailer_obj = get_trailer_load_plan(db, plan_id=plan_id, trailer_plan_id=trailer_plan_id)
        if not trailer_obj:
            raise ValueError(f"拖车装载方案 {trailer_plan_id} 不存在或不属于当前方案，串单风险")
    else:
        trailer_plans = db.query(models.TrailerLoadPlan).filter(
            models.TrailerLoadPlan.packing_plan_id == plan_id,
            models.TrailerLoadPlan.status == "valid"
        ).all()
        if trailer_plans:
            trailer_obj = trailer_plans[0]

    documents = db.query(models.CustomsDocument).filter(
        models.CustomsDocument.plan_id == plan_id,
        models.CustomsDocument.status == "valid"
    ).all()
    doc_snapshot = []
    for doc in documents:
        doc_snapshot.append({
            "document_id": doc.id,
            "document_no": doc.document_no,
            "document_type": doc.document_type,
            "plan_version": doc.plan_version,
            "status": doc.status,
            "container_no": doc.container_no,
            "seal_no": doc.seal_no,
            "total_packages": doc.total_packages,
            "total_weight_kg": doc.total_weight_kg,
        })

    snapshot = {
        "plan": {
            "id": plan.id, "plan_no": plan.plan_no, "version": plan.version,
            "content_hash": current_hash, "container_no": plan.container_no,
            "seal_no": plan.seal_no, "declared_weight": plan.declared_weight,
            "container_name": plan.container_name, "total_weight": plan.total_weight,
            "volume_utilization": plan.volume_utilization,
        },
        "audit": {
            "id": latest_audit.id if latest_audit else None,
            "audit_no": latest_audit.audit_no if latest_audit else None,
            "is_passed": latest_audit.is_passed if latest_audit else None,
            "plan_version": latest_audit.plan_version if latest_audit else None,
            "plan_content_hash": latest_audit.plan_content_hash if latest_audit else None,
        } if latest_audit else None,
        "confirmation": {
            "id": latest_confirmation.id if latest_confirmation else None,
            "confirmation_no": latest_confirmation.confirmation_no if latest_confirmation else None,
            "is_released": latest_confirmation.is_released if latest_confirmation else None,
            "plan_version": latest_confirmation.plan_version if latest_confirmation else None,
        } if latest_confirmation else None,
        "route": {
            "id": route_obj.id, "route_no": route_obj.route_no, "name": route_obj.name,
        } if route_obj else None,
        "simulation": {
            "id": simulation_obj.id, "simulation_no": simulation_obj.simulation_no,
            "total_rehandle_count": simulation_obj.total_rehandle_count,
            "has_deadlock": simulation_obj.has_deadlock,
        } if simulation_obj else None,
        "trailer": {
            "id": trailer_obj.id, "plan_no": trailer_obj.plan_no,
            "total_weight": trailer_obj.total_weight,
            "axles_within_limit": trailer_obj.axles_within_limit,
        } if trailer_obj else None,
        "documents": doc_snapshot,
        "gate_check": gate_result,
    }

    db_pub = models.PublicationRecord(
        publication_no=publication_no,
        plan_id=plan_id,
        plan_no=plan.plan_no,
        plan_version=plan.version or 1,
        plan_content_hash=current_hash,
        container_no=plan.container_no,
        seal_no=plan.seal_no,
        audit_id=latest_audit.id if latest_audit else None,
        audit_no=latest_audit.audit_no if latest_audit else None,
        audit_passed=latest_audit.is_passed if latest_audit else False,
        confirmation_id=latest_confirmation.id if latest_confirmation else None,
        confirmation_no=latest_confirmation.confirmation_no if latest_confirmation else None,
        confirmation_released=latest_confirmation.is_released if latest_confirmation else False,
        route_id=route_obj.id if route_obj else None,
        route_no=route_obj.route_no if route_obj else None,
        simulation_id=simulation_obj.id if simulation_obj else None,
        simulation_no=simulation_obj.simulation_no if simulation_obj else None,
        trailer_plan_id=trailer_obj.id if trailer_obj else None,
        trailer_plan_no=trailer_obj.plan_no if trailer_obj else None,
        document_snapshot=doc_snapshot,
        snapshot_data=snapshot,
        status="pending_approval",
        published_by=published_by,
        gate_check_result=gate_result,
    )
    db.add(db_pub)
    db.commit()
    db.refresh(db_pub)
    return db_pub


def get_publication(db: Session, pub_id: int = None, publication_no: str = None):
    if pub_id:
        return db.query(models.PublicationRecord).filter(models.PublicationRecord.id == pub_id).first()
    if publication_no:
        return db.query(models.PublicationRecord).filter(models.PublicationRecord.publication_no == publication_no).first()
    return None


def list_publications(db: Session, plan_id: int = None, status: str = None, skip: int = 0, limit: int = 100):
    q = db.query(models.PublicationRecord)
    if plan_id:
        q = q.filter(models.PublicationRecord.plan_id == plan_id)
    if status:
        q = q.filter(models.PublicationRecord.status == status)
    return q.order_by(models.PublicationRecord.published_at.desc()).offset(skip).limit(limit).all()


def approve_publication(db: Session, pub_id: int, approved_by: str) -> models.PublicationRecord:
    from datetime import datetime
    pub = get_publication(db, pub_id=pub_id)
    if not pub:
        raise ValueError("发布记录不存在")
    if pub.status != "pending_approval":
        raise ValueError(f"当前状态为 {pub.status}，不允许审批")

    plan = get_packing_plan(db, plan_id=pub.plan_id)
    if not plan:
        raise ValueError("关联方案已不存在，无法审批")

    current_hash = compute_plan_content_hash(db, pub.plan_id)
    current_version = plan.version or 1

    if current_version != pub.plan_version:
        raise ValueError(
            f"方案版本已变更(冻结:v{pub.plan_version} → 当前:v{current_version})，请重新走闸口发布"
        )
    if current_hash != pub.plan_content_hash:
        raise ValueError(
            "方案内容哈希已变化(冻结与当前不一致)，说明发布后方案被改动，请重新走闸口发布"
        )

    gate_result = run_gate_check(db, pub.plan_id)
    if not gate_result["can_publish"]:
        checks_summary = "; ".join(
            f"[{c.get('name')}]{c.get('message','')}" for c in gate_result.get("checks", []) if not c.get("passed")
        )
        raise ValueError(f"审批前重跑闸口未通过: {gate_result['summary']} 详情: {checks_summary}")

    if pub.route_id:
        r = get_unloading_route(db, route_id=pub.route_id)
        if (not r) or r.plan_id != pub.plan_id or r.status == "invalid":
            raise ValueError(f"冻结的路线 {pub.route_id} 已失效/不属于本方案，请重新发布")
    if pub.simulation_id:
        s = get_unloading_simulation(db, simulation_id=pub.simulation_id)
        if not s:
            raise ValueError(f"冻结的路线推演 {pub.simulation_id} 已不存在，请重新发布")
        sim_route = get_unloading_route(db, route_id=s.route_id) if s.route_id else None
        if (not sim_route) or sim_route.plan_id != pub.plan_id:
            raise ValueError(f"冻结的路线推演 {pub.simulation_id} 不属于本方案，请重新发布")
    if pub.trailer_plan_id:
        t = get_trailer_load_plan(db, trailer_plan_id=pub.trailer_plan_id)
        if (not t) or t.packing_plan_id != pub.plan_id or t.status == "invalid":
            raise ValueError(f"冻结的拖车装载方案 {pub.trailer_plan_id} 已失效/不属于本方案，请重新发布")

    pub.status = "approved"
    pub.approved_by = approved_by
    pub.approved_at = datetime.utcnow()
    pub.gate_check_result = gate_result

    snapshot = pub.snapshot_data or {}
    if isinstance(snapshot, dict):
        snapshot["gate_check_at_approve"] = gate_result
        snapshot["approved_plan_snapshot"] = {
            "version": current_version,
            "content_hash": current_hash,
        }
        pub.snapshot_data = snapshot

    dispatch_no = generate_dispatch_no()
    db_dispatch = models.DispatchTask(
        task_no=dispatch_no,
        plan_id=pub.plan_id,
        plan_no=pub.plan_no,
        publication_id=pub.id,
        frozen_version=pub.plan_version,
        frozen_content_hash=pub.plan_content_hash,
        frozen_snapshot=pub.snapshot_data,
        status="pending_dispatch",
        block_reasons=[],
        created_by=approved_by,
    )
    db.add(db_dispatch)
    db.commit()
    db.refresh(pub)
    db.refresh(db_dispatch)
    return pub


def reject_publication(db: Session, pub_id: int, rejected_reason: str) -> models.PublicationRecord:
    from datetime import datetime
    pub = get_publication(db, pub_id=pub_id)
    if not pub:
        raise ValueError("发布记录不存在")
    if pub.status != "pending_approval":
        raise ValueError(f"当前状态为 {pub.status}，不允许驳回")

    pub.status = "rejected"
    pub.rejected_reason = rejected_reason
    db.commit()
    db.refresh(pub)
    return pub


def get_dispatch_task(db: Session, task_id: int = None, task_no: str = None):
    if task_id:
        return db.query(models.DispatchTask).filter(models.DispatchTask.id == task_id).first()
    if task_no:
        return db.query(models.DispatchTask).filter(models.DispatchTask.task_no == task_no).first()
    return None


def list_dispatch_tasks(db: Session, plan_no: str = None, status: str = None, skip: int = 0, limit: int = 100):
    q = db.query(models.DispatchTask)
    if plan_no:
        q = q.filter(models.DispatchTask.plan_no == plan_no)
    if status:
        if status == "actionable":
            q = q.filter(models.DispatchTask.status.in_(["pending_dispatch", "pending_re_review"]))
        else:
            q = q.filter(models.DispatchTask.status == status)
    return q.order_by(models.DispatchTask.created_at.desc()).offset(skip).limit(limit).all()


def update_dispatch_task(db: Session, task_id: int, update_data: dict) -> models.DispatchTask:
    from datetime import datetime
    task = get_dispatch_task(db, task_id=task_id)
    if not task:
        return None
    allowed_fields = ["vehicle_no", "driver_name", "terminal_window"]
    for field in allowed_fields:
        if field in update_data and update_data[field] is not None:
            setattr(task, field, update_data[field])
    if "planned_departure_time" in update_data and update_data["planned_departure_time"]:
        task.planned_departure_time = datetime.fromisoformat(update_data["planned_departure_time"].replace('Z', '+00:00'))
    if "arrival_time" in update_data and update_data["arrival_time"]:
        task.arrival_time = datetime.fromisoformat(update_data["arrival_time"].replace('Z', '+00:00'))
    db.commit()
    db.refresh(task)
    return task


def transition_dispatch_status(db: Session, task_id: int, target_status: str, reason: str = None) -> models.DispatchTask:
    from datetime import datetime
    task = get_dispatch_task(db, task_id=task_id)
    if not task:
        raise ValueError("发运任务不存在")

    valid_transitions = {
        "pending_approval": ["pending_dispatch", "cancelled"],
        "pending_dispatch": ["loading", "cancelled"],
        "loading": ["dispatched", "cancelled"],
        "dispatched": [],
        "cancelled": [],
        "pending_re_review": ["pending_dispatch", "cancelled"],
    }
    allowed = valid_transitions.get(task.status, [])
    if target_status not in allowed:
        raise ValueError(f"当前状态 {task.status} 不允许转到 {target_status}，允许的目标: {allowed}")

    if target_status == "pending_dispatch" and task.status == "pending_re_review":
        validation = validate_dispatch_dependencies(db, task_id)
        if not validation["is_valid"]:
            raise ValueError(f"依赖校验未通过，不允许转为待出车: {validation['summary']}")

    task.status = target_status
    task.status_changed_at = datetime.utcnow()
    if target_status == "pending_dispatch":
        task.block_reasons = []
    db.commit()
    db.refresh(task)
    return task


def validate_dispatch_dependencies(db: Session, task_id: int) -> dict:
    from datetime import datetime
    task = get_dispatch_task(db, task_id=task_id)
    if not task:
        return {"is_valid": False, "block_reasons": [{"type": "not_found", "detail": "发运任务不存在"}], "summary": "任务不存在"}

    plan = get_packing_plan(db, plan_id=task.plan_id)
    block_reasons = []

    if not plan:
        block_reasons.append({"type": "version_change", "detail": "关联方案不存在"})
    else:
        current_hash = compute_plan_content_hash(db, task.plan_id)
        if plan.version != task.frozen_version:
            block_reasons.append({
                "type": "version_change",
                "detail": f"方案版本已从v{task.frozen_version}变更为v{plan.version}"
            })
        if current_hash != task.frozen_content_hash:
            block_reasons.append({
                "type": "version_change",
                "detail": "方案内容哈希已变更，装载方案被修改"
            })

    if task.publication_id:
        pub = get_publication(db, pub_id=task.publication_id)
        if pub and pub.audit_id:
            audit = get_compliance_audit(db, audit_id=pub.audit_id)
            if not audit or audit.status != "valid":
                block_reasons.append({"type": "audit_invalidated", "detail": f"审核 {pub.audit_no} 已失效(状态: {audit.status if audit else '不存在'})"})
            elif audit.plan_content_hash != (current_hash if plan else ""):
                block_reasons.append({"type": "audit_invalidated", "detail": f"审核 {pub.audit_no} 基于旧版本方案"})

    if task.publication_id:
        pub = get_publication(db, pub_id=task.publication_id)
        if pub and pub.confirmation_id:
            conf = get_loading_confirmation(db, conf_id=pub.confirmation_id)
            if not conf or not conf.is_valid:
                block_reasons.append({"type": "review_not_released", "detail": f"确认单 {pub.confirmation_no} 已失效"})
            elif not conf.is_released:
                block_reasons.append({"type": "review_not_released", "detail": f"确认单 {pub.confirmation_no} 未放行"})

    if task.publication_id:
        pub = get_publication(db, pub_id=task.publication_id)
        if pub and pub.route_id:
            latest_sim = get_latest_simulation_by_route(db, pub.route_id)
            if latest_sim and latest_sim.has_deadlock:
                block_reasons.append({"type": "route_outdated", "detail": f"路线 {pub.route_no} 最新推演存在死局"})

    if task.publication_id:
        pub = get_publication(db, pub_id=task.publication_id)
        if pub and pub.trailer_plan_id:
            tp = get_trailer_load_plan(db, plan_id=pub.trailer_plan_id)
            if tp and tp.status != "valid":
                block_reasons.append({"type": "trailer_outdated", "detail": f"拖车方案 {pub.trailer_plan_no} 已失效(状态: {tp.status})"})
            elif tp and tp.plan_content_hash and plan and tp.plan_content_hash != current_hash:
                block_reasons.append({"type": "trailer_outdated", "detail": f"拖车方案 {pub.trailer_plan_no} 基于旧版本方案"})

    if task.publication_id:
        pub = get_publication(db, pub_id=task.publication_id)
        if pub and pub.document_snapshot:
            for doc_snap in pub.document_snapshot:
                doc = get_customs_document(db, doc_id=doc_snap.get("document_id"))
                if doc and doc.status != "valid":
                    block_reasons.append({"type": "document_outdated", "detail": f"单据 {doc_snap['document_no']} 已失效(状态: {doc.status})"})

    is_valid = len(block_reasons) == 0
    summary = "所有依赖有效" if is_valid else f"发现 {len(block_reasons)} 项阻断: " + "；".join(b["detail"] for b in block_reasons)

    task.block_reasons = block_reasons
    task.last_validated_at = datetime.utcnow()

    if not is_valid and task.status in ("pending_dispatch", "pending_approval"):
        task.status = "pending_re_review"
        task.status_changed_at = datetime.utcnow()

    db.commit()
    db.refresh(task)

    return {"is_valid": is_valid, "block_reasons": block_reasons, "summary": summary}


def validate_all_active_dispatches(db: Session):
    active_tasks = db.query(models.DispatchTask).filter(
        models.DispatchTask.status.in_(["pending_approval", "pending_dispatch", "loading"])
    ).all()
    results = []
    for task in active_tasks:
        validation = validate_dispatch_dependencies(db, task.id)
        results.append({
            "task_id": task.id,
            "task_no": task.task_no,
            "plan_no": task.plan_no,
            "is_valid": validation["is_valid"],
            "block_reasons": validation["block_reasons"],
            "new_status": task.status,
        })
    return results


def generate_batch_no() -> str:
    return f"BATCH-{uuid.uuid4().hex[:8].upper()}"


def _snapshot_dispatch_task(db: Session, dispatch_task: models.DispatchTask) -> dict:
    plan = get_packing_plan(db, plan_id=dispatch_task.plan_id)
    snapshot = {
        "task_no": dispatch_task.task_no,
        "plan_no": dispatch_task.plan_no,
        "plan_id": dispatch_task.plan_id,
        "frozen_version": dispatch_task.frozen_version,
        "frozen_content_hash": dispatch_task.frozen_content_hash,
        "vehicle_no": dispatch_task.vehicle_no,
        "planned_departure_time": dispatch_task.planned_departure_time.isoformat() if dispatch_task.planned_departure_time else None,
        "status": dispatch_task.status,
    }
    if plan:
        snapshot["container_no"] = plan.container_no
        snapshot["seal_no"] = plan.seal_no
    if dispatch_task.frozen_snapshot:
        snapshot["frozen_snapshot"] = dispatch_task.frozen_snapshot
    return snapshot


def _validate_batch_direction(db: Session, dispatch_task_ids: List[int], transport_direction: str) -> List[str]:
    errors = []
    for dt_id in dispatch_task_ids:
        dt = get_dispatch_task(db, task_id=dt_id)
        if not dt:
            errors.append(f"发运任务ID {dt_id} 不存在")
            continue
        if dt.status not in ("pending_dispatch",):
            errors.append(f"发运任务 {dt.task_no} 状态为 {dt.status}，非待出车状态")
    return errors


def _validate_batch_time_window(db: Session, batch_id: int, dispatch_task_ids: List[int]) -> List[str]:
    errors = []
    existing_items = db.query(models.BatchTaskItem).filter(
        models.BatchTaskItem.batch_id == batch_id,
        models.BatchTaskItem.removed_at == None,
    ).all()
    existing_ids = {item.dispatch_task_id for item in existing_items}
    all_ids = existing_ids | set(dispatch_task_ids)

    tasks = []
    for dt_id in all_ids:
        dt = get_dispatch_task(db, task_id=dt_id)
        if dt and dt.planned_departure_time:
            tasks.append({"id": dt.id, "task_no": dt.task_no, "time": dt.planned_departure_time})

    if len(tasks) >= 2:
        for i in range(len(tasks)):
            for j in range(i + 1, len(tasks)):
                if tasks[i]["time"] == tasks[j]["time"]:
                    errors.append(f"发运任务 {tasks[i]['task_no']} 和 {tasks[j]['task_no']} 计划发车时间完全相同，时间窗冲突")
    return errors


def _validate_vehicle_not_double_booked(db: Session, batch_id: int, dispatch_task_ids: List[int], tractor_no: str = None, trailer_no: str = None) -> List[str]:
    errors = []
    vehicles_to_check = []
    if tractor_no:
        vehicles_to_check.append(("tractor_no", tractor_no))
    if trailer_no:
        vehicles_to_check.append(("trailer_no", trailer_no))

    for field, value in vehicles_to_check:
        conflict_batch = db.query(models.BatchShipment).filter(
            models.BatchShipment.id != batch_id,
            getattr(models.BatchShipment, field) == value,
            models.BatchShipment.status.in_(["pending_grouping", "grouping", "pending_departure"]),
        ).first()
        if conflict_batch:
            label = "主车" if field == "tractor_no" else "挂车"
            errors.append(f"{label} {value} 已被批次 {conflict_batch.batch_no} 占用")

    existing_items = db.query(models.BatchTaskItem).filter(
        models.BatchTaskItem.dispatch_task_id.in_(dispatch_task_ids),
        models.BatchTaskItem.removed_at == None,
        models.BatchTaskItem.batch_id != batch_id,
    ).all()
    for item in existing_items:
        conflict_batch = db.query(models.BatchShipment).filter(models.BatchShipment.id == item.batch_id).first()
        if conflict_batch and conflict_batch.status in ("pending_grouping", "grouping", "pending_departure"):
            errors.append(f"发运任务 {item.dispatch_task_no} 已在批次 {conflict_batch.batch_no} 中")
    return errors


def create_batch_shipment(db: Session, batch_data: dict, task_items_data: List[dict]) -> models.BatchShipment:
    batch_no = generate_batch_no()
    from datetime import datetime as _dt

    planned_departure = None
    if batch_data.get("planned_departure_time"):
        pdt_str = batch_data["planned_departure_time"]
        if isinstance(pdt_str, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
                try:
                    planned_departure = _dt.strptime(pdt_str, fmt)
                    break
                except ValueError:
                    continue

    db_batch = models.BatchShipment(
        batch_no=batch_no,
        transport_direction=batch_data["transport_direction"],
        fleet_name=batch_data.get("fleet_name"),
        fleet_contact=batch_data.get("fleet_contact"),
        fleet_phone=batch_data.get("fleet_phone"),
        tractor_no=batch_data.get("tractor_no"),
        trailer_no=batch_data.get("trailer_no"),
        planned_departure_time=planned_departure,
        assembly_location=batch_data.get("assembly_location"),
        status="pending_grouping",
        total_containers=0,
        total_weight=0.0,
        created_by=batch_data.get("created_by"),
    )
    db.add(db_batch)
    db.flush()

    total_containers = 0
    total_weight = 0.0

    for item_data in task_items_data:
        dt_id = item_data["dispatch_task_id"]
        dt = get_dispatch_task(db, task_id=dt_id)
        if not dt:
            continue

        plan = get_packing_plan(db, plan_id=dt.plan_id)
        snapshot = _snapshot_dispatch_task(db, dt)

        container_no = plan.container_no if plan else None
        seal_no = plan.seal_no if plan else None
        route_no = None
        if dt.frozen_snapshot:
            route_no = dt.frozen_snapshot.get("route_no")

        db_item = models.BatchTaskItem(
            batch_id=db_batch.id,
            dispatch_task_id=dt.id,
            dispatch_task_no=dt.task_no,
            plan_id=dt.plan_id,
            plan_no=dt.plan_no,
            container_no=container_no,
            seal_no=seal_no,
            route_no=route_no,
            frozen_snapshot=snapshot,
            loading_order=item_data.get("loading_order", 0),
            vehicle_assignment=item_data.get("vehicle_assignment"),
        )
        db.add(db_item)

        total_containers += 1
        if plan:
            total_weight += plan.total_weight or 0.0

    db_batch.total_containers = total_containers
    db_batch.total_weight = total_weight

    db.commit()
    db.refresh(db_batch)
    return db_batch


def get_batch_shipment(db: Session, batch_id: int = None, batch_no: str = None):
    if batch_id:
        return db.query(models.BatchShipment).filter(models.BatchShipment.id == batch_id).first()
    if batch_no:
        return db.query(models.BatchShipment).filter(models.BatchShipment.batch_no == batch_no).first()
    return None


def list_batch_shipments(db: Session, transport_direction: str = None, status: str = None, skip: int = 0, limit: int = 100):
    q = db.query(models.BatchShipment)
    if transport_direction:
        q = q.filter(models.BatchShipment.transport_direction == transport_direction)
    if status:
        q = q.filter(models.BatchShipment.status == status)
    return q.order_by(models.BatchShipment.created_at.desc()).offset(skip).limit(limit).all()


def update_batch_shipment(db: Session, batch_id: int, update_data: dict) -> models.BatchShipment:
    batch = get_batch_shipment(db, batch_id=batch_id)
    if not batch:
        return None

    from datetime import datetime as _dt
    for key, value in update_data.items():
        if value is None:
            continue
        if key == "planned_departure_time" and isinstance(value, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
                try:
                    value = _dt.strptime(value, fmt)
                    break
                except ValueError:
                    continue
        setattr(batch, key, value)
    db.commit()
    db.refresh(batch)
    return batch


def add_tasks_to_batch(db: Session, batch_id: int, task_items_data: List[dict]) -> models.BatchShipment:
    batch = get_batch_shipment(db, batch_id=batch_id)
    if not batch:
        return None

    total_containers = batch.total_containers or 0
    total_weight = batch.total_weight or 0.0

    for item_data in task_items_data:
        dt_id = item_data["dispatch_task_id"]
        dt = get_dispatch_task(db, task_id=dt_id)
        if not dt:
            continue

        existing = db.query(models.BatchTaskItem).filter(
            models.BatchTaskItem.batch_id == batch_id,
            models.BatchTaskItem.dispatch_task_id == dt_id,
            models.BatchTaskItem.removed_at == None,
        ).first()
        if existing:
            continue

        plan = get_packing_plan(db, plan_id=dt.plan_id)
        snapshot = _snapshot_dispatch_task(db, dt)

        container_no = plan.container_no if plan else None
        seal_no = plan.seal_no if plan else None
        route_no = None
        if dt.frozen_snapshot:
            route_no = dt.frozen_snapshot.get("route_no")

        db_item = models.BatchTaskItem(
            batch_id=batch_id,
            dispatch_task_id=dt.id,
            dispatch_task_no=dt.task_no,
            plan_id=dt.plan_id,
            plan_no=dt.plan_no,
            container_no=container_no,
            seal_no=seal_no,
            route_no=route_no,
            frozen_snapshot=snapshot,
            loading_order=item_data.get("loading_order", 0),
            vehicle_assignment=item_data.get("vehicle_assignment"),
        )
        db.add(db_item)
        total_containers += 1
        if plan:
            total_weight += plan.total_weight or 0.0

    batch.total_containers = total_containers
    batch.total_weight = total_weight
    if batch.status == "pending_grouping" and total_containers > 0:
        batch.status = "grouping"

    db.commit()
    db.refresh(batch)
    return batch


def remove_task_from_batch(db: Session, batch_id: int, task_item_id: int, remove_reason: str) -> models.BatchShipment:
    batch = get_batch_shipment(db, batch_id=batch_id)
    if not batch:
        return None

    item = db.query(models.BatchTaskItem).filter(
        models.BatchTaskItem.id == task_item_id,
        models.BatchTaskItem.batch_id == batch_id,
        models.BatchTaskItem.removed_at == None,
    ).first()
    if not item:
        return None

    from datetime import datetime as _dt
    item.removed_at = _dt.utcnow()
    item.remove_reason = remove_reason

    plan = get_packing_plan(db, plan_id=item.plan_id)
    batch.total_containers = max(0, (batch.total_containers or 0) - 1)
    if plan:
        batch.total_weight = max(0.0, (batch.total_weight or 0.0) - (plan.total_weight or 0.0))

    active_items = db.query(models.BatchTaskItem).filter(
        models.BatchTaskItem.batch_id == batch_id,
        models.BatchTaskItem.removed_at == None,
    ).all()

    if len(active_items) == 0 and batch.status in ("grouping", "pending_departure"):
        batch.status = "pending_grouping"

    db.commit()
    db.refresh(batch)
    return batch


def transition_batch_status(db: Session, batch_id: int, target_status: str, reason: str = None) -> models.BatchShipment:
    batch = get_batch_shipment(db, batch_id=batch_id)
    if not batch:
        return None

    from datetime import datetime as _dt

    valid_transitions = {
        "pending_grouping": ["grouping", "cancelled"],
        "grouping": ["pending_departure", "pending_grouping", "cancelled"],
        "pending_departure": ["dispatched", "grouping", "cancelled"],
        "dispatched": [],
        "cancelled": [],
    }

    if target_status not in valid_transitions.get(batch.status, []):
        raise ValueError(f"批次状态 {batch.status} 不允许转换到 {target_status}")

    if target_status == "cancelled":
        batch.cancelled_at = _dt.utcnow()
        batch.cancel_reason = reason or "批次取消"

    batch.status = target_status
    batch.status_changed_at = _dt.utcnow()
    db.commit()
    db.refresh(batch)
    return batch


def validate_batch_blockage(db: Session, batch_id: int) -> dict:
    batch = get_batch_shipment(db, batch_id=batch_id)
    if not batch:
        return {"is_valid": False, "blocked_items": [], "block_reasons": []}

    active_items = db.query(models.BatchTaskItem).filter(
        models.BatchTaskItem.batch_id == batch_id,
        models.BatchTaskItem.removed_at == None,
    ).all()

    blocked_items = []
    batch_block_reasons = []

    for item in active_items:
        dt = get_dispatch_task(db, task_id=item.dispatch_task_id)
        if not dt:
            item.is_blocked = True
            item.block_reason = "关联的发运任务不存在"
            blocked_items.append(item)
            batch_block_reasons.append({"type": "task_missing", "detail": f"发运任务 {item.dispatch_task_no} 不存在", "task_item_id": item.id})
            continue

        if dt.status == "pending_re_review":
            item.is_blocked = True
            item.block_reason = f"发运任务 {dt.task_no} 状态为待重审"
            blocked_items.append(item)
            batch_block_reasons.append({"type": "pending_re_review", "detail": f"发运任务 {dt.task_no} 处于待重审状态，批次不能继续发车", "task_item_id": item.id, "dispatch_task_no": dt.task_no})
            continue

        validation = validate_dispatch_dependencies(db, dt.id)
        if not validation["is_valid"]:
            item.is_blocked = True
            item.block_reason = f"发运任务 {dt.task_no} 依赖校验未通过: {'; '.join(br['detail'] for br in validation['block_reasons'])}"
            blocked_items.append(item)
            for br in validation["block_reasons"]:
                batch_block_reasons.append({"type": br["type"], "detail": f"任务 {dt.task_no}: {br['detail']}", "task_item_id": item.id, "dispatch_task_no": dt.task_no})
        else:
            item.is_blocked = False
            item.block_reason = None

    batch.block_reasons = batch_block_reasons
    db.commit()

    return {
        "is_valid": len(blocked_items) == 0,
        "blocked_items": blocked_items,
        "block_reasons": batch_block_reasons,
    }


def recalculate_batch_totals(db: Session, batch_id: int) -> models.BatchShipment:
    batch = get_batch_shipment(db, batch_id=batch_id)
    if not batch:
        return None

    active_items = db.query(models.BatchTaskItem).filter(
        models.BatchTaskItem.batch_id == batch_id,
        models.BatchTaskItem.removed_at == None,
    ).all()

    total_containers = len(active_items)
    total_weight = 0.0
    for item in active_items:
        plan = get_packing_plan(db, plan_id=item.plan_id)
        if plan:
            total_weight += plan.total_weight or 0.0

    batch.total_containers = total_containers
    batch.total_weight = total_weight
    db.commit()
    db.refresh(batch)
    return batch


# ==================== 费用核算 CRUD Functions ====================

def generate_rate_scheme_code() -> str:
    return f"RATE-{uuid.uuid4().hex[:6].upper()}"


def generate_calculation_no() -> str:
    return f"COST-{uuid.uuid4().hex[:8].upper()}"


def get_rate_scheme(db: Session, scheme_id: int = None, scheme_code: str = None) -> Optional[models.RateScheme]:
    if scheme_id:
        return db.query(models.RateScheme).filter(models.RateScheme.id == scheme_id).first()
    if scheme_code:
        return db.query(models.RateScheme).filter(models.RateScheme.scheme_code == scheme_code).first()
    return None


def resolve_rate_scheme(db: Session, identifier: str) -> Optional[models.RateScheme]:
    if not identifier:
        return get_default_rate_scheme(db)
    if identifier.isdigit():
        scheme = get_rate_scheme(db, scheme_id=int(identifier))
        if scheme:
            return scheme
    return get_rate_scheme(db, scheme_code=identifier)


def get_default_rate_scheme(db: Session) -> Optional[models.RateScheme]:
    return db.query(models.RateScheme).filter(
        models.RateScheme.is_default == True,
        models.RateScheme.is_active == True
    ).first()


def list_rate_schemes(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    carrier: Optional[str] = None,
) -> List[models.RateScheme]:
    q = db.query(models.RateScheme)
    if is_active is not None:
        q = q.filter(models.RateScheme.is_active == is_active)
    if carrier:
        q = q.filter(models.RateScheme.carrier == carrier)
    return q.order_by(
        models.RateScheme.is_default.desc(),
        models.RateScheme.created_at.desc()
    ).offset(skip).limit(limit).all()


def create_rate_scheme(
    db: Session,
    scheme_data: dict,
    container_rates: List[dict] = None,
) -> models.RateScheme:
    if not scheme_data.get("scheme_code"):
        scheme_data["scheme_code"] = generate_rate_scheme_code()

    if scheme_data.get("is_default"):
        db.query(models.RateScheme).filter(
            models.RateScheme.is_default == True
        ).update({"is_default": False})

    db_scheme = models.RateScheme(**scheme_data)
    db.add(db_scheme)
    db.flush()

    if container_rates:
        for rate_data in container_rates:
            container_id = rate_data["container_id"]
            container = get_container(db, container_id=container_id)
            hazard_list = rate_data.pop("hazard_surcharges", []) or []
            hazard_by_class = {}
            for h in hazard_list:
                if isinstance(h, dict):
                    hazard_by_class[str(h.get("hazard_class"))] = float(h.get("surcharge_amount", 0))
            rate_data["hazard_surcharge_by_class"] = hazard_by_class
            rate_config = models.ContainerRateConfig(
                scheme_id=db_scheme.id,
                container_name=container.name if container else f"Container-{container_id}",
                **rate_data
            )
            db.add(rate_config)

    db.commit()
    db.refresh(db_scheme)
    return db_scheme


def update_rate_scheme(db: Session, scheme_id: int, update_data: dict) -> Optional[models.RateScheme]:
    scheme = get_rate_scheme(db, scheme_id=scheme_id)
    if not scheme:
        return None

    if update_data.get("is_default") and not scheme.is_default:
        db.query(models.RateScheme).filter(
            models.RateScheme.is_default == True,
            models.RateScheme.id != scheme_id
        ).update({"is_default": False})

    for key, value in update_data.items():
        if value is not None and hasattr(scheme, key):
            setattr(scheme, key, value)

    db.commit()
    db.refresh(scheme)
    return scheme


def delete_rate_scheme(db: Session, scheme_id: int = None, scheme_code: str = None) -> Optional[models.RateScheme]:
    scheme = get_rate_scheme(db, scheme_id=scheme_id, scheme_code=scheme_code)
    if scheme:
        db.delete(scheme)
        db.commit()
    return scheme


def get_container_rate_config(db: Session, scheme_id: int, container_id: int) -> Optional[models.ContainerRateConfig]:
    return db.query(models.ContainerRateConfig).filter(
        models.ContainerRateConfig.scheme_id == scheme_id,
        models.ContainerRateConfig.container_id == container_id,
        models.ContainerRateConfig.is_active == True
    ).first()


def get_scheme_container_rates(db: Session, scheme_id: int) -> List[models.ContainerRateConfig]:
    return db.query(models.ContainerRateConfig).filter(
        models.ContainerRateConfig.scheme_id == scheme_id,
        models.ContainerRateConfig.is_active == True
    ).all()


def create_container_rate_config(
    db: Session,
    scheme_id: int,
    rate_data: dict,
) -> models.ContainerRateConfig:
    scheme = get_rate_scheme(db, scheme_id=scheme_id)
    if not scheme:
        raise ValueError(f"费率方案 {scheme_id} 不存在")

    container_id = rate_data["container_id"]
    container = get_container(db, container_id=container_id)
    if not container:
        raise ValueError(f"集装箱 {container_id} 不存在")

    existing = get_container_rate_config(db, scheme_id, container_id)
    if existing:
        return update_container_rate_config(db, existing.id, rate_data)

    hazard_list = rate_data.pop("hazard_surcharges", []) or []
    hazard_by_class = {}
    for h in hazard_list:
        if isinstance(h, dict):
            hazard_by_class[str(h.get("hazard_class"))] = float(h.get("surcharge_amount", 0))
    rate_data["hazard_surcharge_by_class"] = hazard_by_class

    db_rate = models.ContainerRateConfig(
        scheme_id=scheme_id,
        container_name=container.name,
        **rate_data
    )
    db.add(db_rate)
    db.commit()
    db.refresh(db_rate)
    return db_rate


def update_container_rate_config(
    db: Session,
    config_id: int,
    update_data: dict,
) -> Optional[models.ContainerRateConfig]:
    config = db.query(models.ContainerRateConfig).filter(
        models.ContainerRateConfig.id == config_id
    ).first()
    if not config:
        return None

    hazard_list = update_data.pop("hazard_surcharges", None)
    if hazard_list is not None:
        hazard_by_class = {}
        for h in hazard_list:
            if isinstance(h, dict):
                hazard_by_class[str(h.get("hazard_class"))] = float(h.get("surcharge_amount", 0))
        config.hazard_surcharge_by_class = hazard_by_class

    for key, value in update_data.items():
        if value is not None and hasattr(config, key):
            setattr(config, key, value)

    db.commit()
    db.refresh(config)
    return config


def delete_container_rate_config(db: Session, config_id: int) -> Optional[models.ContainerRateConfig]:
    config = db.query(models.ContainerRateConfig).filter(
        models.ContainerRateConfig.id == config_id
    ).first()
    if config:
        db.delete(config)
        db.commit()
    return config


def get_cost_calculation(
    db: Session,
    calculation_id: int = None,
    calculation_no: str = None,
) -> Optional[models.CostCalculation]:
    if calculation_id:
        return db.query(models.CostCalculation).filter(
            models.CostCalculation.id == calculation_id
        ).first()
    if calculation_no:
        return db.query(models.CostCalculation).filter(
            models.CostCalculation.calculation_no == calculation_no
        ).first()
    return None


def find_existing_calculation(
    db: Session,
    plan_id: int,
    scheme_id: int,
    plan_version: int = None,
    plan_content_hash: str = None,
) -> Optional[models.CostCalculation]:
    q = db.query(models.CostCalculation).filter(
        models.CostCalculation.plan_id == plan_id,
        models.CostCalculation.scheme_id == scheme_id,
        models.CostCalculation.calculation_status == "completed"
    )
    if plan_version is not None:
        q = q.filter(models.CostCalculation.plan_version == plan_version)
    if plan_content_hash:
        q = q.filter(models.CostCalculation.plan_content_hash == plan_content_hash)
    return q.order_by(models.CostCalculation.created_at.desc()).first()


def list_cost_calculations(
    db: Session,
    plan_id: Optional[int] = None,
    scheme_id: Optional[int] = None,
    calculation_status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[models.CostCalculation]:
    q = db.query(models.CostCalculation)
    if plan_id:
        q = q.filter(models.CostCalculation.plan_id == plan_id)
    if scheme_id:
        q = q.filter(models.CostCalculation.scheme_id == scheme_id)
    if calculation_status:
        q = q.filter(models.CostCalculation.calculation_status == calculation_status)
    return q.order_by(models.CostCalculation.created_at.desc()).offset(skip).limit(limit).all()


def get_box_details(db: Session, calculation_id: int) -> List[models.BoxCostDetail]:
    return db.query(models.BoxCostDetail).filter(
        models.BoxCostDetail.calculation_id == calculation_id
    ).order_by(models.BoxCostDetail.box_index).all()


def get_cargo_allocations(db: Session, calculation_id: int) -> List[models.CargoCostAllocation]:
    return db.query(models.CargoCostAllocation).filter(
        models.CargoCostAllocation.calculation_id == calculation_id
    ).order_by(
        models.CargoCostAllocation.box_index,
        models.CargoCostAllocation.id
    ).all()


def create_cost_calculation(
    db: Session,
    calc_data: dict,
    box_details: List[dict],
    cargo_allocations: List[dict],
) -> models.CostCalculation:
    if not calc_data.get("calculation_no"):
        calc_data["calculation_no"] = generate_calculation_no()

    db_calc = models.CostCalculation(**calc_data)
    db.add(db_calc)
    db.flush()

    for bd in box_details:
        db_box = models.BoxCostDetail(
            calculation_id=db_calc.id,
            **bd
        )
        db.add(db_box)

    db.flush()

    box_id_map = {}
    all_boxes = db.query(models.BoxCostDetail).filter(
        models.BoxCostDetail.calculation_id == db_calc.id
    ).all()
    for b in all_boxes:
        box_id_map[b.box_index] = b.id

    for ca in cargo_allocations:
        box_idx = ca.get("box_index", 0)
        ca["box_detail_id"] = box_id_map.get(box_idx)
        db_alloc = models.CargoCostAllocation(
            calculation_id=db_calc.id,
            **ca
        )
        db.add(db_alloc)

    db.commit()
    db.refresh(db_calc)
    return db_calc


def delete_cost_calculation(
    db: Session,
    calculation_id: int = None,
    calculation_no: str = None,
) -> Optional[models.CostCalculation]:
    calc = get_cost_calculation(db, calculation_id=calculation_id, calculation_no=calculation_no)
    if calc:
        db.delete(calc)
        db.commit()
    return calc


def create_default_rate_schemes(db: Session):
    existing = db.query(models.RateScheme).filter(models.RateScheme.is_default == True).all()
    if existing:
        return

    containers = get_containers(db)
    if not containers:
        create_default_containers(db)
        containers = get_containers(db)

    scheme_container_rates = {}
    for c in containers:
        cbm = (c.length * c.width * c.height) / 1e9
        base_freight_20gp = 3000.0
        factor = cbm / 33.2
        base_freight = round(base_freight_20gp * factor, 2)

        scheme_container_rates[c.id] = {
            "20GP-BASE": {"base": base_freight, "overweight_flat": 500, "overweight_per_kg": 0.5, "threshold": c.max_weight * 0.9},
            "MAERSK-PREMIUM": {"base": base_freight * 1.15, "overweight_flat": 600, "overweight_per_kg": 0.6, "threshold": c.max_weight * 0.85},
            "COSCO-STANDARD": {"base": base_freight * 0.95, "overweight_flat": 450, "overweight_per_kg": 0.45, "threshold": c.max_weight * 0.92},
        }

    default_schemes = [
        {
            "scheme_code": "DEFAULT-MSC-2025",
            "scheme_name": "地中海航运MSC-2025标准",
            "carrier": "MSC地中海航运",
            "trade_lane": "远东-欧洲",
            "currency": "CNY",
            "is_default": True,
            "is_active": True,
            "description": "系统默认的MSC标准费率方案,适用于日常报价估算",
            "rates_key": "20GP-BASE",
            "reefer": 2000,
            "frozen": 1200,
            "hazard": {"1": 8000, "2": 5000, "3": 4000, "4": 3000, "5": 6000, "6": 3500},
            "hazard_per_kg": 2.0,
        },
        {
            "scheme_code": "DEFAULT-MAERSK-2025",
            "scheme_name": "马士基MAERSK-2025Q2航线",
            "carrier": "MAERSK马士基",
            "trade_lane": "远东-北欧",
            "currency": "CNY",
            "is_default": False,
            "is_active": True,
            "description": "马士基航运2025年第二季度远东至北欧航线报价",
            "rates_key": "MAERSK-PREMIUM",
            "reefer": 2800,
            "frozen": 1500,
            "hazard": {"1": 10000, "2": 6500, "3": 5000, "4": 3800, "5": 7500, "6": 4200},
            "hazard_per_kg": 2.5,
        },
        {
            "scheme_code": "DEFAULT-COSCO-2025",
            "scheme_name": "中远海运COSCO-2025Q2",
            "carrier": "COSCO中远海运",
            "trade_lane": "远东-美西",
            "currency": "CNY",
            "is_default": False,
            "is_active": True,
            "description": "中远海运2025年第二季度远东至美西航线标准报价",
            "rates_key": "COSCO-STANDARD",
            "reefer": 2400,
            "frozen": 1400,
            "hazard": {"1": 9000, "2": 5800, "3": 4500, "4": 3400, "5": 6800, "6": 3800},
            "hazard_per_kg": 2.2,
        },
    ]

    for scheme_info in default_schemes:
        rates_key = scheme_info.pop("rates_key")
        reefer = scheme_info.pop("reefer")
        frozen = scheme_info.pop("frozen")
        hazard_conf = scheme_info.pop("hazard")
        hazard_per_kg = scheme_info.pop("hazard_per_kg")

        container_rates = []
        for c in containers:
            rate_conf = scheme_container_rates.get(c.id, {}).get(rates_key, {})
            hazard_list = [
                {"hazard_class": int(k), "surcharge_amount": float(v)}
                for k, v in hazard_conf.items()
            ]
            container_rates.append({
                "container_id": c.id,
                "base_freight": rate_conf.get("base", 3000),
                "overweight_threshold_kg": rate_conf.get("threshold", 25000),
                "overweight_surcharge_per_kg": rate_conf.get("overweight_per_kg", 0.5),
                "overweight_surcharge_flat": rate_conf.get("overweight_flat", 500),
                "reefer_surcharge": reefer,
                "frozen_surcharge": frozen,
                "hazard_surcharges": hazard_list,
                "hazard_surcharge_per_kg": hazard_per_kg,
                "is_active": True,
            })

        create_rate_scheme(db, scheme_info, container_rates)


# ==================== 货损理赔 CRUD Functions ====================

def generate_inspection_no() -> str:
    return f"INSP-{uuid.uuid4().hex[:8].upper()}"


def generate_claim_no() -> str:
    return f"CLAIM-{uuid.uuid4().hex[:8].upper()}"


def resolve_packing_plan(db: Session, plan_identifier: str):
    plan = None
    if plan_identifier.isdigit():
        plan = get_packing_plan(db, plan_id=int(plan_identifier))
    if plan is None:
        plan = get_packing_plan(db, plan_no=plan_identifier)
    return plan


def get_damage_inspection(db: Session, inspection_id: int = None, inspection_no: str = None):
    if inspection_id:
        return db.query(models.CargoDamageInspection).filter(
            models.CargoDamageInspection.id == inspection_id
        ).first()
    if inspection_no:
        return db.query(models.CargoDamageInspection).filter(
            models.CargoDamageInspection.inspection_no == inspection_no
        ).first()
    return None


def list_damage_inspections(
    db: Session,
    plan_identifier: str = None,
    status: str = None,
    skip: int = 0,
    limit: int = 100
):
    q = db.query(models.CargoDamageInspection)
    if plan_identifier:
        plan = resolve_packing_plan(db, plan_identifier)
        if plan:
            q = q.filter(models.CargoDamageInspection.plan_id == plan.id)
    if status:
        q = q.filter(models.CargoDamageInspection.status == status)
    return q.order_by(models.CargoDamageInspection.created_at.desc()).offset(skip).limit(limit).all()


def get_inspection_items(db: Session, inspection_id: int) -> list:
    return db.query(models.InspectionCargoItem).filter(
        models.InspectionCargoItem.inspection_id == inspection_id
    ).order_by(models.InspectionCargoItem.item_no).all()


def get_damage_inferences(db: Session, inspection_id: int) -> list:
    return db.query(models.DamageInference).filter(
        models.DamageInference.inspection_id == inspection_id
    ).all()


def get_claim_record(db: Session, claim_id: int = None, claim_no: str = None):
    if claim_id:
        return db.query(models.ClaimRecord).filter(
            models.ClaimRecord.id == claim_id
        ).first()
    if claim_no:
        return db.query(models.ClaimRecord).filter(
            models.ClaimRecord.claim_no == claim_no
        ).first()
    return None


def list_claim_records(
    db: Session,
    plan_identifier: str = None,
    status: str = None,
    skip: int = 0,
    limit: int = 100
):
    q = db.query(models.ClaimRecord)
    if plan_identifier:
        plan = resolve_packing_plan(db, plan_identifier)
        if plan:
            q = q.filter(models.ClaimRecord.plan_id == plan.id)
    if status:
        q = q.filter(models.ClaimRecord.status == status)
    return q.order_by(models.ClaimRecord.created_at.desc()).offset(skip).limit(limit).all()


def get_claim_items(db: Session, claim_id: int) -> list:
    return db.query(models.ClaimItem).filter(
        models.ClaimItem.claim_id == claim_id
    ).all()


def get_claim_statistics_by_responsibility(
    db: Session,
    plan_identifier: str = None
) -> dict:
    q = db.query(models.ClaimRecord)
    if plan_identifier:
        plan = resolve_packing_plan(db, plan_identifier)
        if plan:
            q = q.filter(models.ClaimRecord.plan_id == plan.id)
    
    claims = q.all()
    
    stats = {
        "carrier_amount": 0.0,
        "packer_amount": 0.0,
        "shipper_amount": 0.0,
        "force_majeure_amount": 0.0,
        "total_amount": 0.0,
        "claim_count": len(claims),
    }
    
    for claim in claims:
        stats["carrier_amount"] += claim.carrier_responsibility_amount or 0
        stats["packer_amount"] += claim.packer_responsibility_amount or 0
        stats["shipper_amount"] += claim.shipper_responsibility_amount or 0
        stats["force_majeure_amount"] += claim.force_majeure_amount or 0
        stats["total_amount"] += claim.total_claim_amount or 0
    
    for key in stats:
        if key.endswith("_amount") or key == "total_amount":
            stats[key] = round(stats[key], 2)
    
    return stats


def create_damage_inspection(
    db: Session,
    inspection_data: dict,
    inspection_items_data: list
) -> models.CargoDamageInspection:
    from datetime import datetime as _dt
    
    plan_identifier = inspection_data.get("plan_identifier")
    plan = resolve_packing_plan(db, plan_identifier)
    if not plan:
        raise ValueError("配载方案不存在")
    
    container = get_container(db, container_id=plan.container_id)
    if not container:
        raise ValueError("关联集装箱信息不存在")
    
    packed_cargos = get_packed_cargos(db, plan_id=plan.id)
    packed_cargo_map = {pc.id: pc for pc in packed_cargos}
    
    inspection_no = inspection_data.get("inspection_no") or generate_inspection_no()
    
    inspection_date = None
    if inspection_data.get("inspection_date"):
        date_str = inspection_data["inspection_date"]
        if isinstance(date_str, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
                try:
                    inspection_date = _dt.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
    
    db_inspection = models.CargoDamageInspection(
        inspection_no=inspection_no,
        plan_id=plan.id,
        plan_no=plan.plan_no,
        plan_version=plan.version or 1,
        container_no=plan.container_no,
        shipment_no=plan.shipment_no,
        inspection_date=inspection_date,
        inspector=inspection_data.get("inspector"),
        total_cargos=len(packed_cargos),
        intact_count=0,
        minor_damage_count=0,
        severe_damage_count=0,
        lost_count=0,
        remarks=inspection_data.get("remarks"),
        status=inspection_data.get("status", "draft"),
    )
    db.add(db_inspection)
    db.flush()
    
    intact_count = 0
    minor_count = 0
    severe_count = 0
    lost_count = 0
    
    from app.damage_claim_engine import (
        DAMAGE_STATUS_INTACT,
        DAMAGE_STATUS_MINOR,
        DAMAGE_STATUS_SEVERE,
        DAMAGE_STATUS_LOST,
        _calculate_top_pressure,
        _calculate_stack_layer,
        _is_door_side,
        _is_bottom_layer,
    )
    
    all_cargos_for_calc = []
    for pc in packed_cargos:
        all_cargos_for_calc.append({
            "id": pc.id,
            "x": pc.x,
            "y": pc.y,
            "z": pc.z,
            "length": pc.length,
            "width": pc.width,
            "height": pc.height,
            "weight": pc.weight,
        })
    
    for idx, item_data in enumerate(inspection_items_data):
        packed_cargo_id = item_data.get("packed_cargo_id")
        pc = packed_cargo_map.get(packed_cargo_id)
        
        if not pc:
            continue
        
        damage_status = item_data.get("damage_status", DAMAGE_STATUS_INTACT)
        damage_type = item_data.get("damage_type")
        
        if damage_status == DAMAGE_STATUS_INTACT:
            intact_count += 1
        elif damage_status == DAMAGE_STATUS_MINOR:
            minor_count += 1
        elif damage_status == DAMAGE_STATUS_SEVERE:
            severe_count += 1
        elif damage_status == DAMAGE_STATUS_LOST:
            lost_count += 1
        
        cargo_dict = {
            "id": pc.id,
            "x": pc.x,
            "y": pc.y,
            "z": pc.z,
            "length": pc.length,
            "width": pc.width,
            "height": pc.height,
            "weight": pc.weight,
        }
        
        top_pressure = _calculate_top_pressure(cargo_dict, all_cargos_for_calc)
        stack_layer = _calculate_stack_layer(cargo_dict, all_cargos_for_calc)
        is_door_side = _is_door_side(cargo_dict, container.length)
        is_bottom = _is_bottom_layer(cargo_dict)
        
        db_item = models.InspectionCargoItem(
            inspection_id=db_inspection.id,
            packed_cargo_id=pc.id,
            cargo_id=pc.cargo_id,
            cargo_name=pc.cargo_name,
            item_no=idx + 1,
            damage_status=damage_status,
            damage_type=damage_type.value if hasattr(damage_type, 'value') else damage_type,
            declared_value=item_data.get("declared_value", 0),
            damage_description=item_data.get("damage_description"),
            position_x=pc.x,
            position_y=pc.y,
            position_z=pc.z,
            length=pc.length,
            width=pc.width,
            height=pc.height,
            weight=pc.weight,
            max_top_load=pc.max_top_load or 0,
            temperature_class=pc.temperature_class,
            hazard_class=getattr(pc, 'hazard_class', None),
            stack_layer=stack_layer,
            is_door_side=is_door_side,
            is_bottom_layer=is_bottom,
            top_pressure_weight=round(top_pressure, 2),
        )
        db.add(db_item)
    
    db_inspection.intact_count = intact_count
    db_inspection.minor_damage_count = minor_count
    db_inspection.severe_damage_count = severe_count
    db_inspection.lost_count = lost_count
    
    db.commit()
    db.refresh(db_inspection)
    return db_inspection


def run_damage_analysis(db: Session, inspection_id: int) -> dict:
    from app.damage_claim_engine import analyze_damage_and_generate_claim
    
    inspection = get_damage_inspection(db, inspection_id=inspection_id)
    if not inspection:
        raise ValueError("检验记录不存在")
    
    plan = get_packing_plan(db, plan_id=inspection.plan_id)
    if not plan:
        raise ValueError("关联配载方案不存在")
    
    container = get_container(db, container_id=plan.container_id)
    if not container:
        raise ValueError("关联集装箱信息不存在")
    
    inspection_items = get_inspection_items(db, inspection_id)
    packed_cargos = get_packed_cargos(db, plan_id=plan.id)
    
    hazard_matrix = db.query(models.HazardSegregationMatrix).filter(
        models.HazardSegregationMatrix.is_active == True
    ).all()
    hazard_matrix_data = []
    for hm in hazard_matrix:
        hazard_matrix_data.append({
            "class_a": hm.class_a,
            "class_b": hm.class_b,
            "min_distance_mm": hm.min_distance_mm,
            "segregation_level": hm.segregation_level,
        })
    
    plan_data = {
        "cog_x": plan.cog_x,
        "cog_y": plan.cog_y,
        "cog_z": plan.cog_z,
        "cog_offset_x_ratio": plan.cog_offset_x_ratio,
        "cog_offset_y_ratio": plan.cog_offset_y_ratio,
    }
    
    inspection_items_data = []
    for item in inspection_items:
        inspection_items_data.append({
            "id": item.id,
            "cargo_id": item.cargo_id,
            "cargo_name": item.cargo_name,
            "damage_status": item.damage_status,
            "damage_type": item.damage_type,
            "declared_value": item.declared_value,
            "position_x": item.position_x,
            "position_y": item.position_y,
            "position_z": item.position_z,
            "x": item.position_x,
            "y": item.position_y,
            "z": item.position_z,
            "length": item.length,
            "width": item.width,
            "height": item.height,
            "weight": item.weight,
            "max_top_load": item.max_top_load,
            "temperature_class": item.temperature_class,
            "hazard_class": item.hazard_class,
            "stack_layer": item.stack_layer,
            "is_door_side": item.is_door_side,
            "is_bottom_layer": item.is_bottom_layer,
            "top_pressure_weight": item.top_pressure_weight,
        })
    
    packed_cargos_data = []
    for pc in packed_cargos:
        packed_cargos_data.append({
            "id": pc.id,
            "packed_cargo_id": pc.id,
            "cargo_id": pc.cargo_id,
            "cargo_name": pc.cargo_name,
            "x": pc.x,
            "y": pc.y,
            "z": pc.z,
            "length": pc.length,
            "width": pc.width,
            "height": pc.height,
            "weight": pc.weight,
            "max_top_load": pc.max_top_load or 0,
            "temperature_class": pc.temperature_class or "AMBIENT",
            "hazard_class": getattr(pc, 'hazard_class', None),
        })
    
    result = analyze_damage_and_generate_claim(
        {"inspection_items": inspection_items_data},
        plan_data,
        packed_cargos_data,
        container.length,
        hazard_matrix_data
    )
    
    db.query(models.DamageInference).filter(
        models.DamageInference.inspection_id == inspection_id
    ).delete()
    
    for inf in result["inferences"]:
        db_inf = models.DamageInference(
            inspection_id=inspection_id,
            inspection_item_id=inf.get("inspection_item_id"),
            cargo_id=inf.get("cargo_id"),
            cargo_name=inf.get("cargo_name"),
            inferred_cause=inf.get("inferred_cause"),
            confidence_level=inf.get("confidence_level"),
            responsibility=inf.get("responsibility"),
            inference_detail=inf.get("inference_detail", {}),
            evidence_list=inf.get("evidence_list", []),
            explanation=inf.get("explanation"),
        )
        db.add(db_inf)
    
    claim_summary = result["claim_summary"]
    
    existing_claim = db.query(models.ClaimRecord).filter(
        models.ClaimRecord.inspection_id == inspection_id
    ).first()
    
    if existing_claim:
        db.query(models.ClaimItem).filter(
            models.ClaimItem.claim_id == existing_claim.id
        ).delete()
        db.delete(existing_claim)
    
    claim_no = generate_claim_no()
    db_claim = models.ClaimRecord(
        claim_no=claim_no,
        inspection_id=inspection_id,
        plan_id=inspection.plan_id,
        plan_no=inspection.plan_no,
        container_no=inspection.container_no,
        shipment_no=inspection.shipment_no,
        total_declared_value=claim_summary.get("total_declared_value", 0),
        total_claim_amount=claim_summary.get("total_claim_amount", 0),
        minor_damage_amount=claim_summary.get("minor_damage_amount", 0),
        severe_damage_amount=claim_summary.get("severe_damage_amount", 0),
        lost_amount=claim_summary.get("lost_amount", 0),
        carrier_responsibility_amount=claim_summary.get("carrier_responsibility_amount", 0),
        packer_responsibility_amount=claim_summary.get("packer_responsibility_amount", 0),
        shipper_responsibility_amount=claim_summary.get("shipper_responsibility_amount", 0),
        force_majeure_amount=claim_summary.get("force_majeure_amount", 0),
        status="pending",
        claim_date=inspection.inspection_date,
    )
    db.add(db_claim)
    db.flush()
    
    for ci in claim_summary.get("claim_items", []):
        db_ci = models.ClaimItem(
            claim_id=db_claim.id,
            inspection_item_id=ci.get("inspection_item_id"),
            cargo_id=ci.get("cargo_id"),
            cargo_name=ci.get("cargo_name"),
            damage_status=ci.get("damage_status"),
            damage_type=ci.get("damage_type"),
            declared_value=ci.get("declared_value", 0),
            claim_ratio=ci.get("claim_ratio", 0),
            claim_amount=ci.get("claim_amount", 0),
            primary_responsibility=ci.get("primary_responsibility"),
        )
        db.add(db_ci)
    
    inspection.status = "submitted"
    
    db.commit()
    db.refresh(inspection)
    db.refresh(db_claim)
    
    return {
        "inspection_id": inspection.id,
        "inspection_no": inspection.inspection_no,
        "inferences": result["inferences"],
        "claim_summary": claim_summary,
        "claim_id": db_claim.id,
        "claim_no": db_claim.claim_no,
    }


def create_demo_damage_claim(db: Session):
    existing = db.query(models.CargoDamageInspection).first()
    if existing:
        return
    
    plans = db.query(models.PackingPlan).all()
    if not plans:
        create_demo_review_record(db)
        plans = db.query(models.PackingPlan).all()
    
    if not plans:
        return
    
    plan = plans[0]
    packed_cargos = get_packed_cargos(db, plan_id=plan.id)
    if not packed_cargos or len(packed_cargos) < 2:
        return
    
    from app.damage_claim_engine import (
        DAMAGE_STATUS_MINOR,
        DAMAGE_STATUS_SEVERE,
        DAMAGE_TYPE_CRUSH,
        DAMAGE_TYPE_WET,
    )
    
    bottom_cargos = sorted(packed_cargos, key=lambda c: c.z)
    door_side_cargos = sorted(packed_cargos, key=lambda c: -(c.x + c.length))
    
    damaged_cargo_1 = bottom_cargos[0] if bottom_cargos else packed_cargos[0]
    damaged_cargo_2 = door_side_cargos[0] if door_side_cargos and door_side_cargos[0].id != damaged_cargo_1.id else packed_cargos[1]
    
    inspection_items = [
        {
            "packed_cargo_id": damaged_cargo_1.id,
            "damage_status": DAMAGE_STATUS_SEVERE,
            "damage_type": DAMAGE_TYPE_CRUSH,
            "declared_value": 5000.0,
            "damage_description": "货物顶部明显凹陷，内部货物受损严重",
        },
        {
            "packed_cargo_id": damaged_cargo_2.id,
            "damage_status": DAMAGE_STATUS_MINOR,
            "damage_type": DAMAGE_TYPE_WET,
            "declared_value": 3000.0,
            "damage_description": "外包装箱有水渍痕迹，内容物部分受潮",
        },
    ]
    
    inspection_data = {
        "plan_identifier": str(plan.id),
        "inspector": "demo_inspector",
        "inspection_date": "2026-06-15T10:30:00",
        "remarks": "演示货损理赔记录-到港检验发现2件货物受损",
        "status": "draft",
    }
    
    try:
        inspection = create_damage_inspection(db, inspection_data, inspection_items)
        run_damage_analysis(db, inspection.id)
    except Exception:
        pass



