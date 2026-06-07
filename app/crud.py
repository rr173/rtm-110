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
