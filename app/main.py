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
from app.packing.stowage_report_engine import generate_stowage_report
from app.packing.trailer_cog_engine import (
    TrailerSpec, BoxSpec, PlacedBox,
    optimize_box_positions, generate_unload_sequence
)
from app.compliance_engine import (
    run_full_compliance_audit,
    generate_customs_documents,
    build_document_items,
    generate_packing_list_content,
    generate_clc_content,
)
from app.unloading_simulation_engine import run_unloading_simulation
from app.cost_allocation_engine import (
    calculate_and_allocate_for_plan,
    get_calculation_detail,
    compare_rate_schemes_for_plan,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="集装箱三维配载计算服务", version="1.4.0")

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
    crud.create_default_trailers(db)
    crud.create_demo_trailer_scenarios(db)
    crud.create_default_hazard_matrix(db)
    crud.create_demo_hazard_cargos(db)
    crud.create_demo_temperature_cargos(db)
    crud.init_plan_hash_and_version(db)
    crud.create_demo_review_record(db)
    crud.create_demo_unloading_routes(db)
    crud.create_default_rate_schemes(db)
    crud.create_demo_damage_claim(db)
    crud.create_default_alert_rules_and_demo_event(db)


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
    try:
        return crud.create_cargo(db=db, cargo=cargo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/cargos/{cargo_id}", response_model=schemas.Cargo)
def update_cargo(cargo_id: int, cargo_update: schemas.CargoUpdate, db: Session = Depends(get_db)):
    try:
        cargo = crud.update_cargo(db, cargo_id=cargo_id, cargo_update=cargo_update)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
        raw_temp = getattr(cargo, 'temperature_class', 'AMBIENT') or 'AMBIENT'
        temp_class = raw_temp.value if hasattr(raw_temp, 'value') else raw_temp
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
                max_top_load=cargo.max_top_load,
                temperature_class=temp_class
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
        raw_temp = getattr(cargo, 'temperature_class', 'AMBIENT') or 'AMBIENT'
        temp_class = raw_temp.value if hasattr(raw_temp, 'value') else raw_temp
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


@app.get("/trailers", response_model=List[schemas.Trailer])
def list_trailers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    trailers = crud.get_trailers(db, skip=skip, limit=limit)
    return trailers


@app.get("/trailers/{trailer_id}", response_model=schemas.Trailer)
def get_trailer(trailer_id: int, db: Session = Depends(get_db)):
    trailer = crud.get_trailer(db, trailer_id=trailer_id)
    if trailer is None:
        raise HTTPException(status_code=404, detail="拖车不存在")
    return trailer


@app.post("/trailers", response_model=schemas.Trailer)
def create_trailer(trailer: schemas.TrailerCreate, db: Session = Depends(get_db)):
    return crud.create_trailer(db=db, trailer=trailer)


@app.delete("/trailers/{trailer_id}")
def delete_trailer(trailer_id: int, db: Session = Depends(get_db)):
    trailer = crud.delete_trailer(db, trailer_id=trailer_id)
    if trailer is None:
        raise HTTPException(status_code=404, detail="拖车不存在")
    return {"message": "删除成功"}


@app.post("/trailer/optimize", response_model=schemas.TrailerLoadOptimizationResult)
def optimize_trailer_load(
    request: schemas.TrailerLoadRequest,
    save: bool = True,
    db: Session = Depends(get_db)
):
    trailer = crud.get_trailer(db, trailer_id=request.trailer_id)
    if trailer is None:
        raise HTTPException(status_code=404, detail="拖车不存在")

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
    for box in request.boxes:
        box_specs.append(BoxSpec(
            box_id=box.box_id,
            box_name=box.box_name,
            length=box.length,
            width=box.width,
            weight=box.weight,
            cog_offset_x=box.cog_offset_x
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

    plan_id = None
    plan_no = None
    if save:
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
            "recommendation": opt_result["recommendation"]
        }
        db_plan = crud.create_trailer_load_plan(
            db, plan_data,
            opt_result["loaded_boxes"],
            unload_result["sequence"]
        )
        plan_id = db_plan.id
        plan_no = db_plan.plan_no

    return {
        "plan_id": plan_id,
        "plan_no": plan_no,
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
        "recommendation": opt_result["recommendation"],
        "loaded_boxes": opt_result["loaded_boxes"],
        "unload_sequence": unload_result["sequence"],
        "all_steps_valid": unload_result["all_steps_valid"],
        "invalid_steps_count": unload_result["invalid_steps_count"]
    }


@app.get("/trailer/plans", response_model=List[schemas.TrailerLoadPlan])
def list_trailer_plans(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    plans = crud.get_trailer_load_plans(db, skip=skip, limit=limit)
    result = []
    for plan in plans:
        result.append({
            "id": plan.id,
            "plan_no": plan.plan_no,
            "trailer_id": plan.trailer_id,
            "trailer_name": plan.trailer_name,
            "total_boxes": plan.total_boxes,
            "total_weight": plan.total_weight,
            "front_axle_load": plan.front_axle_load,
            "rear_axle_load": plan.rear_axle_load,
            "front_axle_load_ratio": plan.front_axle_load_ratio,
            "rear_axle_load_ratio": plan.rear_axle_load_ratio,
            "axles_within_limit": plan.axles_within_limit,
            "left_right_balance_ratio": plan.left_right_balance_ratio,
            "left_right_within_limit": plan.left_right_within_limit,
            "cog_x": plan.cog_x,
            "cog_y": plan.cog_y,
            "score": plan.score,
            "recommendation": plan.recommendation,
            "created_at": plan.created_at.isoformat() if plan.created_at else ""
        })
    return result


@app.get("/trailer/plans/{plan_identifier}", response_model=schemas.TrailerLoadPlanDetail)
def get_trailer_plan_detail(plan_identifier: str, db: Session = Depends(get_db)):
    plan = None
    if plan_identifier.isdigit():
        plan = crud.get_trailer_load_plan(db, plan_id=int(plan_identifier))
    if plan is None:
        plan = crud.get_trailer_load_plan(db, plan_no=plan_identifier)

    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")

    loaded_boxes = crud.get_trailer_loaded_boxes(db, plan_id=plan.id)
    unload_steps = crud.get_unload_steps(db, plan_id=plan.id)

    loaded_boxes_list = []
    for lb in loaded_boxes:
        loaded_boxes_list.append({
            "box_id": lb.box_id,
            "box_name": lb.box_name,
            "x": lb.x,
            "y": lb.y,
            "length": lb.length,
            "width": lb.width,
            "weight": lb.weight,
            "cog_offset_x": lb.cog_offset_x
        })

    unload_sequence_list = []
    for step in unload_steps:
        unload_sequence_list.append({
            "step_number": step.step_number,
            "box_id": step.box_id,
            "box_name": step.box_name,
            "front_axle_load_before": step.front_axle_load_before,
            "rear_axle_load_before": step.rear_axle_load_before,
            "front_axle_load_after": step.front_axle_load_after,
            "rear_axle_load_after": step.rear_axle_load_after,
            "left_weight_before": step.left_weight_before,
            "right_weight_before": step.right_weight_before,
            "left_right_ratio_before": step.left_right_ratio_before,
            "left_right_within_limit_before": step.left_right_within_limit_before,
            "axles_within_limit_before": step.axles_within_limit_before
        })

    return {
        "id": plan.id,
        "plan_no": plan.plan_no,
        "trailer_id": plan.trailer_id,
        "trailer_name": plan.trailer_name,
        "total_boxes": plan.total_boxes,
        "total_weight": plan.total_weight,
        "front_axle_load": plan.front_axle_load,
        "rear_axle_load": plan.rear_axle_load,
        "front_axle_load_ratio": plan.front_axle_load_ratio,
        "rear_axle_load_ratio": plan.rear_axle_load_ratio,
        "axles_within_limit": plan.axles_within_limit,
        "left_right_balance_ratio": plan.left_right_balance_ratio,
        "left_right_within_limit": plan.left_right_within_limit,
        "cog_x": plan.cog_x,
        "cog_y": plan.cog_y,
        "score": plan.score,
        "recommendation": plan.recommendation,
        "created_at": plan.created_at.isoformat() if plan.created_at else "",
        "loaded_boxes": loaded_boxes_list,
        "unload_sequence": unload_sequence_list
    }


@app.delete("/trailer/plans/{plan_identifier}")
def delete_trailer_plan(plan_identifier: str, db: Session = Depends(get_db)):
    plan = None
    if plan_identifier.isdigit():
        plan = crud.delete_trailer_load_plan(db, plan_id=int(plan_identifier))
    if plan is None:
        plan = crud.delete_trailer_load_plan(db, plan_no=plan_identifier)

    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")
    return {"message": "删除成功", "plan_no": plan.plan_no}


def _resolve_packing_plan(plan_identifier: str, db: Session):
    plan = None
    if plan_identifier.isdigit():
        plan = crud.get_packing_plan(db, plan_id=int(plan_identifier))
    if plan is None:
        plan = crud.get_packing_plan(db, plan_no=plan_identifier)
    return plan


@app.get("/hazard/matrix", response_model=List[schemas.HazardSegregationMatrix])
def list_hazard_matrix(db: Session = Depends(get_db)):
    items = crud.get_all_hazard_matrix(db)
    result = []
    for m in items:
        result.append({
            "id": m.id,
            "class_a": m.class_a,
            "class_b": m.class_b,
            "min_distance_mm": m.min_distance_mm,
            "segregation_level": m.segregation_level,
            "description": m.description,
            "is_active": m.is_active,
            "created_at": m.created_at.isoformat() if m.created_at else "",
        })
    return result


@app.post("/hazard/matrix", response_model=schemas.HazardSegregationMatrix)
def add_hazard_matrix_entry(entry: schemas.HazardSegregationMatrixCreate, db: Session = Depends(get_db)):
    existing = crud.get_hazard_matrix(db, entry.class_a, entry.class_b)
    if existing:
        raise HTTPException(status_code=400, detail=f"{entry.class_a}类与{entry.class_b}类的隔离规则已存在(id={existing.id})")
    db_entry = crud.create_hazard_matrix(db, entry.model_dump())
    return {
        "id": db_entry.id,
        "class_a": db_entry.class_a,
        "class_b": db_entry.class_b,
        "min_distance_mm": db_entry.min_distance_mm,
        "segregation_level": db_entry.segregation_level,
        "description": db_entry.description,
        "is_active": db_entry.is_active,
        "created_at": db_entry.created_at.isoformat() if db_entry.created_at else "",
    }


@app.put("/plans/{plan_identifier}/meta")
def update_plan_metadata(
    plan_identifier: str,
    meta: schemas.PackingPlanMetaUpdate,
    db: Session = Depends(get_db)
):
    plan = _resolve_packing_plan(plan_identifier, db)
    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")
    updated = crud.update_packing_plan_meta(db, plan.id, meta.model_dump())
    return {
        "message": "更新成功",
        "plan_id": updated.id,
        "plan_no": updated.plan_no,
        "new_version": updated.version,
        "container_no": updated.container_no,
        "seal_no": updated.seal_no,
        "declared_weight": updated.declared_weight,
        "content_hash": updated.content_hash,
    }


@app.post("/compliance/audit", response_model=schemas.ComplianceAuditDetail)
def run_compliance_audit(request: schemas.ComplianceAuditRequest, db: Session = Depends(get_db)):
    plan = _resolve_packing_plan(request.plan_identifier, db)
    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")
    result = run_full_compliance_audit(db, plan.id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    audit = crud.get_compliance_audit(db, audit_id=result["audit_id"])
    return {
        "id": audit.id,
        "audit_no": audit.audit_no,
        "plan_id": audit.plan_id,
        "plan_no": plan.plan_no,
        "container_name": plan.container_name,
        "plan_version": audit.plan_version,
        "plan_content_hash": audit.plan_content_hash,
        "is_passed": audit.is_passed,
        "hazard_check_passed": audit.hazard_check_passed,
        "weight_check_passed": audit.weight_check_passed,
        "name_check_passed": audit.name_check_passed,
        "temperature_check_passed": audit.temperature_check_passed,
        "hazard_violations": audit.hazard_violations,
        "weight_violations": audit.weight_violations,
        "name_violations": audit.name_violations,
        "temperature_violations": audit.temperature_violations,
        "temperature_violations_count": len(audit.temperature_violations) if audit.temperature_violations else 0,
        "audit_details": audit.audit_details,
        "auditor": audit.auditor,
        "remarks": audit.remarks,
        "audited_at": audit.audited_at.isoformat() if audit.audited_at else "",
    }


@app.get("/compliance/audits")
def list_audits(plan_identifier: Optional[str] = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    if plan_identifier:
        plan = _resolve_packing_plan(plan_identifier, db)
        if plan is None:
            raise HTTPException(status_code=404, detail="方案不存在")
        audits = crud.get_audits_by_plan(db, plan.id)
    else:
        audits = db.query(models.ComplianceAudit).order_by(
            models.ComplianceAudit.audited_at.desc()
        ).offset(skip).limit(limit).all()
    result = []
    for a in audits:
        plan = crud.get_packing_plan(db, plan_id=a.plan_id)
        result.append({
            "id": a.id,
            "audit_no": a.audit_no,
            "plan_id": a.plan_id,
            "plan_no": plan.plan_no if plan else "",
            "plan_version": a.plan_version,
            "is_passed": a.is_passed,
            "hazard_violations_count": len(a.hazard_violations) if a.hazard_violations else 0,
            "weight_violations_count": len(a.weight_violations) if a.weight_violations else 0,
            "name_violations_count": len(a.name_violations) if a.name_violations else 0,
            "temperature_violations_count": len(a.temperature_violations) if a.temperature_violations else 0,
            "hazard_check_passed": a.hazard_check_passed,
            "weight_check_passed": a.weight_check_passed,
            "name_check_passed": a.name_check_passed,
            "temperature_check_passed": a.temperature_check_passed,
            "remarks": a.remarks,
            "audited_at": a.audited_at.isoformat() if a.audited_at else "",
        })
    return result


@app.get("/compliance/audits/{audit_identifier}")
def get_audit_detail(audit_identifier: str, db: Session = Depends(get_db)):
    audit = None
    if audit_identifier.isdigit():
        audit = crud.get_compliance_audit(db, audit_id=int(audit_identifier))
    if audit is None:
        audit = crud.get_compliance_audit(db, audit_no=audit_identifier)
    if audit is None:
        raise HTTPException(status_code=404, detail="审计记录不存在")
    plan = crud.get_packing_plan(db, plan_id=audit.plan_id)
    return {
        "id": audit.id,
        "audit_no": audit.audit_no,
        "plan_id": audit.plan_id,
        "plan_no": plan.plan_no if plan else "",
        "container_name": plan.container_name if plan else "",
        "plan_version": audit.plan_version,
        "plan_content_hash": audit.plan_content_hash,
        "is_passed": audit.is_passed,
        "hazard_check_passed": audit.hazard_check_passed,
        "weight_check_passed": audit.weight_check_passed,
        "name_check_passed": audit.name_check_passed,
        "temperature_check_passed": audit.temperature_check_passed,
        "hazard_violations": audit.hazard_violations,
        "weight_violations": audit.weight_violations,
        "name_violations": audit.name_violations,
        "temperature_violations": audit.temperature_violations,
        "temperature_violations_count": len(audit.temperature_violations) if audit.temperature_violations else 0,
        "audit_details": audit.audit_details,
        "auditor": audit.auditor,
        "remarks": audit.remarks,
        "audited_at": audit.audited_at.isoformat() if audit.audited_at else "",
    }


@app.post("/customs/documents/generate")
def generate_documents(request: schemas.CustomsDocumentGenerateRequest, db: Session = Depends(get_db)):
    plan = _resolve_packing_plan(request.plan_identifier, db)
    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")
    result = generate_customs_documents(
        db=db,
        plan_id=plan.id,
        document_type=request.document_type,
        issued_by=request.issued_by,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@app.get("/customs/documents")
def list_documents(
    document_no: Optional[str] = None,
    document_type: Optional[str] = None,
    plan_identifier: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    if document_no:
        doc = crud.get_customs_document(db, document_no=document_no)
        if not doc:
            return []
        plan = crud.get_packing_plan(db, plan_id=doc.plan_id)
        return [{
            "id": doc.id,
            "document_no": doc.document_no,
            "document_type": doc.document_type,
            "plan_id": doc.plan_id,
            "plan_no": plan.plan_no if plan else "",
            "plan_version": doc.plan_version,
            "container_no": doc.container_no,
            "seal_no": doc.seal_no,
            "status": doc.status,
            "total_packages": doc.total_packages,
            "total_weight_kg": doc.total_weight_kg,
            "total_volume_cbm": doc.total_volume_cbm,
            "issued_by": doc.issued_by,
            "issued_at": doc.issued_at.isoformat() if doc.issued_at else "",
            "void_reason": doc.void_reason,
        }]

    if plan_identifier:
        plan = _resolve_packing_plan(plan_identifier, db)
        if plan is None:
            raise HTTPException(status_code=404, detail="方案不存在")
        docs = crud.get_documents_by_plan(db, plan.id, document_type, status)
    else:
        docs = crud.list_customs_documents(db, skip, limit, document_type, status)

    result = []
    for doc in docs:
        plan = crud.get_packing_plan(db, plan_id=doc.plan_id)
        result.append({
            "id": doc.id,
            "document_no": doc.document_no,
            "document_type": doc.document_type,
            "plan_id": doc.plan_id,
            "plan_no": plan.plan_no if plan else "",
            "plan_version": doc.plan_version,
            "container_no": doc.container_no,
            "seal_no": doc.seal_no,
            "status": doc.status,
            "total_packages": doc.total_packages,
            "total_weight_kg": doc.total_weight_kg,
            "total_volume_cbm": doc.total_volume_cbm,
            "issued_by": doc.issued_by,
            "issued_at": doc.issued_at.isoformat() if doc.issued_at else "",
            "void_reason": doc.void_reason,
        })
    return result


@app.get("/customs/documents/{doc_identifier}", response_model=schemas.CustomsDocumentDetail)
def get_document_detail(doc_identifier: str, db: Session = Depends(get_db)):
    doc = None
    if doc_identifier.isdigit():
        doc = crud.get_customs_document(db, doc_id=int(doc_identifier))
    if doc is None:
        doc = crud.get_customs_document(db, document_no=doc_identifier)
    if doc is None:
        raise HTTPException(status_code=404, detail="单据不存在")
    plan = crud.get_packing_plan(db, plan_id=doc.plan_id)
    items = crud.get_document_items(db, doc.id)
    items_list = []
    for it in items:
        items_list.append({
            "id": it.id,
            "document_id": it.document_id,
            "item_no": it.item_no,
            "cargo_id": it.cargo_id,
            "cargo_name": it.cargo_name,
            "declared_name": it.declared_name,
            "package_count": it.package_count,
            "package_type": it.package_type,
            "weight_kg": it.weight_kg,
            "declared_weight_kg": it.declared_weight_kg,
            "length_mm": it.length_mm,
            "width_mm": it.width_mm,
            "height_mm": it.height_mm,
            "volume_cbm": it.volume_cbm,
            "x_mm": it.x_mm,
            "y_mm": it.y_mm,
            "z_mm": it.z_mm,
            "stack_layer": it.stack_layer,
            "hazard_class": it.hazard_class,
            "marks_and_numbers": it.marks_and_numbers,
            "hs_code": it.hs_code,
        })
    return {
        "id": doc.id,
        "document_no": doc.document_no,
        "document_type": doc.document_type,
        "plan_id": doc.plan_id,
        "plan_no": plan.plan_no if plan else "",
        "container_name": plan.container_name if plan else "",
        "plan_version": doc.plan_version,
        "plan_content_hash": doc.plan_content_hash,
        "audit_id": doc.audit_id,
        "status": doc.status,
        "superseded_by": doc.superseded_by,
        "container_no": doc.container_no,
        "seal_no": doc.seal_no,
        "total_packages": doc.total_packages,
        "total_weight_kg": doc.total_weight_kg,
        "total_volume_cbm": doc.total_volume_cbm,
        "cog_offset_ratio": doc.cog_offset_ratio,
        "volume_utilization": doc.volume_utilization,
        "weight_utilization": doc.weight_utilization,
        "document_content": doc.document_content,
        "issued_by": doc.issued_by,
        "original_customs_declaration_no": doc.original_customs_declaration_no,
        "issued_at": doc.issued_at.isoformat() if doc.issued_at else "",
        "voided_at": doc.voided_at.isoformat() if doc.voided_at else "",
        "void_reason": doc.void_reason,
        "original_hauler_signature": doc.original_hauler_signature,
        "document_items": items_list,
    }


@app.post("/customs/documents/{doc_identifier}/void")
def void_document(doc_identifier: str, request: schemas.CustomsDocumentVoidRequest, db: Session = Depends(get_db)):
    doc = None
    if doc_identifier.isdigit():
        doc = crud.get_customs_document(db, doc_id=int(doc_identifier))
    if doc is None:
        doc = crud.get_customs_document(db, document_no=doc_identifier)
    if doc is None:
        raise HTTPException(status_code=404, detail="单据不存在")
    if doc.status not in ("valid", "outdated"):
        raise HTTPException(status_code=400, detail=f"当前单据状态({doc.status})不允许作废操作")
    voided = crud.void_customs_document(db, doc.id, request.reason)
    return {
        "message": "单据已作废",
        "document_id": voided.id,
        "document_no": voided.document_no,
        "status": voided.status,
        "void_reason": voided.void_reason,
        "voided_at": voided.voided_at.isoformat() if voided.voided_at else "",
    }


@app.post("/customs/documents/{doc_identifier}/reissue")
def reissue_document(doc_identifier: str, request: schemas.CustomsDocumentReissueRequest, db: Session = Depends(get_db)):
    doc = None
    if doc_identifier.isdigit():
        doc = crud.get_customs_document(db, doc_id=int(doc_identifier))
    if doc is None:
        doc = crud.get_customs_document(db, document_no=doc_identifier)
    if doc is None:
        raise HTTPException(status_code=404, detail="单据不存在")
    if doc.status == "superseded":
        raise HTTPException(status_code=400, detail="该单据已被重开过，不允许再次重开")

    plan = crud.get_packing_plan(db, plan_id=doc.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="关联方案不存在")

    current_hash = crud.compute_plan_content_hash(db, plan.id)
    hash_changed = doc.plan_content_hash != current_hash
    if hash_changed:
        plan.version = (plan.version or 1) + 1
        plan.content_hash = current_hash
        db.commit()
        db.refresh(plan)

    latest_audit = crud.get_latest_passed_audit(db, plan.id)
    need_new_audit = (
        latest_audit is None
        or latest_audit.plan_version != plan.version
        or latest_audit.plan_content_hash != plan.content_hash
    )
    if need_new_audit:
        audit_result = run_full_compliance_audit(db, plan.id, auditor=request.issued_by)
        if not audit_result.get("is_passed", False):
            raise HTTPException(status_code=400, detail={
                "error": "合规校验未通过，无法重开发单",
                "audit_result": audit_result
            })
        latest_audit = crud.get_compliance_audit(db, audit_id=audit_result["audit_id"])

    container = crud.get_container(db, container_id=plan.container_id)
    items, summary = build_document_items(db, plan.id)
    container_no = plan.container_no
    seal_no = plan.seal_no
    doc_header = {
        "container_no": container_no,
        "seal_no": seal_no,
        "issued_by": request.issued_by,
    }

    if doc.document_type == "PACKING_LIST":
        content = generate_packing_list_content(plan, container, items, summary, container_no, seal_no, request.issued_by)
    else:
        content = generate_clc_content(plan, container, items, summary, container_no, seal_no, request.issued_by)

    new_doc = crud.reissue_customs_document(
        db=db,
        old_doc_id=doc.id,
        reason=request.reason,
        audit_id=latest_audit.id,
        doc_header=doc_header,
        doc_summary=summary,
        document_content=content,
        document_items=items,
        new_plan_version=plan.version,
        new_plan_hash=plan.content_hash,
    )
    if new_doc is None:
        raise HTTPException(status_code=500, detail="重开失败")
    content["document_no_ref"] = new_doc.document_no
    db.query(models.CustomsDocument).filter(models.CustomsDocument.id == new_doc.id).update(
        {"document_content": content}
    )
    db.commit()
    db.refresh(new_doc)

    return {
        "message": "单据重开成功",
        "old_document": {
            "document_no": doc.document_no,
            "status": doc.status,
            "void_reason": doc.void_reason,
        },
        "new_document": {
            "document_id": new_doc.id,
            "document_no": new_doc.document_no,
            "document_type": new_doc.document_type,
            "plan_version": new_doc.plan_version,
            "status": new_doc.status,
            "total_packages": new_doc.total_packages,
            "total_weight_kg": new_doc.total_weight_kg,
            "issued_at": new_doc.issued_at.isoformat() if new_doc.issued_at else "",
        }
    }


@app.post("/stowage/report/generate", response_model=schemas.StowageReportDetail)
def generate_stowage_report_api(
    plan_identifier: str,
    db: Session = Depends(get_db)
):
    plan = None
    if plan_identifier.isdigit():
        plan = crud.get_packing_plan(db, plan_id=int(plan_identifier))
    if plan is None:
        plan = crud.get_packing_plan(db, plan_no=plan_identifier)

    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")

    packed_cargos_db = crud.get_packed_cargos(db, plan_id=plan.id)
    if not packed_cargos_db:
        raise HTTPException(status_code=400, detail="方案中没有已摆放的货物")

    packed_cargos_list = []
    cargo_ids_needing_fallback = set()
    for pc in packed_cargos_db:
        has_original_dims = (
            pc.original_length is not None
            and pc.original_width is not None
            and pc.original_height is not None
        )
        has_snapshot = has_original_dims

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
            "weight": pc.weight,
            "orientation": pc.orientation,
            "max_top_load": pc.max_top_load if has_snapshot else None,
            "original_length": pc.original_length if has_original_dims else None,
            "original_width": pc.original_width if has_original_dims else None,
            "original_height": pc.original_height if has_original_dims else None,
        })

        if not has_snapshot:
            cargo_ids_needing_fallback.add(pc.cargo_id)

    cargo_info_map = {}
    for cid in cargo_ids_needing_fallback:
        cargo = crud.get_cargo(db, cargo_id=cid)
        if cargo:
            cargo_info_map[cid] = {
                "max_top_load": cargo.max_top_load,
                "length": cargo.length,
                "width": cargo.width,
                "height": cargo.height
            }

    for pc in packed_cargos_list:
        cid = pc["cargo_id"]
        if pc["max_top_load"] is None and cid in cargo_info_map:
            pc["max_top_load"] = cargo_info_map[cid]["max_top_load"]
        if pc["original_length"] is None and cid in cargo_info_map:
            pc["original_length"] = cargo_info_map[cid]["length"]
            pc["original_width"] = cargo_info_map[cid]["width"]
            pc["original_height"] = cargo_info_map[cid]["height"]

    report_result = generate_stowage_report(
        plan_id=plan.id,
        plan_no=plan.plan_no,
        plan_version=plan.version or 1,
        packed_cargos=packed_cargos_list,
        cargo_info_map=cargo_info_map
    )

    summary = report_result["summary"]
    report_no = crud.generate_stowage_report_no()

    db_report = crud.create_stowage_report(db, {
        "report_no": report_no,
        "plan_id": plan.id,
        "plan_no": plan.plan_no,
        "plan_version": plan.version or 1,
        "total_cargos": summary["total_cargos"],
        "flipped_count": summary["flipped_count"],
        "warning_count": summary["warning_count"],
        "danger_count": summary["danger_count"],
        "health_score": summary["health_score"],
        "report_data": report_result,
        "summary": summary
    })

    return {
        "id": db_report.id,
        "report_no": db_report.report_no,
        "plan_id": db_report.plan_id,
        "plan_no": db_report.plan_no,
        "plan_version": db_report.plan_version,
        "total_cargos": db_report.total_cargos,
        "flipped_count": db_report.flipped_count,
        "warning_count": db_report.warning_count,
        "danger_count": db_report.danger_count,
        "health_score": db_report.health_score,
        "summary": summary,
        "created_at": db_report.created_at.isoformat() if db_report.created_at else "",
        "layers": report_result["layers"],
        "overall_health": report_result["overall_health"],
        "statistics": report_result["statistics"]
    }


@app.get("/stowage/reports")
def list_stowage_reports(
    plan_identifier: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    reports = crud.list_stowage_reports(db, skip=skip, limit=limit, plan_identifier=plan_identifier)
    result = []
    for r in reports:
        result.append({
            "id": r.id,
            "report_no": r.report_no,
            "plan_id": r.plan_id,
            "plan_no": r.plan_no,
            "plan_version": r.plan_version,
            "total_cargos": r.total_cargos,
            "flipped_count": r.flipped_count,
            "warning_count": r.warning_count,
            "danger_count": r.danger_count,
            "health_score": r.health_score,
            "summary": r.summary,
            "created_at": r.created_at.isoformat() if r.created_at else ""
        })
    return result


@app.get("/stowage/reports/{report_identifier}", response_model=schemas.StowageReportDetail)
def get_stowage_report_detail(
    report_identifier: str,
    db: Session = Depends(get_db)
):
    report = None
    if report_identifier.isdigit():
        report = crud.get_stowage_report(db, report_id=int(report_identifier))
    if report is None:
        report = crud.get_stowage_report(db, report_no=report_identifier)

    if report is None:
        raise HTTPException(status_code=404, detail="堆码报告不存在")

    report_data = report.report_data or {}

    return {
        "id": report.id,
        "report_no": report.report_no,
        "plan_id": report.plan_id,
        "plan_no": report.plan_no,
        "plan_version": report.plan_version,
        "total_cargos": report.total_cargos,
        "flipped_count": report.flipped_count,
        "warning_count": report.warning_count,
        "danger_count": report.danger_count,
        "health_score": report.health_score,
        "summary": report.summary or {},
        "created_at": report.created_at.isoformat() if report.created_at else "",
        "layers": report_data.get("layers", []),
        "overall_health": report_data.get("overall_health", {}),
        "statistics": report_data.get("statistics", {})
    }


@app.post("/review/tasks", response_model=schemas.ReviewTask)
def create_review_task(
    request: schemas.ReviewTaskCreate,
    db: Session = Depends(get_db)
):
    plan_id = request.plan_id
    plan_no = request.plan_no
    if not plan_id and not plan_no:
        raise HTTPException(status_code=400, detail="必须提供 plan_id 或 plan_no")

    plan = None
    if plan_id:
        plan = crud.get_packing_plan(db, plan_id=plan_id)
    if not plan and plan_no:
        plan = crud.get_packing_plan(db, plan_no=plan_no)

    if not plan:
        raise HTTPException(status_code=404, detail="方案不存在")

    task = crud.create_review_task(
        db,
        plan_id=plan.id,
        created_by=request.created_by,
        remarks=request.remarks,
    )
    if not task:
        raise HTTPException(status_code=500, detail="创建复核任务失败")

    stats = crud.get_review_task_stats(db, task.id)
    return {
        "id": task.id,
        "task_no": task.task_no,
        "plan_id": task.plan_id,
        "plan_no": task.plan_no,
        "plan_version": task.plan_version,
        "plan_content_hash": task.plan_content_hash,
        "status": task.status,
        "is_valid": task.is_valid,
        "invalid_reason": task.invalid_reason,
        "created_by": task.created_by,
        "created_at": task.created_at.isoformat() if task.created_at else "",
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "remarks": task.remarks,
        "total_cargos": stats["total_cargos"],
        "reviewed_count": stats["reviewed_count"],
        "discrepancy_count": stats["discrepancy_count"],
        "blocking_count": stats["blocking_count"],
    }


@app.get("/review/tasks", response_model=List[schemas.ReviewTask])
def list_review_tasks(
    plan_no: Optional[str] = None,
    status: Optional[str] = None,
    only_pending: bool = False,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    tasks = crud.list_review_tasks(
        db,
        skip=skip,
        limit=limit,
        plan_no=plan_no,
        status=status,
        only_pending=only_pending,
        only_valid=False,
    )
    result = []
    for task in tasks:
        stats = crud.get_review_task_stats(db, task.id)
        result.append({
            "id": task.id,
            "task_no": task.task_no,
            "plan_id": task.plan_id,
            "plan_no": task.plan_no,
            "plan_version": task.plan_version,
            "plan_content_hash": task.plan_content_hash,
            "status": task.status,
            "is_valid": task.is_valid,
            "invalid_reason": task.invalid_reason,
            "created_by": task.created_by,
            "created_at": task.created_at.isoformat() if task.created_at else "",
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "remarks": task.remarks,
            "total_cargos": stats["total_cargos"],
            "reviewed_count": stats["reviewed_count"],
            "discrepancy_count": stats["discrepancy_count"],
            "blocking_count": stats["blocking_count"],
        })
    return result


@app.get("/review/tasks/{task_identifier}", response_model=schemas.ReviewTaskDetail)
def get_review_task_detail(
    task_identifier: str,
    db: Session = Depends(get_db)
):
    task = None
    if task_identifier.isdigit():
        task = crud.get_review_task(db, task_id=int(task_identifier))
    if not task:
        task = crud.get_review_task(db, task_no=task_identifier)

    if not task:
        raise HTTPException(status_code=404, detail="复核任务不存在")

    cargo_records = crud.get_review_cargo_records(db, task.id)
    discrepancies = crud.get_review_discrepancies(db, task.id)
    confirmations = task.confirmations or []

    stats = crud.get_review_task_stats(db, task.id)

    cargo_records_list = []
    for rec in cargo_records:
        rec_discs = [d for d in discrepancies if d.cargo_record_id == rec.id]
        discs_list = []
        for d in rec_discs:
            discs_list.append({
                "id": d.id,
                "discrepancy_type": d.discrepancy_type,
                "severity": d.severity,
                "description": d.description,
                "details": d.details or {},
                "is_resolved": d.is_resolved,
                "is_waived": d.is_waived,
            })
        cargo_records_list.append({
            "id": rec.id,
            "task_id": rec.task_id,
            "plan_cargo_id": rec.plan_cargo_id,
            "cargo_id": rec.cargo_id,
            "cargo_name": rec.cargo_name,
            "review_status": rec.review_status,
            "plan_x": rec.plan_x,
            "plan_y": rec.plan_y,
            "plan_z": rec.plan_z,
            "plan_orientation": rec.plan_orientation,
            "plan_load_order": rec.plan_load_order,
            "actual_x": rec.actual_x,
            "actual_y": rec.actual_y,
            "actual_z": rec.actual_z,
            "actual_orientation": rec.actual_orientation,
            "actual_load_order": rec.actual_load_order,
            "loaded_at": rec.loaded_at.isoformat() if rec.loaded_at else None,
            "reviewed_by": rec.reviewed_by,
            "reviewed_at": rec.reviewed_at.isoformat() if rec.reviewed_at else None,
            "remarks": rec.remarks,
            "discrepancies": discs_list,
        })

    disc_list = []
    for d in discrepancies:
        disc_list.append({
            "id": d.id,
            "task_id": d.task_id,
            "cargo_record_id": d.cargo_record_id,
            "discrepancy_type": d.discrepancy_type,
            "severity": d.severity,
            "description": d.description,
            "details": d.details or {},
            "is_resolved": d.is_resolved,
            "resolved_by": d.resolved_by,
            "resolved_at": d.resolved_at.isoformat() if d.resolved_at else None,
            "resolution_note": d.resolution_note,
            "is_waived": d.is_waived,
            "waived_by": d.waived_by,
            "waived_at": d.waived_at.isoformat() if d.waived_at else None,
            "waive_reason": d.waive_reason,
        })

    conf_list = []
    for conf in confirmations:
        conf_list.append({
            "id": conf.id,
            "confirmation_no": conf.confirmation_no,
            "task_id": conf.task_id,
            "plan_id": conf.plan_id,
            "plan_no": conf.plan_no,
            "plan_version": conf.plan_version,
            "plan_content_hash": conf.plan_content_hash,
            "status": conf.status,
            "is_valid": conf.is_valid,
            "total_planned": conf.total_planned,
            "total_actual": conf.total_actual,
            "total_discrepancies": conf.total_discrepancies,
            "blocking_count": conf.blocking_count,
            "releasable_count": conf.releasable_count,
            "is_released": conf.is_released,
            "released_by": conf.released_by,
            "released_at": conf.released_at.isoformat() if conf.released_at else None,
            "release_reason": conf.release_reason,
            "summary_data": conf.summary_data or {},
            "created_at": conf.created_at.isoformat() if conf.created_at else None,
            "confirmed_at": conf.confirmed_at.isoformat() if conf.confirmed_at else None,
        })

    return {
        "id": task.id,
        "task_no": task.task_no,
        "plan_id": task.plan_id,
        "plan_no": task.plan_no,
        "plan_version": task.plan_version,
        "plan_content_hash": task.plan_content_hash,
        "status": task.status,
        "is_valid": task.is_valid,
        "invalid_reason": task.invalid_reason,
        "created_by": task.created_by,
        "created_at": task.created_at.isoformat() if task.created_at else "",
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "remarks": task.remarks,
        "total_cargos": stats["total_cargos"],
        "reviewed_count": stats["reviewed_count"],
        "discrepancy_count": stats["discrepancy_count"],
        "blocking_count": stats["blocking_count"],
        "cargo_records": cargo_records_list,
        "discrepancies": disc_list,
        "confirmations": conf_list,
    }


@app.post("/review/tasks/{task_identifier}/cargos", response_model=schemas.ReviewCargoRecord)
def submit_cargo_review(
    task_identifier: str,
    record: schemas.ReviewCargoRecordCreate,
    db: Session = Depends(get_db)
):
    task = None
    if task_identifier.isdigit():
        task = crud.get_review_task(db, task_id=int(task_identifier))
    if not task:
        task = crud.get_review_task(db, task_no=task_identifier)

    if not task:
        raise HTTPException(status_code=404, detail="复核任务不存在")
    if not task.is_valid:
        raise HTTPException(status_code=400, detail=f"复核任务已失效: {task.invalid_reason}")
    if task.status == "completed":
        raise HTTPException(status_code=400, detail="复核任务已完成，无法修改")

    result = crud.update_cargo_review_record(
        db,
        task_id=task.id,
        record_data=record.model_dump(),
        reviewed_by=record.reviewed_by,
    )
    if not result:
        raise HTTPException(status_code=400, detail="复核记录更新失败")

    return {
        "id": result.id,
        "task_id": result.task_id,
        "plan_cargo_id": result.plan_cargo_id,
        "cargo_id": result.cargo_id,
        "cargo_name": result.cargo_name,
        "review_status": result.review_status,
        "plan_x": result.plan_x,
        "plan_y": result.plan_y,
        "plan_z": result.plan_z,
        "plan_orientation": result.plan_orientation,
        "plan_load_order": result.plan_load_order,
        "actual_x": result.actual_x,
        "actual_y": result.actual_y,
        "actual_z": result.actual_z,
        "actual_orientation": result.actual_orientation,
        "actual_load_order": result.actual_load_order,
        "loaded_at": result.loaded_at.isoformat() if result.loaded_at else None,
        "reviewed_by": result.reviewed_by,
        "reviewed_at": result.reviewed_at.isoformat() if result.reviewed_at else None,
        "remarks": result.remarks,
        "discrepancies": [],
    }


@app.post("/review/tasks/{task_identifier}/cargos/batch")
def batch_submit_cargo_review(
    task_identifier: str,
    request: schemas.CargoReviewSubmit,
    db: Session = Depends(get_db)
):
    task = None
    if task_identifier.isdigit():
        task = crud.get_review_task(db, task_id=int(task_identifier))
    if not task:
        task = crud.get_review_task(db, task_no=task_identifier)

    if not task:
        raise HTTPException(status_code=404, detail="复核任务不存在")
    if not task.is_valid:
        raise HTTPException(status_code=400, detail=f"复核任务已失效: {task.invalid_reason}")
    if task.status == "completed":
        raise HTTPException(status_code=400, detail="复核任务已完成，无法修改")

    results = []
    for record in request.cargo_records:
        result = crud.update_cargo_review_record(
            db,
            task_id=task.id,
            record_data=record.model_dump(),
            reviewed_by=request.reviewed_by or record.reviewed_by,
        )
        if result:
            results.append({
                "id": result.id,
                "cargo_id": result.cargo_id,
                "cargo_name": result.cargo_name,
                "review_status": result.review_status,
            })

    stats = crud.get_review_task_stats(db, task.id)
    return {
        "task_id": task.id,
        "task_no": task.task_no,
        "submitted_count": len(results),
        "results": results,
        "stats": stats,
    }


@app.put("/review/discrepancies/{disc_id}/waive", response_model=schemas.ReviewDiscrepancy)
def waive_discrepancy(
    disc_id: int,
    request: schemas.ReviewDiscrepancyWaive,
    db: Session = Depends(get_db)
):
    try:
        disc = crud.waive_discrepancy(
            db,
            disc_id=disc_id,
            waive_reason=request.waive_reason,
            waived_by=request.waived_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not disc:
        raise HTTPException(status_code=404, detail="差异记录不存在")

    return {
        "id": disc.id,
        "task_id": disc.task_id,
        "cargo_record_id": disc.cargo_record_id,
        "discrepancy_type": disc.discrepancy_type,
        "severity": disc.severity,
        "description": disc.description,
        "details": disc.details or {},
        "is_resolved": disc.is_resolved,
        "resolved_by": disc.resolved_by,
        "resolved_at": disc.resolved_at.isoformat() if disc.resolved_at else None,
        "resolution_note": disc.resolution_note,
        "is_waived": disc.is_waived,
        "waived_by": disc.waived_by,
        "waived_at": disc.waived_at.isoformat() if disc.waived_at else None,
        "waive_reason": disc.waive_reason,
    }


@app.put("/review/discrepancies/{disc_id}/resolve", response_model=schemas.ReviewDiscrepancy)
def resolve_discrepancy(
    disc_id: int,
    request: schemas.ReviewDiscrepancyResolve,
    db: Session = Depends(get_db)
):
    disc = crud.resolve_discrepancy(
        db,
        disc_id=disc_id,
        resolution_note=request.resolution_note,
        resolved_by=request.resolved_by,
    )
    if not disc:
        raise HTTPException(status_code=404, detail="差异记录不存在")

    return {
        "id": disc.id,
        "task_id": disc.task_id,
        "cargo_record_id": disc.cargo_record_id,
        "discrepancy_type": disc.discrepancy_type,
        "severity": disc.severity,
        "description": disc.description,
        "details": disc.details or {},
        "is_resolved": disc.is_resolved,
        "resolved_by": disc.resolved_by,
        "resolved_at": disc.resolved_at.isoformat() if disc.resolved_at else None,
        "resolution_note": disc.resolution_note,
        "is_waived": disc.is_waived,
        "waived_by": disc.waived_by,
        "waived_at": disc.waived_at.isoformat() if disc.waived_at else None,
        "waive_reason": disc.waive_reason,
    }


@app.post("/review/tasks/{task_identifier}/complete", response_model=schemas.ReviewTaskDetail)
def complete_review_task(
    task_identifier: str,
    db: Session = Depends(get_db)
):
    task = None
    if task_identifier.isdigit():
        task = crud.get_review_task(db, task_id=int(task_identifier))
    if not task:
        task = crud.get_review_task(db, task_no=task_identifier)

    if not task:
        raise HTTPException(status_code=404, detail="复核任务不存在")

    try:
        task = crud.complete_review_task(db, task_id=task.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return get_review_task_detail(task_identifier=str(task.id), db=db)


@app.post("/review/tasks/{task_identifier}/release", response_model=schemas.LoadingConfirmationDetail)
def release_confirmation(
    task_identifier: str,
    request: schemas.ReleaseConfirmationRequest,
    db: Session = Depends(get_db)
):
    task = None
    if task_identifier.isdigit():
        task = crud.get_review_task(db, task_id=int(task_identifier))
    if not task:
        task = crud.get_review_task(db, task_no=task_identifier)

    if not task:
        raise HTTPException(status_code=404, detail="复核任务不存在")

    try:
        conf = crud.release_confirmation(
            db,
            task_id=task.id,
            released_by=request.released_by,
            release_reason=request.release_reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return get_loading_confirmation_detail(conf_identifier=str(conf.id), db=db)


@app.get("/loading-confirmations", response_model=List[schemas.LoadingConfirmation])
def list_loading_confirmations(
    plan_no: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    confs = crud.list_loading_confirmations(db, skip=skip, limit=limit, plan_no=plan_no)
    result = []
    for conf in confs:
        result.append({
            "id": conf.id,
            "confirmation_no": conf.confirmation_no,
            "task_id": conf.task_id,
            "plan_id": conf.plan_id,
            "plan_no": conf.plan_no,
            "plan_version": conf.plan_version,
            "plan_content_hash": conf.plan_content_hash,
            "status": conf.status,
            "is_valid": conf.is_valid,
            "total_planned": conf.total_planned,
            "total_actual": conf.total_actual,
            "total_discrepancies": conf.total_discrepancies,
            "blocking_count": conf.blocking_count,
            "releasable_count": conf.releasable_count,
            "is_released": conf.is_released,
            "released_by": conf.released_by,
            "released_at": conf.released_at.isoformat() if conf.released_at else None,
            "release_reason": conf.release_reason,
            "summary_data": conf.summary_data or {},
            "created_at": conf.created_at.isoformat() if conf.created_at else None,
            "confirmed_at": conf.confirmed_at.isoformat() if conf.confirmed_at else None,
        })
    return result


@app.get("/loading-confirmations/{conf_identifier}", response_model=schemas.LoadingConfirmationDetail)
def get_loading_confirmation_detail(
    conf_identifier: str,
    db: Session = Depends(get_db)
):
    conf = None
    if conf_identifier.isdigit():
        conf = crud.get_loading_confirmation(db, conf_id=int(conf_identifier))
    if not conf:
        conf = crud.get_loading_confirmation(db, confirmation_no=conf_identifier)

    if not conf:
        raise HTTPException(status_code=404, detail="实装确认单不存在")

    task = crud.get_review_task(db, task_id=conf.task_id)
    cargo_records = crud.get_review_cargo_records(db, conf.task_id) if task else []
    discrepancies = crud.get_review_discrepancies(db, conf.task_id) if task else []

    cargo_comparison = []
    for rec in cargo_records:
        cargo_comparison.append({
            "record_id": rec.id,
            "plan_cargo_id": rec.plan_cargo_id,
            "cargo_id": rec.cargo_id,
            "cargo_name": rec.cargo_name,
            "review_status": rec.review_status,
            "plan_position": {
                "x": rec.plan_x,
                "y": rec.plan_y,
                "z": rec.plan_z,
            },
            "actual_position": {
                "x": rec.actual_x,
                "y": rec.actual_y,
                "z": rec.actual_z,
            },
            "plan_orientation": rec.plan_orientation,
            "actual_orientation": rec.actual_orientation,
            "plan_load_order": rec.plan_load_order,
            "actual_load_order": rec.actual_load_order,
            "loaded_at": rec.loaded_at.isoformat() if rec.loaded_at else None,
        })

    disc_list = []
    for d in discrepancies:
        disc_list.append({
            "id": d.id,
            "task_id": d.task_id,
            "cargo_record_id": d.cargo_record_id,
            "discrepancy_type": d.discrepancy_type,
            "severity": d.severity,
            "description": d.description,
            "details": d.details or {},
            "is_resolved": d.is_resolved,
            "resolved_by": d.resolved_by,
            "resolved_at": d.resolved_at.isoformat() if d.resolved_at else None,
            "resolution_note": d.resolution_note,
            "is_waived": d.is_waived,
            "waived_by": d.waived_by,
            "waived_at": d.waived_at.isoformat() if d.waived_at else None,
            "waive_reason": d.waive_reason,
        })

    return {
        "id": conf.id,
        "confirmation_no": conf.confirmation_no,
        "task_id": conf.task_id,
        "plan_id": conf.plan_id,
        "plan_no": conf.plan_no,
        "plan_version": conf.plan_version,
        "plan_content_hash": conf.plan_content_hash,
        "status": conf.status,
        "is_valid": conf.is_valid,
        "total_planned": conf.total_planned,
        "total_actual": conf.total_actual,
        "total_discrepancies": conf.total_discrepancies,
        "blocking_count": conf.blocking_count,
        "releasable_count": conf.releasable_count,
        "is_released": conf.is_released,
        "released_by": conf.released_by,
        "released_at": conf.released_at.isoformat() if conf.released_at else None,
        "release_reason": conf.release_reason,
        "summary_data": conf.summary_data or {},
        "created_at": conf.created_at.isoformat() if conf.created_at else None,
        "confirmed_at": conf.confirmed_at.isoformat() if conf.confirmed_at else None,
        "cargo_comparison": cargo_comparison,
        "discrepancies": disc_list,
    }


@app.get("/plans/{plan_identifier}/latest-release")
def get_plan_latest_release(
    plan_identifier: str,
    db: Session = Depends(get_db)
):
    plan = None
    if plan_identifier.isdigit():
        plan = crud.get_packing_plan(db, plan_id=int(plan_identifier))
    if plan is None:
        plan = crud.get_packing_plan(db, plan_no=plan_identifier)

    if not plan:
        raise HTTPException(status_code=404, detail="方案不存在")

    conf = crud.get_latest_confirmation_by_plan(db, plan.id)
    task = crud.get_latest_review_task(db, plan.id)

    return {
        "plan_id": plan.id,
        "plan_no": plan.plan_no,
        "plan_version": plan.version,
        "latest_confirmation": {
            "id": conf.id,
            "confirmation_no": conf.confirmation_no,
            "is_valid": conf.is_valid,
            "is_released": conf.is_released,
            "released_by": conf.released_by,
            "released_at": conf.released_at.isoformat() if conf.released_at else None,
            "release_reason": conf.release_reason,
            "total_discrepancies": conf.total_discrepancies,
            "blocking_count": conf.blocking_count,
            "releasable_count": conf.releasable_count,
        } if conf else None,
        "latest_review_task": {
            "id": task.id,
            "task_no": task.task_no,
            "is_valid": task.is_valid,
            "status": task.status,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        } if task else None,
    }


def _resolve_unloading_route(route_identifier: str, db: Session):
    route = None
    if route_identifier.isdigit():
        route = crud.get_unloading_route(db, route_id=int(route_identifier))
    if route is None:
        route = crud.get_unloading_route(db, route_no=route_identifier)
    return route


def _validate_cargo_assignments(packed_cargos: list, stops: list, cargo_assignments: list):
    packed_ids = {pc.id for pc in packed_cargos}
    stop_orders = {s["stop_order"] for s in stops}

    assigned_packed_ids = set()
    for assignment in cargo_assignments:
        packed_id = assignment["packed_cargo_id"]
        if packed_id not in packed_ids:
            raise ValueError(f"货物分配引用了不存在的 packed_cargo_id: {packed_id}")
        if packed_id in assigned_packed_ids:
            raise ValueError(f"packed_cargo_id {packed_id} 被重复分配")
        assigned_packed_ids.add(packed_id)

        stop_order = assignment["stop_order"]
        if stop_order not in stop_orders:
            raise ValueError(f"货物分配引用了不存在的站点顺序: {stop_order}")

    unassigned = packed_ids - assigned_packed_ids
    if unassigned:
        raise ValueError(f"有 {len(unassigned)} 件货物未分配站点: {sorted(unassigned)[:5]}...")


@app.post("/unloading/routes", response_model=schemas.UnloadingRoute)
def create_unloading_route(
    request: schemas.UnloadingRouteCreate,
    db: Session = Depends(get_db)
):
    plan = None
    if request.plan_identifier.isdigit():
        plan = crud.get_packing_plan(db, plan_id=int(request.plan_identifier))
    if plan is None:
        plan = crud.get_packing_plan(db, plan_no=request.plan_identifier)

    if plan is None:
        raise HTTPException(status_code=404, detail="配载方案不存在")

    packed_cargos = crud.get_packed_cargos(db, plan_id=plan.id)
    if not packed_cargos:
        raise HTTPException(status_code=400, detail="配载方案中没有已装载的货物")

    try:
        _validate_cargo_assignments(packed_cargos, request.stops, request.cargo_assignments)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    stops_data = [s.model_dump() for s in request.stops]
    assignments_data = [a.model_dump() for a in request.cargo_assignments]

    route = crud.create_unloading_route(
        db,
        plan_id=plan.id,
        plan_no=plan.plan_no,
        name=request.name,
        description=request.description,
        created_by=request.created_by,
        stops=stops_data,
        cargo_assignments=assignments_data
    )

    return get_unloading_route_detail(route_identifier=str(route.id), db=db)


@app.get("/unloading/routes", response_model=List[schemas.UnloadingRouteSummary])
def list_unloading_routes(
    plan_identifier: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    plan_id = None
    if plan_identifier:
        plan = None
        if plan_identifier.isdigit():
            plan = crud.get_packing_plan(db, plan_id=int(plan_identifier))
        if plan is None:
            plan = crud.get_packing_plan(db, plan_no=plan_identifier)
        if plan is None:
            raise HTTPException(status_code=404, detail="配载方案不存在")
        plan_id = plan.id

    routes = crud.get_unloading_routes(db, plan_id=plan_id, skip=skip, limit=limit)
    result = []
    for route in routes:
        stops = crud.get_route_stops(db, route_id=route.id)
        assignments = crud.get_route_cargo_assignments(db, route_id=route.id)
        simulations = crud.get_unloading_simulations(db, route_id=route.id)
        result.append({
            "id": route.id,
            "route_no": route.route_no,
            "plan_id": route.plan_id,
            "plan_no": route.plan_no,
            "name": route.name,
            "description": route.description,
            "created_by": route.created_by,
            "created_at": route.created_at.isoformat() if route.created_at else "",
            "total_stops": len(stops),
            "total_cargos": len(assignments),
            "simulation_count": len(simulations)
        })
    return result


@app.get("/unloading/routes/{route_identifier}", response_model=schemas.UnloadingRoute)
def get_unloading_route_detail(
    route_identifier: str,
    db: Session = Depends(get_db)
):
    route = _resolve_unloading_route(route_identifier, db)
    if route is None:
        raise HTTPException(status_code=404, detail="路线不存在")

    stops = crud.get_route_stops(db, route_id=route.id)
    assignments = crud.get_route_cargo_assignments(db, route_id=route.id)

    stops_list = []
    for s in stops:
        stops_list.append({
            "id": s.id,
            "route_id": s.route_id,
            "stop_order": s.stop_order,
            "stop_name": s.stop_name,
            "stop_code": s.stop_code,
            "contact_person": s.contact_person,
            "contact_phone": s.contact_phone,
            "address": s.address
        })

    assignments_list = []
    for a in assignments:
        assignments_list.append({
            "id": a.id,
            "route_id": a.route_id,
            "packed_cargo_id": a.packed_cargo_id,
            "cargo_id": a.cargo_id,
            "cargo_name": a.cargo_name,
            "stop_id": a.stop_id,
            "stop_order": a.stop_order,
            "unload_order": a.unload_order
        })

    return {
        "id": route.id,
        "route_no": route.route_no,
        "plan_id": route.plan_id,
        "plan_no": route.plan_no,
        "name": route.name,
        "description": route.description,
        "created_by": route.created_by,
        "created_at": route.created_at.isoformat() if route.created_at else "",
        "stops": stops_list,
        "cargo_assignments": assignments_list
    }


@app.put("/unloading/routes/{route_identifier}", response_model=schemas.UnloadingRoute)
def update_unloading_route(
    route_identifier: str,
    request: schemas.UnloadingRouteUpdate,
    db: Session = Depends(get_db)
):
    route = _resolve_unloading_route(route_identifier, db)
    if route is None:
        raise HTTPException(status_code=404, detail="路线不存在")

    stops_data = None
    assignments_data = None

    if request.stops is not None:
        plan = crud.get_packing_plan(db, plan_id=route.plan_id)
        packed_cargos = crud.get_packed_cargos(db, plan_id=route.plan_id)
        if not packed_cargos:
            raise HTTPException(status_code=400, detail="配载方案中没有已装载的货物")

        assignments_for_validation = request.cargo_assignments if request.cargo_assignments is not None else [
            {
                "packed_cargo_id": a.packed_cargo_id,
                "cargo_id": a.cargo_id,
                "cargo_name": a.cargo_name,
                "stop_order": a.stop_order,
                "unload_order": a.unload_order
            }
            for a in route.cargo_assignments
        ]

        try:
            _validate_cargo_assignments(
                packed_cargos,
                [s.model_dump() for s in request.stops],
                assignments_for_validation
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        stops_data = [s.model_dump() for s in request.stops]

    if request.cargo_assignments is not None:
        assignments_data = [a.model_dump() for a in request.cargo_assignments]

    updated_route = crud.update_unloading_route(
        db,
        route_id=route.id,
        name=request.name,
        description=request.description,
        stops=stops_data,
        cargo_assignments=assignments_data
    )

    return get_unloading_route_detail(route_identifier=str(updated_route.id), db=db)


@app.delete("/unloading/routes/{route_identifier}")
def delete_unloading_route(
    route_identifier: str,
    db: Session = Depends(get_db)
):
    route = crud.delete_unloading_route(db, route_identifier if not route_identifier.isdigit() else None,
                                       int(route_identifier) if route_identifier.isdigit() else None)
    if route is None:
        raise HTTPException(status_code=404, detail="路线不存在")
    return {"message": "删除成功", "route_no": route.route_no}


@app.post("/unloading/simulations", response_model=schemas.UnloadingSimulationDetail)
def run_unloading_simulation_api(
    request: schemas.UnloadingSimulationCreate,
    db: Session = Depends(get_db)
):
    route = _resolve_unloading_route(request.route_identifier, db)
    if route is None:
        raise HTTPException(status_code=404, detail="路线不存在")

    plan = crud.get_packing_plan(db, plan_id=route.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="关联的配载方案不存在")

    packed_cargos_db = crud.get_packed_cargos(db, plan_id=plan.id)
    if not packed_cargos_db:
        raise HTTPException(status_code=400, detail="配载方案中没有已装载的货物")

    packed_cargos_list = []
    for pc in packed_cargos_db:
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

    stops_list = []
    for s in route.stops:
        stops_list.append({
            "id": s.id,
            "stop_order": s.stop_order,
            "stop_name": s.stop_name,
            "stop_code": s.stop_code
        })

    assignments_list = []
    for a in route.cargo_assignments:
        assignments_list.append({
            "packed_cargo_id": a.packed_cargo_id,
            "stop_order": a.stop_order,
            "unload_order": a.unload_order
        })

    sim_result = run_unloading_simulation(
        packed_cargos_list,
        stops_list,
        assignments_list
    )

    db_simulation = crud.create_unloading_simulation(db, route, sim_result)

    return get_simulation_detail(simulation_identifier=str(db_simulation.id), db=db)


@app.get("/unloading/simulations", response_model=List[schemas.UnloadingSimulationSummary])
def list_unloading_simulations(
    route_identifier: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    route_id = None
    if route_identifier:
        route = _resolve_unloading_route(route_identifier, db)
        if route is None:
            raise HTTPException(status_code=404, detail="路线不存在")
        route_id = route.id

    simulations = crud.get_unloading_simulations(db, route_id=route_id, skip=skip, limit=limit)
    result = []
    for sim in simulations:
        route = crud.get_unloading_route(db, route_id=sim.route_id)
        worst_stop_name = None
        deadlock_stop_name = None
        if sim.worst_stop_id:
            worst_stop = db.query(models.UnloadingRouteStop).filter(
                models.UnloadingRouteStop.id == sim.worst_stop_id
            ).first()
            if worst_stop:
                worst_stop_name = worst_stop.stop_name
        if sim.deadlock_stop_id:
            deadlock_stop = db.query(models.UnloadingRouteStop).filter(
                models.UnloadingRouteStop.id == sim.deadlock_stop_id
            ).first()
            if deadlock_stop:
                deadlock_stop_name = deadlock_stop.stop_name

        result.append({
            "id": sim.id,
            "simulation_no": sim.simulation_no,
            "route_id": sim.route_id,
            "route_no": sim.route_no,
            "route_name": route.name if route else "",
            "status": sim.status,
            "total_stops": sim.total_stops,
            "total_cargos": sim.total_cargos,
            "total_rehandle_count": sim.total_rehandle_count,
            "worst_stop_order": sim.worst_stop_order,
            "worst_stop_name": worst_stop_name,
            "worst_stop_rehandle_count": sim.worst_stop_rehandle_count,
            "has_deadlock": sim.has_deadlock,
            "deadlock_stop_order": sim.deadlock_stop_order,
            "deadlock_stop_name": deadlock_stop_name,
            "created_at": sim.created_at.isoformat() if sim.created_at else ""
        })
    return result


@app.get("/unloading/simulations/{simulation_identifier}", response_model=schemas.UnloadingSimulationDetail)
def get_simulation_detail(
    simulation_identifier: str,
    db: Session = Depends(get_db)
):
    simulation = None
    if simulation_identifier.isdigit():
        simulation = crud.get_unloading_simulation(db, simulation_id=int(simulation_identifier))
    if simulation is None:
        simulation = crud.get_unloading_simulation(db, simulation_no=simulation_identifier)

    if simulation is None:
        raise HTTPException(status_code=404, detail="推演记录不存在")

    stop_results = crud.get_simulation_stop_results(db, simulation_id=simulation.id)

    stop_results_list = []
    for sr in stop_results:
        moves_list = []
        for move in (sr.moves or []):
            moves_list.append({
                "move_type": move["move_type"],
                "packed_cargo_id": move["packed_cargo_id"],
                "cargo_id": move["cargo_id"],
                "cargo_name": move["cargo_name"],
                "stop_order": move["stop_order"],
                "move_sequence": move["move_sequence"],
                "reason": move.get("reason"),
                "cargo_state_snapshot": move.get("cargo_state_snapshot", [])
            })

        stop_results_list.append({
            "id": sr.id,
            "simulation_id": sr.simulation_id,
            "stop_id": sr.stop_id,
            "stop_order": sr.stop_order,
            "stop_name": sr.stop_name,
            "rehandle_count": sr.rehandle_count,
            "unload_count": sr.unload_count,
            "remaining_count": sr.remaining_count,
            "has_deadlock": sr.has_deadlock,
            "deadlock_cargo_ids": sr.deadlock_cargo_ids or [],
            "moves": moves_list,
            "remaining_cargos_state": sr.remaining_cargos_state or []
        })

    return {
        "id": simulation.id,
        "simulation_no": simulation.simulation_no,
        "route_id": simulation.route_id,
        "route_no": simulation.route_no,
        "status": simulation.status,
        "total_stops": simulation.total_stops,
        "total_cargos": simulation.total_cargos,
        "total_rehandle_count": simulation.total_rehandle_count,
        "worst_stop_id": simulation.worst_stop_id,
        "worst_stop_order": simulation.worst_stop_order,
        "worst_stop_rehandle_count": simulation.worst_stop_rehandle_count,
        "has_deadlock": simulation.has_deadlock,
        "deadlock_stop_id": simulation.deadlock_stop_id,
        "deadlock_stop_order": simulation.deadlock_stop_order,
        "deadlock_cargo_ids": simulation.deadlock_cargo_ids or [],
        "poorly_stacked_cargo_ids": simulation.poorly_stacked_cargo_ids or [],
        "created_at": simulation.created_at.isoformat() if simulation.created_at else "",
        "stop_results": stop_results_list
    }


@app.post("/unloading/routes/compare", response_model=schemas.RouteComparisonResult)
def compare_routes(
    request: schemas.RouteComparisonRequest,
    db: Session = Depends(get_db)
):
    plan = None
    if request.plan_identifier.isdigit():
        plan = crud.get_packing_plan(db, plan_id=int(request.plan_identifier))
    if plan is None:
        plan = crud.get_packing_plan(db, plan_no=request.plan_identifier)

    if plan is None:
        raise HTTPException(status_code=404, detail="配载方案不存在")

    routes_data = []
    best_route = None
    min_rehandle = float('inf')

    for route_identifier in request.route_identifiers:
        route = _resolve_unloading_route(route_identifier, db)
        if route is None:
            raise HTTPException(status_code=404, detail=f"路线 {route_identifier} 不存在")

        stops = crud.get_route_stops(db, route_id=route.id)
        assignments = crud.get_route_cargo_assignments(db, route_id=route.id)
        latest_sim = crud.get_latest_simulation_by_route(db, route_id=route.id)

        needs_renew = False
        if latest_sim is None:
            needs_renew = True
        elif route.updated_at and latest_sim.created_at < route.updated_at:
            needs_renew = True

        if needs_renew:
            plan = crud.get_packing_plan(db, plan_id=route.plan_id)
            if plan:
                packed_cargos_db = crud.get_packed_cargos(db, plan_id=plan.id)
                if packed_cargos_db:
                    packed_cargos_list = [{
                        "id": pc.id, "cargo_id": pc.cargo_id, "cargo_name": pc.cargo_name,
                        "x": pc.x, "y": pc.y, "z": pc.z,
                        "length": pc.length, "width": pc.width, "height": pc.height, "weight": pc.weight
                    } for pc in packed_cargos_db]
                    stops_list = [{
                        "id": s.id, "stop_order": s.stop_order,
                        "stop_name": s.stop_name, "stop_code": s.stop_code
                    } for s in stops]
                    assignments_list = [{
                        "packed_cargo_id": a.packed_cargo_id,
                        "stop_order": a.stop_order, "unload_order": a.unload_order
                    } for a in assignments]
                    new_sim_result = run_unloading_simulation(packed_cargos_list, stops_list, assignments_list)
                    latest_sim = crud.create_unloading_simulation(db, route, new_sim_result)

        worst_stop_name = None
        has_deadlock = False
        total_rehandle = 0
        worst_stop_order = None
        worst_stop_rehandle = 0

        if latest_sim:
            total_rehandle = latest_sim.total_rehandle_count
            worst_stop_order = latest_sim.worst_stop_order
            worst_stop_rehandle = latest_sim.worst_stop_rehandle_count
            has_deadlock = latest_sim.has_deadlock
            if latest_sim.worst_stop_id:
                worst_stop = db.query(models.UnloadingRouteStop).filter(
                    models.UnloadingRouteStop.id == latest_sim.worst_stop_id
                ).first()
                if worst_stop:
                    worst_stop_name = worst_stop.stop_name

        if not has_deadlock and total_rehandle < min_rehandle:
            min_rehandle = total_rehandle
            best_route = route

        routes_data.append({
            "route_id": route.id,
            "route_no": route.route_no,
            "route_name": route.name,
            "total_stops": len(stops),
            "total_cargos": len(assignments),
            "total_rehandle_count": total_rehandle,
            "worst_stop_order": worst_stop_order,
            "worst_stop_name": worst_stop_name,
            "worst_stop_rehandle_count": worst_stop_rehandle,
            "has_deadlock": has_deadlock,
            "latest_simulation_no": latest_sim.simulation_no if latest_sim else None
        })

    if best_route:
        recommendation = f"推荐使用路线「{best_route.name}」({best_route.route_no})，总返搬次数最少({min_rehandle}次)"
    else:
        valid_routes = [r for r in routes_data if not r["has_deadlock"]]
        if valid_routes:
            best = min(valid_routes, key=lambda r: r["total_rehandle_count"])
            recommendation = f"推荐使用路线「{best['route_name']}」({best['route_no']})，总返搬次数最少({best['total_rehandle_count']}次)"
        else:
            recommendation = "所有对比路线均存在死局，请重新规划货物分配或站点顺序"

    comparison_id = f"CMP-ROUTE-{uuid.uuid4().hex[:8].upper()}"

    return {
        "plan_id": plan.id,
        "plan_no": plan.plan_no,
        "plan_name": plan.container_name,
        "comparison_id": comparison_id,
        "routes": routes_data,
        "recommendation": recommendation
    }


@app.get("/plans/{plan_identifier}/unloading-routes", response_model=List[schemas.UnloadingRouteSummary])
def get_plan_unloading_routes(
    plan_identifier: str,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    return list_unloading_routes(
        plan_identifier=plan_identifier,
        skip=skip,
        limit=limit,
        db=db
    )


def _resolve_change_draft(draft_identifier: str, db: Session):
    draft = None
    if draft_identifier.isdigit():
        draft = crud.get_change_draft(db, draft_id=int(draft_identifier))
    if draft is None:
        draft = crud.get_change_draft(db, draft_no=draft_identifier)
    return draft


def _serialize_change_draft(draft: models.ChangeDraft) -> dict:
    proposed = draft.proposed_changes or {}
    return {
        "id": draft.id,
        "draft_no": draft.draft_no,
        "plan_id": draft.plan_id,
        "plan_no": draft.plan_no,
        "base_version": draft.base_version,
        "base_content_hash": draft.base_content_hash,
        "status": draft.status,
        "change_type": draft.change_type,
        "change_description": draft.change_description,
        "proposed_changes": {
            "cargo_changes": proposed.get("cargo_changes", []),
            "site_changes": proposed.get("site_changes", []),
            "plan_meta_changes": proposed.get("plan_meta_changes", []),
        },
        "created_by": draft.created_by,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "analyzed_at": draft.analyzed_at.isoformat() if draft.analyzed_at else None,
        "applied_at": draft.applied_at.isoformat() if draft.applied_at else None,
        "applied_by": draft.applied_by,
        "remarks": draft.remarks,
    }


def _serialize_impact_analysis(analysis: models.ChangeImpactAnalysis, include_items: bool = True) -> dict:
    result = {
        "id": analysis.id,
        "analysis_no": analysis.analysis_no,
        "draft_id": analysis.draft_id,
        "plan_id": analysis.plan_id,
        "plan_no": analysis.plan_no,
        "base_version": analysis.base_version,
        "new_version": analysis.new_version,
        "total_affected_count": analysis.total_affected_count,
        "need_rerun_count": analysis.need_rerun_count,
        "can_keep_count": analysis.can_keep_count,
        "must_invalidate_count": analysis.must_invalidate_count,
        "analysis_summary": analysis.analysis_summary,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
    }

    if include_items:
        impact_items = []
        for item in analysis.impact_items:
            impact_items.append({
                "id": item.id,
                "analysis_id": item.analysis_id,
                "result_type": item.result_type,
                "result_id": item.result_id,
                "result_no": item.result_no,
                "result_version": item.result_version,
                "impact_decision": item.impact_decision,
                "impact_reason": item.impact_reason,
                "affected_fields": item.affected_fields or [],
                "created_at": item.created_at.isoformat() if item.created_at else None,
            })
        result["impact_items"] = impact_items

        if analysis.diff_snapshot:
            snap = analysis.diff_snapshot
            result["diff_snapshot"] = {
                "id": snap.id,
                "snapshot_no": snap.snapshot_no,
                "analysis_id": snap.analysis_id,
                "plan_id": snap.plan_id,
                "plan_no": snap.plan_no,
                "base_version": snap.base_version,
                "new_version": snap.new_version,
                "before_data": snap.before_data or {},
                "after_data": snap.after_data or {},
                "field_diffs": snap.field_diffs or [],
                "cargo_diffs": snap.cargo_diffs or [],
                "created_at": snap.created_at.isoformat() if snap.created_at else None,
            }
        else:
            result["diff_snapshot"] = None

    return result


@app.post("/change/drafts", response_model=schemas.ChangeDraftDetail)
def create_change_draft(
    request: schemas.ChangeDraftCreate,
    db: Session = Depends(get_db)
):
    plan = None
    if request.plan_identifier.isdigit():
        plan = crud.get_packing_plan(db, plan_id=int(request.plan_identifier))
    if plan is None:
        plan = crud.get_packing_plan(db, plan_no=request.plan_identifier)

    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")

    try:
        draft = crud.create_change_draft(
            db=db,
            plan_id=plan.id,
            change_type=request.change_type.value,
            change_description=request.change_description,
            proposed_changes=request.proposed_changes.model_dump(),
            created_by=request.created_by,
            remarks=request.remarks
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return get_change_draft_detail(draft_identifier=str(draft.id), db=db)


@app.get("/change/drafts", response_model=List[schemas.ChangeDraftList])
def list_change_drafts(
    plan_identifier: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    drafts = crud.list_change_drafts(
        db,
        plan_identifier=plan_identifier,
        status=status,
        skip=skip,
        limit=limit
    )

    result = []
    for draft in drafts:
        draft_data = _serialize_change_draft(draft)
        if draft.status in ("analyzed", "applied") and draft.impact_analysis:
            draft_data["impact_analysis"] = {
                "id": draft.impact_analysis.id,
                "analysis_no": draft.impact_analysis.analysis_no,
                "plan_id": draft.impact_analysis.plan_id,
                "plan_no": draft.impact_analysis.plan_no,
                "base_version": draft.impact_analysis.base_version,
                "new_version": draft.impact_analysis.new_version,
                "total_affected_count": draft.impact_analysis.total_affected_count,
                "need_rerun_count": draft.impact_analysis.need_rerun_count,
                "can_keep_count": draft.impact_analysis.can_keep_count,
                "must_invalidate_count": draft.impact_analysis.must_invalidate_count,
                "analysis_summary": draft.impact_analysis.analysis_summary,
                "created_at": draft.impact_analysis.created_at.isoformat() if draft.impact_analysis.created_at else None,
            }
        else:
            draft_data["impact_analysis"] = None
        result.append(draft_data)

    return result


@app.get("/change/drafts/{draft_identifier}", response_model=schemas.ChangeDraftDetail)
def get_change_draft_detail(
    draft_identifier: str,
    db: Session = Depends(get_db)
):
    draft = _resolve_change_draft(draft_identifier, db)
    if draft is None:
        raise HTTPException(status_code=404, detail="变更草案不存在")

    draft_data = _serialize_change_draft(draft)

    if draft.impact_analysis:
        draft_data["impact_analysis"] = _serialize_impact_analysis(draft.impact_analysis, include_items=True)
    else:
        draft_data["impact_analysis"] = None

    return draft_data


@app.put("/change/drafts/{draft_identifier}", response_model=schemas.ChangeDraftDetail)
def update_change_draft(
    draft_identifier: str,
    request: schemas.ChangeDraftUpdate,
    db: Session = Depends(get_db)
):
    draft = _resolve_change_draft(draft_identifier, db)
    if draft is None:
        raise HTTPException(status_code=404, detail="变更草案不存在")

    update_data = {}
    if request.change_type is not None:
        update_data["change_type"] = request.change_type.value
    if request.change_description is not None:
        update_data["change_description"] = request.change_description
    if request.proposed_changes is not None:
        update_data["proposed_changes"] = request.proposed_changes.model_dump()
    if request.remarks is not None:
        update_data["remarks"] = request.remarks

    try:
        draft = crud.update_change_draft(db, draft_id=draft.id, update_data=update_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return get_change_draft_detail(draft_identifier=str(draft.id), db=db)


@app.post("/change/drafts/{draft_identifier}/cancel")
def cancel_change_draft(
    draft_identifier: str,
    db: Session = Depends(get_db)
):
    draft = _resolve_change_draft(draft_identifier, db)
    if draft is None:
        raise HTTPException(status_code=404, detail="变更草案不存在")

    try:
        draft = crud.cancel_change_draft(db, draft_id=draft.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "message": "变更草案已取消",
        "draft_id": draft.id,
        "draft_no": draft.draft_no,
        "status": draft.status
    }


@app.post("/change/drafts/{draft_identifier}/analyze", response_model=schemas.ChangeImpactAnalysisResult)
def analyze_change_impact(
    draft_identifier: str,
    db: Session = Depends(get_db)
):
    draft = _resolve_change_draft(draft_identifier, db)
    if draft is None:
        raise HTTPException(status_code=404, detail="变更草案不存在")

    try:
        analysis = crud.run_impact_analysis(db, draft_id=draft.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "draft_id": draft.id,
        "draft_no": draft.draft_no,
        "analysis": _serialize_impact_analysis(analysis, include_items=True)
    }


@app.post("/change/drafts/{draft_identifier}/apply")
def apply_change(
    draft_identifier: str,
    request: schemas.ChangeApplyRequest,
    db: Session = Depends(get_db)
):
    draft = _resolve_change_draft(draft_identifier, db)
    if draft is None:
        raise HTTPException(status_code=404, detail="变更草案不存在")

    try:
        plan = crud.apply_change(
            db,
            draft_id=draft.id,
            applied_by=request.applied_by,
            remarks=request.remarks
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    analysis = crud.get_impact_analysis(db, analysis_id=draft.impact_analysis.id) if draft.impact_analysis else None

    return {
        "message": "变更已应用",
        "draft_id": draft.id,
        "draft_no": draft.draft_no,
        "plan_id": plan.id,
        "plan_no": plan.plan_no,
        "new_version": plan.version,
        "new_content_hash": plan.content_hash,
        "applied_at": draft.applied_at.isoformat() if draft.applied_at else None,
        "applied_by": draft.applied_by,
        "impact_summary": {
            "total_affected": analysis.total_affected_count if analysis else 0,
            "need_rerun": analysis.need_rerun_count if analysis else 0,
            "can_keep": analysis.can_keep_count if analysis else 0,
            "must_invalidate": analysis.must_invalidate_count if analysis else 0,
        } if analysis else None
    }


@app.get("/change/analyses", response_model=List[schemas.ChangeImpactAnalysis])
def list_impact_analyses(
    plan_identifier: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    if plan_identifier:
        analyses = crud.get_impact_analyses_by_plan(db, plan_identifier=plan_identifier, skip=skip, limit=limit)
    else:
        analyses = db.query(models.ChangeImpactAnalysis).order_by(
            models.ChangeImpactAnalysis.created_at.desc()
        ).offset(skip).limit(limit).all()

    result = []
    for analysis in analyses:
        result.append(_serialize_impact_analysis(analysis, include_items=False))
    return result


@app.get("/change/analyses/{analysis_identifier}", response_model=schemas.ChangeImpactAnalysisDetail)
def get_impact_analysis_detail(
    analysis_identifier: str,
    db: Session = Depends(get_db)
):
    analysis = None
    if analysis_identifier.isdigit():
        analysis = crud.get_impact_analysis(db, analysis_id=int(analysis_identifier))
    if analysis is None:
        analysis = crud.get_impact_analysis(db, analysis_no=analysis_identifier)

    if analysis is None:
        raise HTTPException(status_code=404, detail="影响分析记录不存在")

    return _serialize_impact_analysis(analysis, include_items=True)


@app.get("/change/snapshots/{snapshot_identifier}", response_model=schemas.ChangeDiffSnapshot)
def get_diff_snapshot(
    snapshot_identifier: str,
    db: Session = Depends(get_db)
):
    snapshot = None
    if snapshot_identifier.isdigit():
        snapshot = crud.get_diff_snapshot(db, snapshot_id=int(snapshot_identifier))
    if snapshot is None:
        snapshot = crud.get_diff_snapshot(db, snapshot_no=snapshot_identifier)

    if snapshot is None:
        raise HTTPException(status_code=404, detail="差异快照不存在")

    return {
        "id": snapshot.id,
        "snapshot_no": snapshot.snapshot_no,
        "analysis_id": snapshot.analysis_id,
        "plan_id": snapshot.plan_id,
        "plan_no": snapshot.plan_no,
        "base_version": snapshot.base_version,
        "new_version": snapshot.new_version,
        "before_data": snapshot.before_data or {},
        "after_data": snapshot.after_data or {},
        "field_diffs": snapshot.field_diffs or [],
        "cargo_diffs": snapshot.cargo_diffs or [],
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


@app.get("/plans/{plan_identifier}/change-history")
def get_plan_change_history(
    plan_identifier: str,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    plan = None
    if plan_identifier.isdigit():
        plan = crud.get_packing_plan(db, plan_id=int(plan_identifier))
    if plan is None:
        plan = crud.get_packing_plan(db, plan_no=plan_identifier)

    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")

    history = crud.get_change_history(db, plan_identifier=plan_identifier, skip=skip, limit=limit)

    return {
        "plan_id": plan.id,
        "plan_no": plan.plan_no,
        "current_version": plan.version,
        "total_changes": len(history),
        "history": history
    }


def _resolve_dispatch_task(task_identifier: str, db: Session):
    task = None
    if task_identifier.isdigit():
        task = crud.get_dispatch_task(db, task_id=int(task_identifier))
    if task is None:
        task = crud.get_dispatch_task(db, task_no=task_identifier)
    return task


def _serialize_publication(pub: models.PublicationRecord) -> dict:
    result = {
        "id": pub.id,
        "publication_no": pub.publication_no,
        "plan_id": pub.plan_id,
        "plan_no": pub.plan_no,
        "plan_version": pub.plan_version,
        "plan_content_hash": pub.plan_content_hash,
        "container_no": pub.container_no,
        "seal_no": pub.seal_no,
        "audit_no": pub.audit_no,
        "audit_passed": pub.audit_passed,
        "confirmation_no": pub.confirmation_no,
        "confirmation_released": pub.confirmation_released,
        "route_no": pub.route_no,
        "simulation_no": pub.simulation_no,
        "trailer_plan_no": pub.trailer_plan_no,
        "status": pub.status,
        "published_by": pub.published_by,
        "published_at": pub.published_at.isoformat() if pub.published_at else None,
        "approved_by": pub.approved_by,
        "approved_at": pub.approved_at.isoformat() if pub.approved_at else None,
        "rejected_reason": pub.rejected_reason,
        "gate_check_result": pub.gate_check_result or {},
    }
    return result


def _serialize_dispatch_task(task: models.DispatchTask, db: Session = None, include_snapshot: bool = False) -> dict:
    result = {
        "id": task.id,
        "task_no": task.task_no,
        "plan_id": task.plan_id,
        "plan_no": task.plan_no,
        "publication_id": task.publication_id,
        "frozen_version": task.frozen_version,
        "frozen_content_hash": task.frozen_content_hash,
        "vehicle_no": task.vehicle_no,
        "driver_name": task.driver_name,
        "planned_departure_time": task.planned_departure_time.isoformat() if task.planned_departure_time else None,
        "arrival_time": task.arrival_time.isoformat() if task.arrival_time else None,
        "terminal_window": task.terminal_window,
        "status": task.status,
        "block_reasons": task.block_reasons or [],
        "last_validated_at": task.last_validated_at.isoformat() if task.last_validated_at else None,
        "status_changed_at": task.status_changed_at.isoformat() if task.status_changed_at else None,
        "created_by": task.created_by,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }
    if include_snapshot and db:
        result["frozen_snapshot"] = task.frozen_snapshot
        pub = crud.get_publication(db, pub_id=task.publication_id)
        result["publication_no"] = pub.publication_no if pub else None
    return result


@app.get("/dispatch/plans/{plan_identifier}/gate-check", response_model=schemas.GateCheckResult)
def check_dispatch_gate(
    plan_identifier: str,
    db: Session = Depends(get_db)
):
    plan = _resolve_packing_plan(plan_identifier, db)
    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")
    return crud.run_gate_check(db, plan.id)


@app.post("/dispatch/publish", response_model=schemas.PublicationDetail)
def publish_plan(
    request: schemas.PublicationRequest,
    db: Session = Depends(get_db)
):
    plan = _resolve_packing_plan(request.plan_identifier, db)
    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")

    route_id = None
    if request.route_identifier:
        route = crud.get_unloading_route(db, route_id=int(request.route_identifier) if request.route_identifier.isdigit() else None, route_no=request.route_identifier if not request.route_identifier.isdigit() else None)
        if route:
            route_id = route.id

    simulation_id = None
    if request.simulation_identifier:
        sim = crud.get_unloading_simulation(db, simulation_id=int(request.simulation_identifier) if request.simulation_identifier.isdigit() else None, simulation_no=request.simulation_identifier if not request.simulation_identifier.isdigit() else None)
        if sim:
            simulation_id = sim.id

    trailer_plan_id = None
    if request.trailer_plan_identifier:
        tp = crud.get_trailer_load_plan(db, plan_id=int(request.trailer_plan_identifier) if request.trailer_plan_identifier.isdigit() else None, plan_no=request.trailer_plan_identifier if not request.trailer_plan_identifier.isdigit() else None)
        if tp:
            trailer_plan_id = tp.id

    try:
        pub = crud.create_publication(
            db, plan_id=plan.id,
            route_id=route_id,
            simulation_id=simulation_id,
            trailer_plan_id=trailer_plan_id,
            published_by=request.published_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = _serialize_publication(pub)
    result["document_snapshot"] = pub.document_snapshot or []
    result["snapshot_data"] = pub.snapshot_data or {}

    dt = db.query(models.DispatchTask).filter(models.DispatchTask.publication_id == pub.id).first()
    result["dispatch_task"] = _serialize_dispatch_task(dt, db=db) if dt else None
    return result


@app.post("/dispatch/publish/{pub_identifier}/approve", response_model=schemas.PublicationDetail)
def approve_publication(
    pub_identifier: str,
    request: schemas.PublicationApproveRequest,
    db: Session = Depends(get_db)
):
    pub = None
    if pub_identifier.isdigit():
        pub = crud.get_publication(db, pub_id=int(pub_identifier))
    if pub is None:
        pub = crud.get_publication(db, publication_no=pub_identifier)
    if pub is None:
        raise HTTPException(status_code=404, detail="发布记录不存在")

    try:
        pub = crud.approve_publication(db, pub_id=pub.id, approved_by=request.approved_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = _serialize_publication(pub)
    result["document_snapshot"] = pub.document_snapshot or []
    result["snapshot_data"] = pub.snapshot_data or {}
    dt = db.query(models.DispatchTask).filter(models.DispatchTask.publication_id == pub.id).first()
    result["dispatch_task"] = _serialize_dispatch_task(dt, db=db) if dt else None
    return result


@app.post("/dispatch/publish/{pub_identifier}/reject", response_model=schemas.PublicationDetail)
def reject_publication(
    pub_identifier: str,
    request: schemas.PublicationRejectRequest,
    db: Session = Depends(get_db)
):
    pub = None
    if pub_identifier.isdigit():
        pub = crud.get_publication(db, pub_id=int(pub_identifier))
    if pub is None:
        pub = crud.get_publication(db, publication_no=pub_identifier)
    if pub is None:
        raise HTTPException(status_code=404, detail="发布记录不存在")

    try:
        pub = crud.reject_publication(db, pub_id=pub.id, rejected_reason=request.rejected_reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = _serialize_publication(pub)
    result["document_snapshot"] = pub.document_snapshot or []
    result["snapshot_data"] = pub.snapshot_data or {}
    result["dispatch_task"] = None
    return result


@app.get("/dispatch/plans/{plan_identifier}/publish-history", response_model=List[schemas.Publication])
def get_publish_history(
    plan_identifier: str,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    plan = _resolve_packing_plan(plan_identifier, db)
    if plan is None:
        raise HTTPException(status_code=404, detail="方案不存在")

    pubs = crud.list_publications(db, plan_id=plan.id, status=status, skip=skip, limit=limit)
    return [_serialize_publication(p) for p in pubs]


@app.get("/dispatch/publish/{pub_identifier}", response_model=schemas.PublicationDetail)
def get_publication_detail(
    pub_identifier: str,
    db: Session = Depends(get_db)
):
    pub = None
    if pub_identifier.isdigit():
        pub = crud.get_publication(db, pub_id=int(pub_identifier))
    if pub is None:
        pub = crud.get_publication(db, publication_no=pub_identifier)
    if pub is None:
        raise HTTPException(status_code=404, detail="发布记录不存在")

    result = _serialize_publication(pub)
    result["document_snapshot"] = pub.document_snapshot or []
    result["snapshot_data"] = pub.snapshot_data or {}
    dt = db.query(models.DispatchTask).filter(models.DispatchTask.publication_id == pub.id).first()
    result["dispatch_task"] = _serialize_dispatch_task(dt, db=db) if dt else None
    return result


@app.get("/dispatch/tasks", response_model=List[schemas.DispatchTask])
def list_dispatch_tasks(
    plan_no: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    tasks = crud.list_dispatch_tasks(db, plan_no=plan_no, status=status, skip=skip, limit=limit)
    return [_serialize_dispatch_task(t, db=db) for t in tasks]


@app.get("/dispatch/tasks/{task_identifier}", response_model=schemas.DispatchTaskDetail)
def get_dispatch_task_detail(
    task_identifier: str,
    db: Session = Depends(get_db)
):
    task = _resolve_dispatch_task(task_identifier, db)
    if task is None:
        raise HTTPException(status_code=404, detail="发运任务不存在")

    result = _serialize_dispatch_task(task, db=db, include_snapshot=True)
    result["frozen_snapshot"] = task.frozen_snapshot or {}
    pub = crud.get_publication(db, pub_id=task.publication_id)
    result["publication_no"] = pub.publication_no if pub else None
    return result


@app.put("/dispatch/tasks/{task_identifier}", response_model=schemas.DispatchTask)
def update_dispatch_task(
    task_identifier: str,
    request: schemas.DispatchTaskUpdateRequest,
    db: Session = Depends(get_db)
):
    task = _resolve_dispatch_task(task_identifier, db)
    if task is None:
        raise HTTPException(status_code=404, detail="发运任务不存在")

    updated = crud.update_dispatch_task(db, task_id=task.id, update_data=request.model_dump())
    if not updated:
        raise HTTPException(status_code=400, detail="更新失败")
    return _serialize_dispatch_task(updated, db=db)


@app.post("/dispatch/tasks/{task_identifier}/status", response_model=schemas.DispatchTask)
def transition_dispatch_status(
    task_identifier: str,
    request: schemas.DispatchStatusTransitionRequest,
    db: Session = Depends(get_db)
):
    task = _resolve_dispatch_task(task_identifier, db)
    if task is None:
        raise HTTPException(status_code=404, detail="发运任务不存在")

    try:
        updated = crud.transition_dispatch_status(db, task_id=task.id, target_status=request.target_status, reason=request.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_dispatch_task(updated, db=db)


@app.post("/dispatch/tasks/{task_identifier}/validate")
def validate_dispatch_task(
    task_identifier: str,
    db: Session = Depends(get_db)
):
    task = _resolve_dispatch_task(task_identifier, db)
    if task is None:
        raise HTTPException(status_code=404, detail="发运任务不存在")

    validation = crud.validate_dispatch_dependencies(db, task.id)
    return {
        "task_id": task.id,
        "task_no": task.task_no,
        "is_valid": validation["is_valid"],
        "block_reasons": validation["block_reasons"],
        "summary": validation["summary"],
        "current_status": task.status,
    }


@app.post("/dispatch/validate-all")
def validate_all_dispatches(db: Session = Depends(get_db)):
    results = crud.validate_all_active_dispatches(db)
    return {
        "total_checked": len(results),
        "invalid_count": sum(1 for r in results if not r["is_valid"]),
        "results": results,
    }


def _serialize_batch_task_item(item) -> dict:
    return {
        "id": item.id,
        "batch_id": item.batch_id,
        "dispatch_task_id": item.dispatch_task_id,
        "dispatch_task_no": item.dispatch_task_no,
        "plan_id": item.plan_id,
        "plan_no": item.plan_no,
        "container_no": item.container_no,
        "seal_no": item.seal_no,
        "route_no": item.route_no,
        "frozen_snapshot": item.frozen_snapshot or {},
        "loading_order": item.loading_order,
        "vehicle_assignment": item.vehicle_assignment,
        "is_blocked": item.is_blocked,
        "block_reason": item.block_reason,
        "removed_at": item.removed_at.isoformat() if item.removed_at else None,
        "remove_reason": item.remove_reason,
    }


def _serialize_batch(batch, db: Session = None, include_items: bool = False) -> dict:
    result = {
        "id": batch.id,
        "batch_no": batch.batch_no,
        "transport_direction": batch.transport_direction,
        "fleet_name": batch.fleet_name,
        "fleet_contact": batch.fleet_contact,
        "fleet_phone": batch.fleet_phone,
        "tractor_no": batch.tractor_no,
        "trailer_no": batch.trailer_no,
        "planned_departure_time": batch.planned_departure_time.isoformat() if batch.planned_departure_time else None,
        "assembly_location": batch.assembly_location,
        "status": batch.status,
        "total_containers": batch.total_containers,
        "total_weight": batch.total_weight,
        "block_reasons": batch.block_reasons or [],
        "status_changed_at": batch.status_changed_at.isoformat() if batch.status_changed_at else None,
        "created_by": batch.created_by,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
        "cancelled_at": batch.cancelled_at.isoformat() if batch.cancelled_at else None,
        "cancel_reason": batch.cancel_reason,
    }
    if include_items and db:
        items = db.query(models.BatchTaskItem).filter(
            models.BatchTaskItem.batch_id == batch.id
        ).order_by(models.BatchTaskItem.loading_order, models.BatchTaskItem.id).all()
        result["task_items"] = [_serialize_batch_task_item(it) for it in items]
    return result


def _resolve_batch(batch_identifier: str, db: Session):
    batch = None
    if batch_identifier.isdigit():
        batch = crud.get_batch_shipment(db, batch_id=int(batch_identifier))
    if batch is None:
        batch = crud.get_batch_shipment(db, batch_no=batch_identifier)
    return batch


@app.post("/batch", response_model=schemas.BatchShipmentDetail)
def create_batch_shipment(
    request: schemas.BatchShipmentCreate,
    db: Session = Depends(get_db)
):
    task_ids = [item.dispatch_task_id for item in request.task_items]
    direction_errors = crud._validate_batch_direction(db, task_ids, request.transport_direction)
    if direction_errors:
        raise HTTPException(status_code=400, detail="; ".join(direction_errors))

    vehicle_errors = crud._validate_vehicle_not_double_booked(
        db, batch_id=0, dispatch_task_ids=task_ids,
        tractor_no=request.tractor_no, trailer_no=request.trailer_no
    )
    if vehicle_errors:
        raise HTTPException(status_code=400, detail="; ".join(vehicle_errors))

    batch_data = request.model_dump(exclude={"task_items"})
    task_items_data = [item.model_dump() for item in request.task_items]

    batch = crud.create_batch_shipment(db, batch_data, task_items_data)
    return _serialize_batch(batch, db=db, include_items=True)


@app.get("/batch", response_model=List[schemas.BatchShipment])
def list_batch_shipments(
    transport_direction: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    batches = crud.list_batch_shipments(
        db, transport_direction=transport_direction, status=status, skip=skip, limit=limit
    )
    return [_serialize_batch(b) for b in batches]


@app.get("/batch/{batch_identifier}", response_model=schemas.BatchShipmentDetail)
def get_batch_detail(
    batch_identifier: str,
    db: Session = Depends(get_db)
):
    batch = _resolve_batch(batch_identifier, db)
    if batch is None:
        raise HTTPException(status_code=404, detail="发运批次不存在")
    return _serialize_batch(batch, db=db, include_items=True)


@app.put("/batch/{batch_identifier}", response_model=schemas.BatchShipment)
def update_batch_shipment(
    batch_identifier: str,
    request: schemas.BatchShipmentUpdate,
    db: Session = Depends(get_db)
):
    batch = _resolve_batch(batch_identifier, db)
    if batch is None:
        raise HTTPException(status_code=404, detail="发运批次不存在")

    update_data = request.model_dump(exclude_unset=True)
    if update_data.get("tractor_no") or update_data.get("trailer_no"):
        tractor = update_data.get("tractor_no", batch.tractor_no)
        trailer = update_data.get("trailer_no", batch.trailer_no)
        vehicle_errors = crud._validate_vehicle_not_double_booked(
            db, batch_id=batch.id, dispatch_task_ids=[],
            tractor_no=tractor, trailer_no=trailer
        )
        if vehicle_errors:
            raise HTTPException(status_code=400, detail="; ".join(vehicle_errors))

    updated = crud.update_batch_shipment(db, batch_id=batch.id, update_data=update_data)
    return _serialize_batch(updated)


@app.post("/batch/{batch_identifier}/tasks", response_model=schemas.BatchShipmentDetail)
def add_tasks_to_batch(
    batch_identifier: str,
    request: schemas.BatchTaskItemsAddRequest,
    db: Session = Depends(get_db)
):
    batch = _resolve_batch(batch_identifier, db)
    if batch is None:
        raise HTTPException(status_code=404, detail="发运批次不存在")
    if batch.status not in ("pending_grouping", "grouping"):
        raise HTTPException(status_code=400, detail=f"批次状态为 {batch.status}，不允许添加任务")

    task_ids = [item.dispatch_task_id for item in request.task_items]
    direction_errors = crud._validate_batch_direction(db, task_ids, batch.transport_direction)
    if direction_errors:
        raise HTTPException(status_code=400, detail="; ".join(direction_errors))

    vehicle_errors = crud._validate_vehicle_not_double_booked(
        db, batch_id=batch.id, dispatch_task_ids=task_ids,
        tractor_no=batch.tractor_no, trailer_no=batch.trailer_no
    )
    if vehicle_errors:
        raise HTTPException(status_code=400, detail="; ".join(vehicle_errors))

    task_items_data = [item.model_dump() for item in request.task_items]
    updated = crud.add_tasks_to_batch(db, batch_id=batch.id, task_items_data=task_items_data)
    return _serialize_batch(updated, db=db, include_items=True)


@app.delete("/batch/{batch_identifier}/tasks/{task_item_id}", response_model=schemas.BatchShipmentDetail)
def remove_task_from_batch(
    batch_identifier: str,
    task_item_id: int,
    request: schemas.BatchTaskItemRemoveRequest,
    db: Session = Depends(get_db)
):
    batch = _resolve_batch(batch_identifier, db)
    if batch is None:
        raise HTTPException(status_code=404, detail="发运批次不存在")

    updated = crud.remove_task_from_batch(
        db, batch_id=batch.id, task_item_id=task_item_id, remove_reason=request.remove_reason
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="批次任务项不存在或已移出")
    return _serialize_batch(updated, db=db, include_items=True)


@app.post("/batch/{batch_identifier}/status", response_model=schemas.BatchShipment)
def transition_batch_status(
    batch_identifier: str,
    request: schemas.BatchStatusTransitionRequest,
    db: Session = Depends(get_db)
):
    batch = _resolve_batch(batch_identifier, db)
    if batch is None:
        raise HTTPException(status_code=404, detail="发运批次不存在")

    target = request.target_status.value if hasattr(request.target_status, "value") else request.target_status

    if target in ("pending_departure", "dispatched"):
        validation = crud.validate_batch_blockage(db, batch_id=batch.id)
        if not validation["is_valid"]:
            blocked_details = []
            for item in validation["blocked_items"]:
                blocked_details.append(f"任务 {item.dispatch_task_no}: {item.block_reason}")
            raise HTTPException(status_code=400, detail={
                "error": "批次存在阻断任务，不能变更到目标状态",
                "blocked_tasks": blocked_details,
                "block_reasons": validation["block_reasons"],
            })

    try:
        updated = crud.transition_batch_status(
            db, batch_id=batch.id, target_status=target, reason=request.reason
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _serialize_batch(updated)


@app.post("/batch/{batch_identifier}/validate")
def validate_batch(
    batch_identifier: str,
    db: Session = Depends(get_db)
):
    batch = _resolve_batch(batch_identifier, db)
    if batch is None:
        raise HTTPException(status_code=404, detail="发运批次不存在")

    validation = crud.validate_batch_blockage(db, batch_id=batch.id)
    return {
        "batch_id": batch.id,
        "batch_no": batch.batch_no,
        "is_valid": validation["is_valid"],
        "blocked_tasks": [
            {
                "task_item_id": item.id,
                "dispatch_task_no": item.dispatch_task_no,
                "plan_no": item.plan_no,
                "block_reason": item.block_reason,
            }
            for item in validation["blocked_items"]
        ],
        "block_reasons": validation["block_reasons"],
    }


@app.get("/batch/{batch_identifier}/history")
def get_batch_history(
    batch_identifier: str,
    db: Session = Depends(get_db)
):
    batch = _resolve_batch(batch_identifier, db)
    if batch is None:
        raise HTTPException(status_code=404, detail="发运批次不存在")

    all_items = db.query(models.BatchTaskItem).filter(
        models.BatchTaskItem.batch_id == batch.id
    ).order_by(models.BatchTaskItem.loading_order, models.BatchTaskItem.id).all()

    active_items = []
    removed_items = []
    vehicle_map = {}

    for item in all_items:
        entry = _serialize_batch_task_item(item)
        if item.removed_at:
            removed_items.append(entry)
        else:
            active_items.append(entry)
            if item.vehicle_assignment:
                if item.vehicle_assignment not in vehicle_map:
                    vehicle_map[item.vehicle_assignment] = []
                vehicle_map[item.vehicle_assignment].append({
                    "task_item_id": item.id,
                    "dispatch_task_no": item.dispatch_task_no,
                    "plan_no": item.plan_no,
                    "container_no": item.container_no,
                    "loading_order": item.loading_order,
                })

    return {
        "batch_id": batch.id,
        "batch_no": batch.batch_no,
        "transport_direction": batch.transport_direction,
        "status": batch.status,
        "total_containers": batch.total_containers,
        "total_weight": batch.total_weight,
        "fleet_name": batch.fleet_name,
        "tractor_no": batch.tractor_no,
        "trailer_no": batch.trailer_no,
        "planned_departure_time": batch.planned_departure_time.isoformat() if batch.planned_departure_time else None,
        "assembly_location": batch.assembly_location,
        "block_reasons": batch.block_reasons or [],
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "active_items": active_items,
        "removed_items": removed_items,
        "vehicle_assignments": vehicle_map,
    }


# ==================== 费率方案管理 API ====================

def _resolve_rate_scheme(identifier: str, db: Session):
    return crud.resolve_rate_scheme(db, identifier)


@app.get("/rate/schemes", response_model=List[schemas.RateSchemeSummary])
def list_rate_schemes(
    is_active: Optional[bool] = None,
    carrier: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    schemes = crud.list_rate_schemes(db, skip=skip, limit=limit, is_active=is_active, carrier=carrier)
    result = []
    for s in schemes:
        rates = crud.get_scheme_container_rates(db, s.id)
        result.append({
            "id": s.id,
            "scheme_code": s.scheme_code,
            "scheme_name": s.scheme_name,
            "carrier": s.carrier,
            "trade_lane": s.trade_lane,
            "currency": s.currency,
            "is_default": s.is_default,
            "is_active": s.is_active,
            "container_count": len(rates),
            "description": s.description,
            "created_at": s.created_at.isoformat() if s.created_at else "",
        })
    return result


@app.get("/rate/schemes/{scheme_identifier}", response_model=schemas.RateSchemeDetail)
def get_rate_scheme_detail(scheme_identifier: str, db: Session = Depends(get_db)):
    scheme = _resolve_rate_scheme(scheme_identifier, db)
    if scheme is None:
        raise HTTPException(status_code=404, detail="费率方案不存在")

    rates = crud.get_scheme_container_rates(db, scheme.id)
    rate_list = []
    for r in rates:
        hazard_list = []
        for hc_str, amt in (r.hazard_surcharge_by_class or {}).items():
            try:
                hazard_list.append({"hazard_class": int(hc_str), "surcharge_amount": float(amt)})
            except (ValueError, TypeError):
                continue
        rate_list.append({
            "id": r.id,
            "scheme_id": r.scheme_id,
            "container_id": r.container_id,
            "container_name": r.container_name,
            "base_freight": r.base_freight,
            "overweight_threshold_kg": r.overweight_threshold_kg,
            "overweight_surcharge_per_kg": r.overweight_surcharge_per_kg,
            "overweight_surcharge_flat": r.overweight_surcharge_flat,
            "reefer_surcharge": r.reefer_surcharge,
            "frozen_surcharge": r.frozen_surcharge,
            "hazard_surcharge_by_class": r.hazard_surcharge_by_class or {},
            "hazard_surcharges": hazard_list,
            "hazard_surcharge_per_kg": r.hazard_surcharge_per_kg,
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "updated_at": r.updated_at.isoformat() if r.updated_at else "",
        })

    return {
        "id": scheme.id,
        "scheme_code": scheme.scheme_code,
        "scheme_name": scheme.scheme_name,
        "carrier": scheme.carrier,
        "trade_lane": scheme.trade_lane,
        "effective_from": scheme.effective_from.isoformat() if scheme.effective_from else None,
        "effective_to": scheme.effective_to.isoformat() if scheme.effective_to else None,
        "currency": scheme.currency,
        "is_default": scheme.is_default,
        "is_active": scheme.is_active,
        "description": scheme.description,
        "created_by": scheme.created_by,
        "created_at": scheme.created_at.isoformat() if scheme.created_at else "",
        "updated_at": scheme.updated_at.isoformat() if scheme.updated_at else "",
        "container_rates": rate_list,
    }


@app.post("/rate/schemes", response_model=schemas.RateSchemeDetail)
def create_rate_scheme(scheme: schemas.RateSchemeCreate, db: Session = Depends(get_db)):
    existing = crud.get_rate_scheme(db, scheme_code=scheme.scheme_code)
    if existing:
        raise HTTPException(status_code=400, detail=f"费率方案编码 {scheme.scheme_code} 已存在")

    scheme_data = scheme.model_dump()
    container_rates_data = scheme_data.pop("container_rates", []) or []

    try:
        if scheme_data.get("effective_from"):
            scheme_data["effective_from"] = datetime.fromisoformat(scheme_data["effective_from"])
        if scheme_data.get("effective_to"):
            scheme_data["effective_to"] = datetime.fromisoformat(scheme_data["effective_to"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"日期格式错误: {str(e)}")

    rate_dicts = []
    for r in container_rates_data:
        if isinstance(r, dict):
            rate_dicts.append(r)
        else:
            rate_dicts.append(r.model_dump())
    db_scheme = crud.create_rate_scheme(db, scheme_data, rate_dicts)

    return get_rate_scheme_detail(str(db_scheme.id), db)


@app.put("/rate/schemes/{scheme_identifier}")
def update_rate_scheme(
    scheme_identifier: str,
    update: schemas.RateSchemeUpdate,
    db: Session = Depends(get_db)
):
    scheme = _resolve_rate_scheme(scheme_identifier, db)
    if scheme is None:
        raise HTTPException(status_code=404, detail="费率方案不存在")

    update_data = update.model_dump(exclude_unset=True)
    try:
        if "effective_from" in update_data and update_data["effective_from"]:
            update_data["effective_from"] = datetime.fromisoformat(update_data["effective_from"])
        if "effective_to" in update_data and update_data["effective_to"]:
            update_data["effective_to"] = datetime.fromisoformat(update_data["effective_to"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"日期格式错误: {str(e)}")

    updated = crud.update_rate_scheme(db, scheme.id, update_data)
    return get_rate_scheme_detail(str(updated.id), db)


@app.delete("/rate/schemes/{scheme_identifier}")
def delete_rate_scheme(scheme_identifier: str, db: Session = Depends(get_db)):
    scheme = crud.delete_rate_scheme(
        db,
        scheme_id=int(scheme_identifier) if scheme_identifier.isdigit() else None,
        scheme_code=None if scheme_identifier.isdigit() else scheme_identifier,
    )
    if scheme is None:
        raise HTTPException(status_code=404, detail="费率方案不存在")
    return {"message": "删除成功", "scheme_code": scheme.scheme_code, "scheme_name": scheme.scheme_name}


# ==================== 箱型费率配置 API ====================

@app.post("/rate/schemes/{scheme_identifier}/rates")
def add_container_rate_config(
    scheme_identifier: str,
    rate_config: schemas.ContainerRateConfigCreate,
    db: Session = Depends(get_db)
):
    scheme = _resolve_rate_scheme(scheme_identifier, db)
    if scheme is None:
        raise HTTPException(status_code=404, detail="费率方案不存在")

    try:
        result = crud.create_container_rate_config(db, scheme.id, rate_config.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "message": "配置成功",
        "config_id": result.id,
        "container_name": result.container_name,
        "base_freight": result.base_freight,
    }


@app.put("/rate/rates/{config_id}")
def update_container_rate_config(
    config_id: int,
    update: schemas.ContainerRateConfigUpdate,
    db: Session = Depends(get_db)
):
    update_data = update.model_dump(exclude_unset=True)
    updated = crud.update_container_rate_config(db, config_id, update_data)
    if updated is None:
        raise HTTPException(status_code=404, detail="费率配置不存在")
    return {"message": "更新成功", "config_id": updated.id}


@app.delete("/rate/rates/{config_id}")
def delete_container_rate_config(config_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_container_rate_config(db, config_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="费率配置不存在")
    return {"message": "删除成功", "config_id": deleted.id}


# ==================== 费用计算与分摊 API ====================

@app.post("/cost/calculate", response_model=schemas.CostCalculationDetail)
def calculate_cost_allocation(request: schemas.CostCalculateRequest, db: Session = Depends(get_db)):
    plan = None
    if request.plan_identifier.isdigit():
        plan = crud.get_packing_plan(db, plan_id=int(request.plan_identifier))
    if plan is None:
        plan = crud.get_packing_plan(db, plan_no=request.plan_identifier)
    if plan is None:
        raise HTTPException(status_code=404, detail="配载方案不存在")

    scheme = _resolve_rate_scheme(request.scheme_identifier, db) if request.scheme_identifier else crud.get_default_rate_scheme(db)
    if scheme is None:
        raise HTTPException(status_code=400, detail="未找到可用的费率方案(请先配置默认费率方案或指定方案ID/编码)")

    result = calculate_and_allocate_for_plan(
        db,
        plan_id=plan.id,
        scheme_id=scheme.id,
        calculated_by=request.calculated_by,
        remarks=request.remarks,
        recalculate=request.recalculate,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    calc_id = result.get("calculation_id")
    detail = get_calculation_detail(db, calculation_id=calc_id)
    if "error" in detail:
        raise HTTPException(status_code=500, detail=detail["error"])

    return detail


@app.get("/cost/calculations")
def list_cost_calculations(
    plan_identifier: Optional[str] = None,
    scheme_identifier: Optional[str] = None,
    calculation_status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    plan_id = None
    scheme_id = None

    if plan_identifier:
        plan = None
        if plan_identifier.isdigit():
            plan = crud.get_packing_plan(db, plan_id=int(plan_identifier))
        if plan is None:
            plan = crud.get_packing_plan(db, plan_no=plan_identifier)
        if plan is None:
            raise HTTPException(status_code=404, detail="配载方案不存在")
        plan_id = plan.id

    if scheme_identifier:
        scheme = _resolve_rate_scheme(scheme_identifier, db)
        if scheme is None:
            raise HTTPException(status_code=404, detail="费率方案不存在")
        scheme_id = scheme.id

    calcs = crud.list_cost_calculations(
        db,
        plan_id=plan_id,
        scheme_id=scheme_id,
        calculation_status=calculation_status,
        skip=skip,
        limit=limit,
    )

    result = []
    for calc in calcs:
        scheme = crud.get_rate_scheme(db, scheme_id=calc.scheme_id)
        boxes = crud.get_box_details(db, calc.id)
        allocs = crud.get_cargo_allocations(db, calc.id)
        result.append({
            "id": calc.id,
            "calculation_no": calc.calculation_no,
            "plan_id": calc.plan_id,
            "plan_no": calc.plan_no,
            "plan_version": calc.plan_version,
            "scheme_id": calc.scheme_id,
            "scheme_code": scheme.scheme_code if scheme else "",
            "scheme_name": scheme.scheme_name if scheme else "",
            "carrier": scheme.carrier if scheme else "",
            "currency": calc.currency,
            "total_base_freight": calc.total_base_freight,
            "total_overweight_surcharge": calc.total_overweight_surcharge,
            "total_reefer_surcharge": calc.total_reefer_surcharge,
            "total_frozen_surcharge": calc.total_frozen_surcharge,
            "total_hazard_surcharge": calc.total_hazard_surcharge,
            "total_cost": calc.total_cost,
            "box_count": len(boxes),
            "total_cargo_count": len(allocs),
            "calculation_status": calc.calculation_status,
            "created_at": calc.created_at.isoformat() if calc.created_at else "",
        })
    return result


@app.get("/cost/calculations/{calc_identifier}", response_model=schemas.CostCalculationDetail)
def get_cost_calculation_detail(calc_identifier: str, db: Session = Depends(get_db)):
    calc_id = None
    calc_no = None
    if calc_identifier.isdigit():
        calc_id = int(calc_identifier)
    else:
        calc_no = calc_identifier

    detail = get_calculation_detail(db, calculation_id=calc_id, calculation_no=calc_no)
    if "error" in detail:
        raise HTTPException(status_code=404, detail=detail["error"])
    return detail


@app.get("/plans/{plan_identifier}/cost")
def get_plan_cost_by_plan(
    plan_identifier: str,
    scheme_identifier: Optional[str] = None,
    db: Session = Depends(get_db)
):
    plan = None
    if plan_identifier.isdigit():
        plan = crud.get_packing_plan(db, plan_id=int(plan_identifier))
    if plan is None:
        plan = crud.get_packing_plan(db, plan_no=plan_identifier)
    if plan is None:
        raise HTTPException(status_code=404, detail="配载方案不存在")

    scheme = _resolve_rate_scheme(scheme_identifier, db) if scheme_identifier else crud.get_default_rate_scheme(db)
    if scheme is None:
        raise HTTPException(status_code=400, detail="未找到可用的费率方案")

    existing = crud.find_existing_calculation(
        db,
        plan_id=plan.id,
        scheme_id=scheme.id,
        plan_version=plan.version,
        plan_content_hash=plan.content_hash,
    )
    if existing:
        detail = get_calculation_detail(db, calculation_id=existing.id)
        return {
            "from_cache": True,
            "calculation_id": existing.id,
            "calculation_no": existing.calculation_no,
            "currency": existing.currency,
            "total_cost": existing.total_cost,
            "detail": detail,
        }

    result = calculate_and_allocate_for_plan(
        db,
        plan_id=plan.id,
        scheme_id=scheme.id,
        calculated_by="plan_query_auto",
        remarks=f"按方案 {plan.plan_no} 查询时自动计算",
        recalculate=False,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    detail = get_calculation_detail(db, calculation_id=result["calculation_id"])
    return {
        "from_cache": False,
        "calculation_id": result["calculation_id"],
        "calculation_no": result["calculation_no"],
        "currency": result.get("currency", scheme.currency),
        "total_cost": result.get("total_cost"),
        "detail": detail,
    }


@app.delete("/cost/calculations/{calc_identifier}")
def delete_cost_calculation(calc_identifier: str, db: Session = Depends(get_db)):
    calc_id = None
    calc_no = None
    if calc_identifier.isdigit():
        calc_id = int(calc_identifier)
    else:
        calc_no = calc_identifier

    deleted = crud.delete_cost_calculation(db, calculation_id=calc_id, calculation_no=calc_no)
    if deleted is None:
        raise HTTPException(status_code=404, detail="费用计算记录不存在")
    return {
        "message": "删除成功",
        "calculation_id": deleted.id,
        "calculation_no": deleted.calculation_no,
        "total_cost": deleted.total_cost,
    }


# ==================== 费率方案对比 API ====================

@app.post("/cost/compare", response_model=schemas.RateCompareResult)
def compare_rate_schemes(request: schemas.RateCompareRequest, db: Session = Depends(get_db)):
    if len(request.scheme_identifiers) < 2:
        raise HTTPException(status_code=400, detail="至少需要2个费率方案进行对比")

    plan = None
    if request.plan_identifier.isdigit():
        plan = crud.get_packing_plan(db, plan_id=int(request.plan_identifier))
    if plan is None:
        plan = crud.get_packing_plan(db, plan_no=request.plan_identifier)
    if plan is None:
        raise HTTPException(status_code=404, detail="配载方案不存在")

    scheme_ids = []
    for sid in request.scheme_identifiers:
        scheme = _resolve_rate_scheme(sid, db)
        if scheme is None:
            raise HTTPException(status_code=404, detail=f"费率方案 {sid} 不存在")
        scheme_ids.append(scheme.id)

    result = compare_rate_schemes_for_plan(db, plan.id, scheme_ids)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


# ==================== 货损理赔与责任判定 API ====================

def _resolve_damage_inspection(inspection_identifier: str, db: Session):
    inspection = None
    if inspection_identifier.isdigit():
        inspection = crud.get_damage_inspection(db, inspection_id=int(inspection_identifier))
    if inspection is None:
        inspection = crud.get_damage_inspection(db, inspection_no=inspection_identifier)
    return inspection


def _resolve_claim_record(claim_identifier: str, db: Session):
    claim = None
    if claim_identifier.isdigit():
        claim = crud.get_claim_record(db, claim_id=int(claim_identifier))
    if claim is None:
        claim = crud.get_claim_record(db, claim_no=claim_identifier)
    return claim


@app.post("/damage/inspections", response_model=schemas.CargoDamageInspection)
def create_damage_inspection_api(
    request: schemas.CargoDamageInspectionCreate,
    db: Session = Depends(get_db)
):
    try:
        inspection = crud.create_damage_inspection(
            db,
            request.model_dump(),
            [item.model_dump() for item in request.inspection_items]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "id": inspection.id,
        "inspection_no": inspection.inspection_no,
        "plan_identifier": str(inspection.plan_id),
        "plan_id": inspection.plan_id,
        "plan_no": inspection.plan_no,
        "plan_version": inspection.plan_version or 1,
        "container_no": inspection.container_no,
        "shipment_no": inspection.shipment_no,
        "inspector": inspection.inspector,
        "inspection_date": inspection.inspection_date.isoformat() if inspection.inspection_date else None,
        "total_cargos": inspection.total_cargos,
        "intact_count": inspection.intact_count,
        "minor_damage_count": inspection.minor_damage_count,
        "severe_damage_count": inspection.severe_damage_count,
        "lost_count": inspection.lost_count,
        "remarks": inspection.remarks,
        "status": inspection.status,
        "created_at": inspection.created_at.isoformat() if inspection.created_at else "",
        "updated_at": inspection.updated_at.isoformat() if inspection.updated_at else "",
    }


@app.post("/damage/inspections/{inspection_identifier}/analyze")
def run_damage_analysis_api(
    inspection_identifier: str,
    db: Session = Depends(get_db)
):
    inspection = _resolve_damage_inspection(inspection_identifier, db)
    if not inspection:
        raise HTTPException(status_code=404, detail="检验记录不存在")

    try:
        result = crud.run_damage_analysis(db, inspection.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result


@app.get("/damage/inspections")
def list_damage_inspections_api(
    plan_identifier: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    inspections = crud.list_damage_inspections(
        db,
        plan_identifier=plan_identifier,
        status=status,
        skip=skip,
        limit=limit
    )
    result = []
    for insp in inspections:
        result.append({
            "id": insp.id,
            "inspection_no": insp.inspection_no,
            "plan_id": insp.plan_id,
            "plan_no": insp.plan_no,
            "plan_version": insp.plan_version or 1,
            "container_no": insp.container_no,
            "shipment_no": insp.shipment_no,
            "inspector": insp.inspector,
            "inspection_date": insp.inspection_date.isoformat() if insp.inspection_date else None,
            "total_cargos": insp.total_cargos,
            "intact_count": insp.intact_count,
            "minor_damage_count": insp.minor_damage_count,
            "severe_damage_count": insp.severe_damage_count,
            "lost_count": insp.lost_count,
            "status": insp.status,
            "remarks": insp.remarks,
            "created_at": insp.created_at.isoformat() if insp.created_at else "",
            "updated_at": insp.updated_at.isoformat() if insp.updated_at else "",
        })
    return result


@app.get("/damage/inspections/{inspection_identifier}", response_model=schemas.CargoDamageInspectionDetail)
def get_damage_inspection_detail_api(
    inspection_identifier: str,
    db: Session = Depends(get_db)
):
    inspection = _resolve_damage_inspection(inspection_identifier, db)
    if not inspection:
        raise HTTPException(status_code=404, detail="检验记录不存在")

    inspection_items = crud.get_inspection_items(db, inspection.id)
    damage_inferences = crud.get_damage_inferences(db, inspection.id)

    claim_record = None
    claim_items = []
    if hasattr(inspection, 'claim_record') and inspection.claim_record:
        claim_record = inspection.claim_record
        claim_items = crud.get_claim_items(db, claim_record.id)

    items_list = []
    for item in inspection_items:
        items_list.append({
            "id": item.id,
            "inspection_id": item.inspection_id,
            "packed_cargo_id": item.packed_cargo_id,
            "cargo_id": item.cargo_id,
            "cargo_name": item.cargo_name,
            "item_no": item.item_no,
            "damage_status": item.damage_status,
            "damage_type": item.damage_type,
            "declared_value": item.declared_value,
            "damage_description": item.damage_description,
            "position_x": item.position_x,
            "position_y": item.position_y,
            "position_z": item.position_z,
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

    inferences_list = []
    for inf in damage_inferences:
        inferences_list.append({
            "id": inf.id,
            "inspection_id": inf.inspection_id,
            "inspection_item_id": inf.inspection_item_id,
            "cargo_id": inf.cargo_id,
            "cargo_name": inf.cargo_name,
            "inferred_cause": inf.inferred_cause,
            "confidence_level": inf.confidence_level,
            "responsibility": inf.responsibility,
            "inference_detail": inf.inference_detail or {},
            "evidence_list": inf.evidence_list or [],
            "explanation": inf.explanation,
            "created_at": inf.created_at.isoformat() if inf.created_at else "",
        })

    claim_data = None
    if claim_record:
        claim_items_list = []
        for ci in claim_items:
            claim_items_list.append({
                "id": ci.id,
                "claim_id": ci.claim_id,
                "inspection_item_id": ci.inspection_item_id,
                "cargo_id": ci.cargo_id,
                "cargo_name": ci.cargo_name,
                "damage_status": ci.damage_status,
                "damage_type": ci.damage_type,
                "declared_value": ci.declared_value,
                "claim_ratio": ci.claim_ratio,
                "claim_amount": ci.claim_amount,
                "primary_responsibility": ci.primary_responsibility,
                "created_at": ci.created_at.isoformat() if ci.created_at else "",
            })
        claim_data = {
            "id": claim_record.id,
            "claim_no": claim_record.claim_no,
            "inspection_id": claim_record.inspection_id,
            "plan_id": claim_record.plan_id,
            "plan_no": claim_record.plan_no,
            "container_no": claim_record.container_no,
            "shipment_no": claim_record.shipment_no,
            "total_declared_value": claim_record.total_declared_value,
            "total_claim_amount": claim_record.total_claim_amount,
            "minor_damage_amount": claim_record.minor_damage_amount,
            "severe_damage_amount": claim_record.severe_damage_amount,
            "lost_amount": claim_record.lost_amount,
            "carrier_responsibility_amount": claim_record.carrier_responsibility_amount,
            "packer_responsibility_amount": claim_record.packer_responsibility_amount,
            "shipper_responsibility_amount": claim_record.shipper_responsibility_amount,
            "force_majeure_amount": claim_record.force_majeure_amount,
            "status": claim_record.status,
            "handler": claim_record.handler,
            "remarks": claim_record.remarks,
            "claim_date": claim_record.claim_date.isoformat() if claim_record.claim_date else None,
            "created_at": claim_record.created_at.isoformat() if claim_record.created_at else "",
            "updated_at": claim_record.updated_at.isoformat() if claim_record.updated_at else "",
            "claim_items": claim_items_list,
        }

    return {
        "id": inspection.id,
        "inspection_no": inspection.inspection_no,
        "plan_identifier": str(inspection.plan_id),
        "plan_id": inspection.plan_id,
        "plan_no": inspection.plan_no,
        "plan_version": inspection.plan_version or 1,
        "container_no": inspection.container_no,
        "shipment_no": inspection.shipment_no,
        "inspector": inspection.inspector,
        "inspection_date": inspection.inspection_date.isoformat() if inspection.inspection_date else None,
        "total_cargos": inspection.total_cargos,
        "intact_count": inspection.intact_count,
        "minor_damage_count": inspection.minor_damage_count,
        "severe_damage_count": inspection.severe_damage_count,
        "lost_count": inspection.lost_count,
        "remarks": inspection.remarks,
        "status": inspection.status,
        "created_at": inspection.created_at.isoformat() if inspection.created_at else "",
        "updated_at": inspection.updated_at.isoformat() if inspection.updated_at else "",
        "inspection_items": items_list,
        "damage_inferences": inferences_list,
        "claim_record": claim_data,
    }


@app.get("/damage/claims")
def list_claim_records_api(
    plan_identifier: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    claims = crud.list_claim_records(
        db,
        plan_identifier=plan_identifier,
        status=status,
        skip=skip,
        limit=limit
    )
    result = []
    for claim in claims:
        result.append({
            "id": claim.id,
            "claim_no": claim.claim_no,
            "inspection_id": claim.inspection_id,
            "plan_id": claim.plan_id,
            "plan_no": claim.plan_no,
            "container_no": claim.container_no,
            "shipment_no": claim.shipment_no,
            "total_declared_value": claim.total_declared_value,
            "total_claim_amount": claim.total_claim_amount,
            "minor_damage_amount": claim.minor_damage_amount,
            "severe_damage_amount": claim.severe_damage_amount,
            "lost_amount": claim.lost_amount,
            "carrier_responsibility_amount": claim.carrier_responsibility_amount,
            "packer_responsibility_amount": claim.packer_responsibility_amount,
            "shipper_responsibility_amount": claim.shipper_responsibility_amount,
            "force_majeure_amount": claim.force_majeure_amount,
            "status": claim.status,
            "handler": claim.handler,
            "remarks": claim.remarks,
            "claim_date": claim.claim_date.isoformat() if claim.claim_date else None,
            "created_at": claim.created_at.isoformat() if claim.created_at else "",
            "updated_at": claim.updated_at.isoformat() if claim.updated_at else "",
        })
    return result


@app.get("/damage/claims/statistics")
def get_claim_statistics_api(
    plan_identifier: Optional[str] = None,
    db: Session = Depends(get_db)
):
    stats = crud.get_claim_statistics_by_responsibility(db, plan_identifier=plan_identifier)
    return stats


@app.get("/damage/claims/{claim_identifier}", response_model=schemas.ClaimRecordDetail)
def get_claim_record_detail_api(
    claim_identifier: str,
    db: Session = Depends(get_db)
):
    claim = _resolve_claim_record(claim_identifier, db)
    if not claim:
        raise HTTPException(status_code=404, detail="理赔记录不存在")

    claim_items = crud.get_claim_items(db, claim.id)
    claim_items_list = []
    for ci in claim_items:
        claim_items_list.append({
            "id": ci.id,
            "claim_id": ci.claim_id,
            "inspection_item_id": ci.inspection_item_id,
            "cargo_id": ci.cargo_id,
            "cargo_name": ci.cargo_name,
            "damage_status": ci.damage_status,
            "damage_type": ci.damage_type,
            "declared_value": ci.declared_value,
            "claim_ratio": ci.claim_ratio,
            "claim_amount": ci.claim_amount,
            "primary_responsibility": ci.primary_responsibility,
            "created_at": ci.created_at.isoformat() if ci.created_at else "",
        })

    return {
        "id": claim.id,
        "claim_no": claim.claim_no,
        "inspection_id": claim.inspection_id,
        "plan_id": claim.plan_id,
        "plan_no": claim.plan_no,
        "container_no": claim.container_no,
        "shipment_no": claim.shipment_no,
        "total_declared_value": claim.total_declared_value,
        "total_claim_amount": claim.total_claim_amount,
        "minor_damage_amount": claim.minor_damage_amount,
        "severe_damage_amount": claim.severe_damage_amount,
        "lost_amount": claim.lost_amount,
        "carrier_responsibility_amount": claim.carrier_responsibility_amount,
        "packer_responsibility_amount": claim.packer_responsibility_amount,
        "shipper_responsibility_amount": claim.shipper_responsibility_amount,
        "force_majeure_amount": claim.force_majeure_amount,
        "status": claim.status,
        "handler": claim.handler,
        "remarks": claim.remarks,
        "claim_date": claim.claim_date.isoformat() if claim.claim_date else None,
        "created_at": claim.created_at.isoformat() if claim.created_at else "",
        "updated_at": claim.updated_at.isoformat() if claim.updated_at else "",
        "claim_items": claim_items_list,
    }


@app.delete("/damage/inspections/{inspection_identifier}")
def delete_damage_inspection_api(
    inspection_identifier: str,
    db: Session = Depends(get_db)
):
    inspection = _resolve_damage_inspection(inspection_identifier, db)
    if not inspection:
        raise HTTPException(status_code=404, detail="检验记录不存在")

    db.delete(inspection)
    db.commit()

    return {
        "message": "删除成功",
        "inspection_id": inspection.id,
        "inspection_no": inspection.inspection_no,
    }


# ==================== 理赔趋势分析 API ====================

@app.post("/damage/claims/trend", response_model=schemas.TrendAnalysisResult)
def get_claim_trend_analysis_api(
    request: schemas.TrendAnalysisRequest,
    db: Session = Depends(get_db)
):
    result = crud.get_claim_trend_analysis(
        db,
        time_granularity=request.time_granularity,
        carrier=request.carrier,
        container_type=request.container_type,
        damage_type=request.damage_type,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    return result


# ==================== 预警规则管理 API ====================

def _resolve_alert_rule(rule_identifier: str, db: Session):
    rule = None
    if rule_identifier.isdigit():
        rule = crud.get_alert_rule(db, rule_id=int(rule_identifier))
    if rule is None:
        rule = crud.get_alert_rule(db, rule_no=rule_identifier)
    return rule


@app.get("/damage/alerts/rules", response_model=List[schemas.AlertRule])
def list_alert_rules_api(
    only_active: bool = False,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    rules = crud.list_alert_rules(db, skip=skip, limit=limit, only_active=only_active)
    result = []
    for r in rules:
        result.append({
            "id": r.id,
            "rule_no": r.rule_no,
            "rule_name": r.rule_name,
            "rule_type": r.rule_type,
            "description": r.description,
            "is_active": r.is_active,
            "scope": r.scope,
            "scope_value": r.scope_value,
            "threshold_value": r.threshold_value,
            "consecutive_months": r.consecutive_months,
            "time_granularity": r.time_granularity,
            "suggested_action": r.suggested_action,
            "created_by": r.created_by,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "updated_at": r.updated_at.isoformat() if r.updated_at else "",
        })
    return result


@app.post("/damage/alerts/rules", response_model=schemas.AlertRule)
def create_alert_rule_api(
    request: schemas.AlertRuleCreate,
    db: Session = Depends(get_db)
):
    rule = crud.create_alert_rule(db, request.model_dump())
    return {
        "id": rule.id,
        "rule_no": rule.rule_no,
        "rule_name": rule.rule_name,
        "rule_type": rule.rule_type,
        "description": rule.description,
        "is_active": rule.is_active,
        "scope": rule.scope,
        "scope_value": rule.scope_value,
        "threshold_value": rule.threshold_value,
        "consecutive_months": rule.consecutive_months,
        "time_granularity": rule.time_granularity,
        "suggested_action": rule.suggested_action,
        "created_by": rule.created_by,
        "created_at": rule.created_at.isoformat() if rule.created_at else "",
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else "",
    }


@app.get("/damage/alerts/rules/{rule_identifier}", response_model=schemas.AlertRule)
def get_alert_rule_api(
    rule_identifier: str,
    db: Session = Depends(get_db)
):
    rule = _resolve_alert_rule(rule_identifier, db)
    if not rule:
        raise HTTPException(status_code=404, detail="预警规则不存在")
    return {
        "id": rule.id,
        "rule_no": rule.rule_no,
        "rule_name": rule.rule_name,
        "rule_type": rule.rule_type,
        "description": rule.description,
        "is_active": rule.is_active,
        "scope": rule.scope,
        "scope_value": rule.scope_value,
        "threshold_value": rule.threshold_value,
        "consecutive_months": rule.consecutive_months,
        "time_granularity": rule.time_granularity,
        "suggested_action": rule.suggested_action,
        "created_by": rule.created_by,
        "created_at": rule.created_at.isoformat() if rule.created_at else "",
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else "",
    }


@app.put("/damage/alerts/rules/{rule_identifier}", response_model=schemas.AlertRule)
def update_alert_rule_api(
    rule_identifier: str,
    request: schemas.AlertRuleUpdate,
    db: Session = Depends(get_db)
):
    rule = _resolve_alert_rule(rule_identifier, db)
    if not rule:
        raise HTTPException(status_code=404, detail="预警规则不存在")
    updated = crud.update_alert_rule(db, rule.id, request.model_dump(exclude_unset=True))
    return {
        "id": updated.id,
        "rule_no": updated.rule_no,
        "rule_name": updated.rule_name,
        "rule_type": updated.rule_type,
        "description": updated.description,
        "is_active": updated.is_active,
        "scope": updated.scope,
        "scope_value": updated.scope_value,
        "threshold_value": updated.threshold_value,
        "consecutive_months": updated.consecutive_months,
        "time_granularity": updated.time_granularity,
        "suggested_action": updated.suggested_action,
        "created_by": updated.created_by,
        "created_at": updated.created_at.isoformat() if updated.created_at else "",
        "updated_at": updated.updated_at.isoformat() if updated.updated_at else "",
    }


@app.delete("/damage/alerts/rules/{rule_identifier}")
def delete_alert_rule_api(
    rule_identifier: str,
    db: Session = Depends(get_db)
):
    rule = _resolve_alert_rule(rule_identifier, db)
    if not rule:
        raise HTTPException(status_code=404, detail="预警规则不存在")
    crud.delete_alert_rule(db, rule.id)
    return {
        "message": "删除成功",
        "rule_id": rule.id,
        "rule_no": rule.rule_no,
    }


# ==================== 预警引擎运行 API ====================

@app.post("/damage/alerts/engine/run", response_model=schemas.AlertEngineRunResult)
def run_alert_engine_api(db: Session = Depends(get_db)):
    result = crud.run_alert_engine(db)
    events_data = []
    for e in result["triggered_events"]:
        events_data.append({
            "id": e.id,
            "event_no": e.event_no,
            "rule_id": e.rule_id,
            "rule_no": e.rule_no,
            "rule_name": e.rule_name,
            "trigger_time": e.trigger_time.isoformat() if e.trigger_time else "",
            "trigger_condition": e.trigger_condition,
            "trigger_period": e.trigger_period,
            "scope": e.scope,
            "scope_value": e.scope_value,
            "actual_value": e.actual_value,
            "threshold_value": e.threshold_value,
            "related_claim_ids": e.related_claim_ids or [],
            "suggested_action": e.suggested_action,
            "status": e.status,
            "handler": e.handler,
            "handled_at": e.handled_at.isoformat() if e.handled_at else None,
            "handling_notes": e.handling_notes,
            "created_at": e.created_at.isoformat() if e.created_at else "",
            "updated_at": e.updated_at.isoformat() if e.updated_at else "",
        })
    return {
        "triggered_count": result["triggered_count"],
        "triggered_events": events_data,
    }


# ==================== 预警事件管理 API ====================

def _resolve_alert_event(event_identifier: str, db: Session):
    event = None
    if event_identifier.isdigit():
        event = crud.get_alert_event(db, event_id=int(event_identifier))
    if event is None:
        event = crud.get_alert_event(db, event_no=event_identifier)
    return event


@app.get("/damage/alerts/events", response_model=List[schemas.AlertEvent])
def list_alert_events_api(
    status: Optional[str] = None,
    only_pending: bool = False,
    rule_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    events = crud.list_alert_events(
        db,
        status=status,
        only_pending=only_pending,
        rule_id=rule_id,
        skip=skip,
        limit=limit,
    )
    result = []
    for e in events:
        result.append({
            "id": e.id,
            "event_no": e.event_no,
            "rule_id": e.rule_id,
            "rule_no": e.rule_no,
            "rule_name": e.rule_name,
            "trigger_time": e.trigger_time.isoformat() if e.trigger_time else "",
            "trigger_condition": e.trigger_condition,
            "trigger_period": e.trigger_period,
            "scope": e.scope,
            "scope_value": e.scope_value,
            "actual_value": e.actual_value,
            "threshold_value": e.threshold_value,
            "related_claim_ids": e.related_claim_ids or [],
            "suggested_action": e.suggested_action,
            "status": e.status,
            "handler": e.handler,
            "handled_at": e.handled_at.isoformat() if e.handled_at else None,
            "handling_notes": e.handling_notes,
            "created_at": e.created_at.isoformat() if e.created_at else "",
            "updated_at": e.updated_at.isoformat() if e.updated_at else "",
        })
    return result


@app.get("/damage/alerts/events/pending")
def get_pending_alert_events_api(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    events = crud.list_alert_events(db, only_pending=True, skip=skip, limit=limit)
    result = []
    for e in events:
        result.append({
            "id": e.id,
            "event_no": e.event_no,
            "rule_id": e.rule_id,
            "rule_no": e.rule_no,
            "rule_name": e.rule_name,
            "trigger_time": e.trigger_time.isoformat() if e.trigger_time else "",
            "trigger_condition": e.trigger_condition,
            "trigger_period": e.trigger_period,
            "scope": e.scope,
            "scope_value": e.scope_value,
            "actual_value": e.actual_value,
            "threshold_value": e.threshold_value,
            "related_claim_count": len(e.related_claim_ids or []),
            "suggested_action": e.suggested_action,
            "status": e.status,
            "handler": e.handler,
            "created_at": e.created_at.isoformat() if e.created_at else "",
        })
    return {
        "total": len(result),
        "events": result,
    }


@app.get("/damage/alerts/events/history")
def get_history_alert_events_api(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    events = crud.list_alert_events(
        db,
        only_pending=False,
        skip=skip,
        limit=limit,
    )
    result = []
    for e in events:
        result.append({
            "id": e.id,
            "event_no": e.event_no,
            "rule_id": e.rule_id,
            "rule_no": e.rule_no,
            "rule_name": e.rule_name,
            "trigger_time": e.trigger_time.isoformat() if e.trigger_time else "",
            "trigger_condition": e.trigger_condition,
            "trigger_period": e.trigger_period,
            "scope": e.scope,
            "scope_value": e.scope_value,
            "actual_value": e.actual_value,
            "threshold_value": e.threshold_value,
            "status": e.status,
            "handler": e.handler,
            "handled_at": e.handled_at.isoformat() if e.handled_at else None,
            "handling_notes": e.handling_notes,
            "created_at": e.created_at.isoformat() if e.created_at else "",
        })
    return {
        "total": len(result),
        "events": result,
    }


@app.get("/damage/alerts/events/{event_identifier}", response_model=schemas.AlertEventDetail)
def get_alert_event_detail_api(
    event_identifier: str,
    db: Session = Depends(get_db)
):
    event = _resolve_alert_event(event_identifier, db)
    if not event:
        raise HTTPException(status_code=404, detail="预警事件不存在")

    related_claims = []
    if event.related_claim_ids:
        for cid in event.related_claim_ids:
            claim = crud.get_claim_record(db, claim_id=cid)
            if claim:
                related_claims.append({
                    "id": claim.id,
                    "claim_no": claim.claim_no,
                    "plan_no": claim.plan_no,
                    "container_no": claim.container_no,
                    "shipment_no": claim.shipment_no,
                    "total_claim_amount": claim.total_claim_amount,
                    "status": claim.status,
                    "claim_date": claim.claim_date.isoformat() if claim.claim_date else None,
                })

    return {
        "id": event.id,
        "event_no": event.event_no,
        "rule_id": event.rule_id,
        "rule_no": event.rule_no,
        "rule_name": event.rule_name,
        "trigger_time": event.trigger_time.isoformat() if event.trigger_time else "",
        "trigger_condition": event.trigger_condition,
        "trigger_period": event.trigger_period,
        "scope": event.scope,
        "scope_value": event.scope_value,
        "actual_value": event.actual_value,
        "threshold_value": event.threshold_value,
        "related_claim_ids": event.related_claim_ids or [],
        "suggested_action": event.suggested_action,
        "status": event.status,
        "handler": event.handler,
        "handled_at": event.handled_at.isoformat() if event.handled_at else None,
        "handling_notes": event.handling_notes,
        "created_at": event.created_at.isoformat() if event.created_at else "",
        "updated_at": event.updated_at.isoformat() if event.updated_at else "",
        "related_claims": related_claims,
    }


@app.post("/damage/alerts/events/{event_identifier}/close", response_model=schemas.AlertEvent)
def close_alert_event_api(
    event_identifier: str,
    request: schemas.AlertEventCloseRequest,
    db: Session = Depends(get_db)
):
    if not request.handling_notes or not request.handling_notes.strip():
        raise HTTPException(status_code=400, detail="关闭预警事件必须填写处理说明")
    event = _resolve_alert_event(event_identifier, db)
    if not event:
        raise HTTPException(status_code=404, detail="预警事件不存在")
    closed = crud.close_alert_event(db, event.id, request.handling_notes.strip(), request.handler)
    return {
        "id": closed.id,
        "event_no": closed.event_no,
        "rule_id": closed.rule_id,
        "rule_no": closed.rule_no,
        "rule_name": closed.rule_name,
        "trigger_time": closed.trigger_time.isoformat() if closed.trigger_time else "",
        "trigger_condition": closed.trigger_condition,
        "trigger_period": closed.trigger_period,
        "scope": closed.scope,
        "scope_value": closed.scope_value,
        "actual_value": closed.actual_value,
        "threshold_value": closed.threshold_value,
        "related_claim_ids": closed.related_claim_ids or [],
        "suggested_action": closed.suggested_action,
        "status": closed.status,
        "handler": closed.handler,
        "handled_at": closed.handled_at.isoformat() if closed.handled_at else None,
        "handling_notes": closed.handling_notes,
        "created_at": closed.created_at.isoformat() if closed.created_at else "",
        "updated_at": closed.updated_at.isoformat() if closed.updated_at else "",
    }


@app.post("/damage/alerts/events/{event_identifier}/handle", response_model=schemas.AlertEvent)
def handle_alert_event_api(
    event_identifier: str,
    request: schemas.AlertEventHandleRequest,
    db: Session = Depends(get_db)
):
    event = _resolve_alert_event(event_identifier, db)
    if not event:
        raise HTTPException(status_code=404, detail="预警事件不存在")
    handled = crud.handle_alert_event(db, event.id, request.handler, request.handling_notes)
    return {
        "id": handled.id,
        "event_no": handled.event_no,
        "rule_id": handled.rule_id,
        "rule_no": handled.rule_no,
        "rule_name": handled.rule_name,
        "trigger_time": handled.trigger_time.isoformat() if handled.trigger_time else "",
        "trigger_condition": handled.trigger_condition,
        "trigger_period": handled.trigger_period,
        "scope": handled.scope,
        "scope_value": handled.scope_value,
        "actual_value": handled.actual_value,
        "threshold_value": handled.threshold_value,
        "related_claim_ids": handled.related_claim_ids or [],
        "suggested_action": handled.suggested_action,
        "status": handled.status,
        "handler": handled.handler,
        "handled_at": handled.handled_at.isoformat() if handled.handled_at else None,
        "handling_notes": handled.handling_notes,
        "created_at": handled.created_at.isoformat() if handled.created_at else "",
        "updated_at": handled.updated_at.isoformat() if handled.updated_at else "",
    }


