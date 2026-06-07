from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid

from app.database import engine, get_db, Base
from app import models, schemas, crud
from app.packing.algorithm import pack_boxes, Box, rank_plans
from app.packing.visualizer import render_three_views, CARGO_COLORS
from app.packing.sequence_engine import generate_packing_sequence, get_step_snapshot
from app.packing.split_engine import split_cargos_into_boxes, ContainerSpec

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
            db_plan = crud.create_packing_plan(db, plan_data, plan_info["placed_cargos"], plan_info["unplaced_cargos"])
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
                "created_at": db_plan.created_at.isoformat() if db_plan.created_at else "",
                "unplaced_cargos": plan_info["unplaced_cargos"]
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

    split_result = None
    if request.enable_split:
        container_specs = []
        for container_id in container_ids:
            container = crud.get_container(db, container_id=container_id)
            if container:
                container_specs.append(ContainerSpec(
                    id=container.id,
                    name=container.name,
                    length=container.length,
                    width=container.width,
                    height=container.height,
                    max_weight=container.max_weight
                ))

        split_result = split_cargos_into_boxes(boxes, container_specs)

    return {
        "comparison_id": comparison_id,
        "plans": saved_plans,
        "ranking": ranking,
        "recommendation": overall_recommendation,
        "split_result": split_result
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

    plan_id = None
    plan_no = None
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
        db_plan = crud.create_packing_plan(db, plan_data, result["placed_cargos"], result["unplaced_cargos"])
        plan_id = db_plan.id
        plan_no = db_plan.plan_no

    return {
        "container_id": container.id,
        "container_name": container.name,
        "placed_cargos": result["placed_cargos"],
        "unplaced_cargos": result["unplaced_cargos"],
        "total_weight": result["total_weight"],
        "volume_utilization": result["volume_utilization"],
        "center_of_gravity": result["center_of_gravity"],
        "cog_within_limit": result["cog_within_limit"],
        "plan_id": plan_id,
        "plan_no": plan_no
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
    unplaced_cargos = crud.get_unplaced_cargos(db, plan_id=plan.id)

    unplaced_list = []
    for uc in unplaced_cargos:
        unplaced_list.append({
            "cargo_id": uc.cargo_id,
            "cargo_name": uc.cargo_name,
            "reason": uc.reason
        })

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
        "unplaced_cargos": unplaced_list
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


def _get_plan_and_cargos(plan_identifier: str, db: Session):
    plan = None
    if plan_identifier.isdigit():
        plan = crud.get_packing_plan(db, plan_id=int(plan_identifier))
    if plan is None:
        plan = crud.get_packing_plan(db, plan_no=plan_identifier)

    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")

    container = crud.get_container(db, container_id=plan.container_id)
    if container is None:
        raise HTTPException(status_code=404, detail="集装箱信息不存在")

    packed_cargos = crud.get_packed_cargos(db, plan_id=plan.id)
    placed_cargos = []
    for pc in packed_cargos:
        placed_cargos.append({
            "cargo_id": pc.cargo_id,
            "cargo_name": pc.cargo_name,
            "x": pc.x,
            "y": pc.y,
            "z": pc.z,
            "length": pc.length,
            "width": pc.width,
            "height": pc.height,
            "weight": pc.weight,
            "orientation": pc.orientation
        })

    return plan, container, placed_cargos


@app.get("/plans/{plan_identifier}/views", response_model=schemas.ThreeViewsResponse)
def get_packing_views(
    plan_identifier: str,
    view_width: int = 500,
    db: Session = Depends(get_db)
):
    plan, container, placed_cargos = _get_plan_and_cargos(plan_identifier, db)

    views = render_three_views(
        container_length=container.length,
        container_width=container.width,
        container_height=container.height,
        placed_cargos=placed_cargos,
        view_width=view_width
    )

    cargo_colors = []
    for idx, cargo in enumerate(placed_cargos):
        color_idx = idx % len(CARGO_COLORS)
        cargo_colors.append({
            "idx": idx,
            "cargo_id": cargo["cargo_id"],
            "cargo_name": cargo["cargo_name"],
            "color": CARGO_COLORS[color_idx],
            "label": str(idx + 1)
        })

    return {
        "plan_id": plan.id,
        "plan_no": plan.plan_no,
        "container_name": plan.container_name,
        "container_length": container.length,
        "container_width": container.width,
        "container_height": container.height,
        "top_view": views["top_view"],
        "front_view": views["front_view"],
        "side_view": views["side_view"],
        "cargo_count": len(placed_cargos),
        "cargo_colors": cargo_colors
    }


@app.get("/plans/{plan_identifier}/sequence", response_model=schemas.PackingSequenceResponse)
def get_packing_sequence(
    plan_identifier: str,
    max_cog_offset: float = 0.20,
    db: Session = Depends(get_db)
):
    plan, container, placed_cargos = _get_plan_and_cargos(plan_identifier, db)

    sequence_result = generate_packing_sequence(
        container_length=container.length,
        container_width=container.width,
        container_height=container.height,
        placed_cargos=placed_cargos,
        max_cog_offset_ratio=max_cog_offset
    )

    return {
        "plan_id": plan.id,
        "plan_no": plan.plan_no,
        "total_steps": sequence_result["total_steps"],
        "cargo_count": sequence_result["cargo_count"],
        "all_placed": sequence_result["all_placed"],
        "all_steps_within_limit": sequence_result["all_steps_within_limit"],
        "max_cog_offset_ratio": sequence_result["max_cog_offset_ratio"],
        "final_cog": sequence_result["final_cog"],
        "final_cog_within_limit": sequence_result["final_cog_within_limit"],
        "final_cog_offset_x_ratio": sequence_result["final_cog_offset_x_ratio"],
        "final_cog_offset_y_ratio": sequence_result["final_cog_offset_y_ratio"],
        "sequence": sequence_result["sequence"]
    }


@app.get("/plans/{plan_identifier}/snapshot/{step}", response_model=schemas.StepSnapshotResponse)
def get_packing_snapshot(
    plan_identifier: str,
    step: int,
    view_width: int = 500,
    max_cog_offset: float = 0.20,
    db: Session = Depends(get_db)
):
    plan, container, placed_cargos = _get_plan_and_cargos(plan_identifier, db)

    sequence_result = generate_packing_sequence(
        container_length=container.length,
        container_width=container.width,
        container_height=container.height,
        placed_cargos=placed_cargos,
        max_cog_offset_ratio=max_cog_offset
    )

    snapshot = get_step_snapshot(
        container_length=container.length,
        container_width=container.width,
        container_height=container.height,
        placed_cargos=placed_cargos,
        sequence_result=sequence_result,
        step_number=step
    )

    views = render_three_views(
        container_length=container.length,
        container_width=container.width,
        container_height=container.height,
        placed_cargos=snapshot["placed_cargos"],
        view_width=view_width
    )

    return {
        "plan_id": plan.id,
        "plan_no": plan.plan_no,
        "step": snapshot["step"],
        "total_steps": snapshot["total_steps"],
        "placed_count": snapshot["placed_count"],
        "placed_cargos": snapshot["placed_cargos"],
        "cog": snapshot["cog"],
        "cog_within_limit": snapshot["cog_within_limit"],
        "cog_offset_x_ratio": snapshot["cog_offset_x_ratio"],
        "cog_offset_y_ratio": snapshot["cog_offset_y_ratio"],
        "last_placed": snapshot["last_placed"],
        "top_view": views["top_view"],
        "front_view": views["front_view"],
        "side_view": views["side_view"]
    }
