from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List

from app.database import engine, get_db, Base
from app import models, schemas, crud
from app.packing.algorithm import pack_boxes, Box

Base.metadata.create_all(bind=engine)

app = FastAPI(title="集装箱三维配载计算服务", version="1.0.0")

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


@app.post("/packing/{container_id}", response_model=schemas.PackingResult)
def calculate_packing(container_id: int, cargo_ids: List[int], db: Session = Depends(get_db)):
    container = crud.get_container(db, container_id=container_id)
    if container is None:
        raise HTTPException(status_code=404, detail="集装箱不存在")

    boxes = []
    for cargo_id in cargo_ids:
        cargo = crud.get_cargo(db, cargo_id=cargo_id)
        if cargo is None:
            raise HTTPException(status_code=404, detail=f"货物 ID {cargo_id} 不存在")
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
