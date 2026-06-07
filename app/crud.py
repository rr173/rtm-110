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
            orientation=pc["orientation"]
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
