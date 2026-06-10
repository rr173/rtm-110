from sqlalchemy.orm import Session
from app import models, schemas
from datetime import datetime
import uuid


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


def create_cargo(db: Session, cargo: schemas.CargoCreate):
    db_cargo = models.Cargo(**cargo.model_dump())
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
        cargo_list.append({
            "cargo_id": pc.cargo_id,
            "cargo_name": pc.cargo_name,
            "x": pc.x, "y": pc.y, "z": pc.z,
            "length": pc.length, "width": pc.width, "height": pc.height,
            "weight": pc.weight, "orientation": pc.orientation
        })
    content = {
        "container_id": plan.container_id,
        "total_cargos": plan.total_cargos,
        "placed_count": plan.placed_count,
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

