from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid

from app.database import engine, get_db, Base
from app import models, schemas, crud
from app.packing.algorithm import pack_boxes, Box, rank_plans

Base.metadata.create_all(bind=engine)

app = FastAPI(title="集装箱三维配载计算服务", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    db = next(get_db())
    crud.create_default_containers(db)


@app.get("/")
def root():
    return {"message": "集装箱三维配载计算服务", "version": "1.0.0"}


@app.get("/containers", response_model=List[schemas.Container])
def list_containers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    containers = crud.get_containers(db, skip=skip, limit=limit)
    return containers


@app.get("/containers/{container_id}", response_model=schemas.Container)
def get_container(container_id: int, db: Session = Depends(get_db)):
    container = crud.get_container(db, container_id=container_id)
    if container is None:
        raise HTTPException(status_code=404, detail="集装箱不存在")
    return container


@app.post("/containers", response_model=schemas.Container)
def create_container(container: schemas.ContainerCreate, db: Session = Depends(get_db)):
    return crud.create_container(db=db, container=container)


@app.delete("/containers/{container_id}")
def delete_container(container_id: int, db: Session = Depends(get_db)):
    container = crud.delete_container(db, container_id=container_id)
    if container is None:
        raise HTTPException(status_code=404, detail="集装箱不存在")
    return {"message": "删除成功"}


@app.get("/cargos", response_model=List[schemas.Cargo])
def list_cargos(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    cargos = crud.get_cargos(db, skip=skip, limit=limit)
    return cargos


@app.get("/cargos/{cargo_id}", response_model=schemas.Cargo)
def get_cargo(cargo_id: int, db: Session = Depends(get_db)):
    cargo = crud.get_cargo(db, cargo_id=cargo_id)
    if cargo is None:
        raise HTTPException(status_code=404, detail="货物不存在")
    return cargo


@app.post("/cargos", response_model=schemas.Cargo)
def create_cargo(cargo: schemas.CargoCreate, db: Session = Depends(get_db)):
    return crud.create_cargo(db=db, cargo=cargo)


@app.put("/cargos/{cargo_id}", response_model=schemas.Cargo)
def update_cargo(cargo_id: int, cargo_update: schemas.CargoUpdate, db: Session = Depends(get_db)):
    cargo = crud.update_cargo(db, cargo_id=cargo_id, cargo_update=cargo_update)
    if cargo is None:
        raise HTTPException(status_code=404, detail="货物不存在")
    return cargo


@app.delete("/cargos/{cargo_id}")
def delete_cargo(cargo_id: int, db: Session = Depends(get_db)):
    cargo = crud.delete_cargo(db, cargo_id=cargo_id)
    if cargo is None:
        raise HTTPException(status_code=404, detail="货物不存在")
    return {"message": "删除成功"}


@app.post("/packing/compare", response_model=schemas.PackingCompareResult)
def compare_packing(request: schemas.PackingCompareRequest, save: bool = True, db: Session = Depends(get_db)):
    container_ids = request.container_ids
    if not container_ids:
        containers = crud.get_containers(db)
        container_ids = [c.id for c in containers]

    if not container_ids:
        raise HTTPException(status_code=400, detail="没有可用的集装箱箱型")

    boxes = []
    total_cargos = 0
    for cargo_id in request.cargo_ids:
        cargo = crud.get_cargo(db, cargo_id=cargo_id)
        if cargo is None:
            raise HTTPException(status_code=404, detail=f"货物 ID {cargo_id} 不存在")
        total_cargos += cargo.quantity
        for i in range(cargo.quantity):
            boxes.append(Box(
                cargo_id=cargo.id,
                cargo_name=cargo.name,
                length=cargo.length,
                width=cargo.width,
                height=cargo.height,
                weight=cargo.weight,
                can_rotate_horizontal=cargo.can_rotate_horizontal,
                can_flip=cargo.can_flip,
                max_top_load=cargo.max_top_load
            ))

    plans_data = []
    for container_id in container_ids:
        container = crud.get_container(db, container_id=container_id)
        if container is None:
            continue

        result = pack_boxes(
            container_length=container.length,
            container_width=container.width,
            container_height=container.height,
            container_max_weight=container.max_weight,
            boxes=boxes
        )

        plan_info = {
            "container_id": container.id,
            "container_name": container.name,
            "total_cargos": total_cargos,
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
            "placed_cargos": result["placed_cargos"],
            "unplaced_cargos": result["unplaced_cargos"],
        }
        plans_data.append(plan_info)

    ranked_plans = rank_plans(plans_data)

    for idx, plan in enumerate(ranked_plans):
        if "plan_no" not in plan:
            plan["plan_no"] = f"TMP-{uuid.uuid4().hex[:8].upper()}"
        if "id" not in plan:
            plan["id"] = 0
        if "created_at" not in plan:
            plan["created_at"] = ""

    comparison_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"

    saved_plans = []
    if save:
        for plan_info in ranked_plans:
            plan_data = {k: v for k, v in plan_info.items() if k != "placed_cargos" and k != "unplaced_cargos"}
            db_plan = crud.create_packing_plan(db, plan_data, plan_info["placed_cargos"])
            crud.update_packing_plan_score(
                db, db_plan.id,
                plan_info["score"],
                plan_info["rank"],
                plan_info["recommendation"]
            )
            saved_plans.append({
                "id": db_plan.id,
                "plan_no": db_plan.plan_no,
                "container_id": db_plan.container_id,
                "container_name": db_plan.container_name,
                "total_cargos": db_plan.total_cargos,
                "placed_count": db_plan.placed_count,
                "unplaced_count": db_plan.unplaced_count,
                "total_weight": db_plan.total_weight,
                "volume_utilization": db_plan.volume_utilization,
                "cog_x": db_plan.cog_x,
                "cog_y": db_plan.cog_y,
                "cog_z": db_plan.cog_z,
                "cog_within_limit": db_plan.cog_within_limit,
                "cog_offset_x_ratio": db_plan.cog_offset_x_ratio,
                "cog_offset_y_ratio": db_plan.cog_offset_y_ratio,
                "score": db_plan.score,
                "rank": db_plan.rank,
                "recommendation": db_plan.recommendation,
                "created_at": db_plan.created_at.isoformat() if db_plan.created_at else ""
            })
    else:
        saved_plans = ranked_plans

    ranking = []
    for idx, plan in enumerate(saved_plans):
        ranking.append({
            "rank": plan["rank"] if isinstance(plan, dict) else plan.rank,
            "plan_no": plan["plan_no"] if isinstance(plan, dict) else plan.plan_no,
            "container_name": plan["container_name"] if isinstance(plan, dict) else plan.container_name,
            "score": plan["score"] if isinstance(plan, dict) else plan.score,
            "volume_utilization": plan["volume_utilization"] if isinstance(plan, dict) else plan.volume_utilization,
            "placed_count": plan["placed_count"] if isinstance(plan, dict) else plan.placed_count,
            "recommendation": plan["recommendation"] if isinstance(plan, dict) else plan.recommendation,
        })

    best_plan = saved_plans[0] if saved_plans else None
    if best_plan:
        if isinstance(best_plan, dict):
            recommendation = best_plan["recommendation"]
            container_name = best_plan["container_name"]
        else:
            recommendation = best_plan.recommendation
            container_name = best_plan.container_name
        overall_recommendation = f"推荐使用 {container_name}，{recommendation}"
    else:
        overall_recommendation = "无可用方案"

    return {
        "comparison_id": comparison_id,
        "plans": saved_plans,
        "ranking": ranking,
        "recommendation": overall_recommendation
    }


@app.post("/packing/{container_id}", response_model=schemas.PackingResult)
def calculate_packing(container_id: int, cargo_ids: List[int], save: bool = False, db: Session = Depends(get_db)):
    container = crud.get_container(db, container_id=container_id)
    if container is None:
        raise HTTPException(status_code=404, detail="集装箱不存在")

    boxes = []
    total_cargos = 0
    for cargo_id in cargo_ids:
        cargo = crud.get_cargo(db, cargo_id=cargo_id)
        if cargo is None:
            raise HTTPException(status_code=404, detail=f"货物 ID {cargo_id} 不存在")
        total_cargos += cargo.quantity
        for i in range(cargo.quantity):
            boxes.append(Box(
                cargo_id=cargo.id,
                cargo_name=cargo.name,
                length=cargo.length,
                width=cargo.width,
                height=cargo.height,
                weight=cargo.weight,
                can_rotate_horizontal=cargo.can_rotate_horizontal,
                can_flip=cargo.can_flip,
                max_top_load=cargo.max_top_load
            ))

    result = pack_boxes(
        container_length=container.length,
        container_width=container.width,
        container_height=container.height,
        container_max_weight=container.max_weight,
        boxes=boxes
    )

    if save:
        plan_data = {
            "container_id": container.id,
            "container_name": container.name,
            "total_cargos": total_cargos,
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
        }
        db_plan = crud.create_packing_plan(db, plan_data, result["placed_cargos"])
        result["plan_id"] = db_plan.id
        result["plan_no"] = db_plan.plan_no

    return {
        "container_id": container.id,
        "container_name": container.name,
        "placed_cargos": result["placed_cargos"],
        "unplaced_cargos": result["unplaced_cargos"],
        "total_weight": result["total_weight"],
        "volume_utilization": result["volume_utilization"],
        "center_of_gravity": result["center_of_gravity"],
        "cog_within_limit": result["cog_within_limit"]
    }


@app.get("/plans", response_model=List[schemas.PackingPlan])
def list_packing_plans(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    plans = crud.get_packing_plans(db, skip=skip, limit=limit)
    result = []
    for plan in plans:
        result.append({
            "id": plan.id,
            "plan_no": plan.plan_no,
            "container_id": plan.container_id,
            "container_name": plan.container_name,
            "total_cargos": plan.total_cargos,
            "placed_count": plan.placed_count,
            "unplaced_count": plan.unplaced_count,
            "total_weight": plan.total_weight,
            "volume_utilization": plan.volume_utilization,
            "cog_x": plan.cog_x,
            "cog_y": plan.cog_y,
            "cog_z": plan.cog_z,
            "cog_within_limit": plan.cog_within_limit,
            "cog_offset_x_ratio": plan.cog_offset_x_ratio,
            "cog_offset_y_ratio": plan.cog_offset_y_ratio,
            "score": plan.score,
            "rank": plan.rank,
            "recommendation": plan.recommendation,
            "created_at": plan.created_at.isoformat() if plan.created_at else ""
        })
    return result


@app.get("/plans/{plan_identifier}", response_model=schemas.PackingPlanDetail)
def get_packing_plan_detail(plan_identifier: str, db: Session = Depends(get_db)):
    plan = None
    if plan_identifier.isdigit():
        plan = crud.get_packing_plan(db, plan_id=int(plan_identifier))
    if plan is None:
        plan = crud.get_packing_plan(db, plan_no=plan_identifier)

    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")

    placed_cargos = crud.get_packed_cargos(db, plan_id=plan.id)

    return {
        "id": plan.id,
        "plan_no": plan.plan_no,
        "container_id": plan.container_id,
        "container_name": plan.container_name,
        "total_cargos": plan.total_cargos,
        "placed_count": plan.placed_count,
        "unplaced_count": plan.unplaced_count,
        "total_weight": plan.total_weight,
        "volume_utilization": plan.volume_utilization,
        "cog_x": plan.cog_x,
        "cog_y": plan.cog_y,
        "cog_z": plan.cog_z,
        "cog_within_limit": plan.cog_within_limit,
        "cog_offset_x_ratio": plan.cog_offset_x_ratio,
        "cog_offset_y_ratio": plan.cog_offset_y_ratio,
        "score": plan.score,
        "rank": plan.rank,
        "recommendation": plan.recommendation,
        "created_at": plan.created_at.isoformat() if plan.created_at else "",
        "placed_cargos": placed_cargos,
        "unplaced_cargos": []
    }


@app.delete("/plans/{plan_identifier}")
def delete_packing_plan(plan_identifier: str, db: Session = Depends(get_db)):
    plan = None
    if plan_identifier.isdigit():
        plan = crud.delete_packing_plan(db, plan_id=int(plan_identifier))
    if plan is None:
        plan = crud.delete_packing_plan(db, plan_no=plan_identifier)

    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")
    return {"message": "删除成功", "plan_no": plan.plan_no}
