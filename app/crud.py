from sqlalchemy.orm import Session
from app import models, schemas
from app.schemas import TemperatureClassEnum
from datetime import datetime
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


def create_trailer_load_plan(db: Session, plan_data: dict, loaded_boxes: list, unload_sequence: list = None) -> models.TrailerLoadPlan:
    plan_no = generate_trailer_plan_no()
    db_plan = models.TrailerLoadPlan(
        plan_no=plan_no,
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
        recommendation=plan_data.get("recommendation", "")
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


def get_trailer_load_plan(db: Session, plan_id: int = None, plan_no: str = None):
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

    trailer_plans = db.query(models.TrailerLoadPlan).all()
    for r in trailer_plans:
        results.append({
            "type": "trailer_load",
            "obj": r,
            "id": r.id,
            "no": r.plan_no,
            "version": plan_version
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
                assignments = db.query(models.UnloadingCargoAssignment).filter(
                    models.UnloadingCargoAssignment.route_id == route.id,
                    models.UnloadingCargoAssignment.packed_cargo_id == sc["packed_cargo_id"]
                ).all()
                for assign in assignments:
                    if sc["new_stop_order"] is not None:
                        assign.stop_order = sc["new_stop_order"]
                    if sc["new_unload_order"] is not None:
                        assign.unload_order = sc["new_unload_order"]

    bump_plan_version(db, plan.id)
    db.refresh(plan)

    impact_items = db.query(models.ChangeImpactItem).filter(
        models.ChangeImpactItem.analysis_id == analysis.id
    ).all()

    for item in impact_items:
        decision = item.impact_decision
        result_type = item.result_type
        result_id = item.result_id

        if decision == "invalidate":
            if result_type == "review_task":
                task = db.query(models.ReviewTask).filter(
                    models.ReviewTask.id == result_id
                ).first()
                if task:
                    task.is_valid = False
                    task.invalid_reason = f"方案变更(v{current_version}→v{plan.version})：{item.impact_reason}"

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
                    doc.void_reason = f"方案变更(v{current_version}→v{plan.version})：{item.impact_reason}"
                    doc.voided_at = datetime.utcnow()

        elif decision == "rerun":
            if result_type == "compliance_audit":
                pass
            elif result_type == "unloading_route":
                simulations = db.query(models.UnloadingSimulation).filter(
                    models.UnloadingSimulation.route_id == result_id
                ).all()
                for sim in simulations:
                    sim.status = "outdated" if hasattr(sim, 'status') else sim.status

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


