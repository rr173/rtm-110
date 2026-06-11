from typing import List, Dict, Any
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class CargoInfo:
    packed_cargo_id: int
    cargo_id: int
    cargo_name: str
    x: float
    y: float
    z: float
    length: float
    width: float
    height: float
    weight: float
    orientation: str
    max_top_load: float
    cumulative_load: float = 0.0


def _is_flipped_orientation(orientation: str) -> bool:
    return orientation.startswith("flipped")


def _get_pressure_status(utilization: float) -> str:
    if utilization >= 0.95:
        return "danger"
    elif utilization >= 0.80:
        return "warning"
    else:
        return "normal"


def _overlap_area(
    x1: float, y1: float, l1: float, w1: float,
    x2: float, y2: float, l2: float, w2: float
) -> float:
    x_overlap_start = max(x1, x2)
    x_overlap_end = min(x1 + l1, x2 + l2)
    y_overlap_start = max(y1, y2)
    y_overlap_end = min(y1 + w1, y2 + w2)
    if x_overlap_end > x_overlap_start and y_overlap_end > y_overlap_start:
        return (x_overlap_end - x_overlap_start) * (y_overlap_end - y_overlap_start)
    return 0.0


def _find_direct_supporters(
    target: CargoInfo,
    all_cargos: List[CargoInfo]
) -> List[tuple]:
    """找出直接支撑 target 的所有货物及其接触面积"""
    supporters = []
    for c in all_cargos:
        if c.packed_cargo_id == target.packed_cargo_id:
            continue
        c_top_z = c.z + c.height
        if abs(c_top_z - target.z) > 1.0:
            continue
        overlap = _overlap_area(
            target.x, target.y, target.length, target.width,
            c.x, c.y, c.length, c.width
        )
        if overlap > 0.001:
            supporters.append((c, overlap))
    return supporters


def _distribute_load_top_down(cargos: List[CargoInfo]):
    """自上而下承压传播：每个货物把自身重量+已承受的重量，按接触面积分配给下面支撑它的货物"""
    sorted_by_z_desc = sorted(cargos, key=lambda c: -(c.z + c.height))

    for upper in sorted_by_z_desc:
        load_to_distribute = upper.weight + upper.cumulative_load
        supporters = _find_direct_supporters(upper, cargos)

        if not supporters:
            continue

        total_support_area = sum(area for _, area in supporters)
        if total_support_area <= 0.001:
            continue

        for supporter, contact_area in supporters:
            weight_ratio = contact_area / total_support_area
            supporter.cumulative_load += load_to_distribute * weight_ratio


def _assign_layers(cargos: List[CargoInfo]) -> Dict[int, List[CargoInfo]]:
    if not cargos:
        return {}

    sorted_cargos = sorted(cargos, key=lambda c: c.z)

    layers = defaultdict(list)
    current_layer_z = None
    layer_index = 0

    for c in sorted_cargos:
        if current_layer_z is None:
            current_layer_z = c.z
            layers[layer_index].append(c)
        elif abs(c.z - current_layer_z) < 1.0:
            layers[layer_index].append(c)
        else:
            layer_index += 1
            current_layer_z = c.z
            layers[layer_index].append(c)

    return dict(layers)


def generate_stowage_report(
    plan_id: int,
    plan_no: str,
    plan_version: int,
    packed_cargos: List[Dict[str, Any]],
    cargo_info_map: Dict[int, Dict[str, Any]]
) -> Dict[str, Any]:
    cargos = []
    for pc in packed_cargos:
        cargo_id = pc["cargo_id"]
        original_cargo = cargo_info_map.get(cargo_id, {})
        max_top_load = original_cargo.get("max_top_load", 0.0)

        cargos.append(CargoInfo(
            packed_cargo_id=pc["id"],
            cargo_id=cargo_id,
            cargo_name=pc["cargo_name"],
            x=pc["x"],
            y=pc["y"],
            z=pc["z"],
            length=pc["length"],
            width=pc["width"],
            height=pc["height"],
            weight=pc["weight"],
            orientation=pc["orientation"],
            max_top_load=max_top_load,
            cumulative_load=0.0
        ))

    _distribute_load_top_down(cargos)

    layers_dict = _assign_layers(cargos)

    layers_result = []
    total_weight = 0.0
    weighted_utilization_sum = 0.0
    flipped_count = 0
    warning_count = 0
    danger_count = 0

    for layer_idx in sorted(layers_dict.keys()):
        layer_cargos = layers_dict[layer_idx]
        layer_z_start = min(c.z for c in layer_cargos)
        layer_z_end = max(c.z + c.height for c in layer_cargos)

        layer_items = []
        for c in layer_cargos:
            top_load = c.cumulative_load
            is_flipped = _is_flipped_orientation(c.orientation)

            if c.max_top_load > 0.001:
                utilization = top_load / c.max_top_load
            else:
                utilization = 1.0 if top_load > 0.001 else 0.0

            pressure_status = _get_pressure_status(utilization)

            if is_flipped:
                flipped_count += 1
            if pressure_status == "warning":
                warning_count += 1
            elif pressure_status == "danger":
                danger_count += 1

            total_weight += c.weight
            weighted_utilization_sum += utilization * c.weight

            layer_items.append({
                "packed_cargo_id": c.packed_cargo_id,
                "cargo_id": c.cargo_id,
                "cargo_name": c.cargo_name,
                "x": c.x,
                "y": c.y,
                "z": c.z,
                "length": c.length,
                "width": c.width,
                "height": c.height,
                "weight": c.weight,
                "orientation": c.orientation,
                "original_orientation": "original",
                "is_flipped": is_flipped,
                "max_top_load": c.max_top_load,
                "top_load_weight": round(top_load, 2),
                "pressure_utilization": round(utilization, 4),
                "pressure_status": pressure_status
            })

        layers_result.append({
            "layer_index": layer_idx + 1,
            "z_start": round(layer_z_start, 2),
            "z_end": round(layer_z_end, 2),
            "cargos": layer_items
        })

    health_score = 0.0
    if total_weight > 0.001:
        avg_utilization = weighted_utilization_sum / total_weight
        health_score = max(0.0, min(100.0, (1.0 - avg_utilization) * 100.0))

    total_cargos = len(cargos)
    statistics = {
        "total_cargos": total_cargos,
        "flipped_count": flipped_count,
        "flipped_ratio": round(flipped_count / total_cargos, 4) if total_cargos > 0 else 0,
        "warning_count": warning_count,
        "warning_ratio": round(warning_count / total_cargos, 4) if total_cargos > 0 else 0,
        "danger_count": danger_count,
        "danger_ratio": round(danger_count / total_cargos, 4) if total_cargos > 0 else 0,
        "total_layers": len(layers_result)
    }

    overall_health = {
        "score": round(health_score, 2),
        "level": "excellent" if health_score >= 90 else (
            "good" if health_score >= 75 else (
                "fair" if health_score >= 60 else "poor"
            )
        ),
        "weighted_avg_utilization": round(weighted_utilization_sum / total_weight, 4) if total_weight > 0.001 else 0
    }

    summary = {
        "plan_id": plan_id,
        "plan_no": plan_no,
        "plan_version": plan_version,
        "total_cargos": total_cargos,
        "total_layers": len(layers_result),
        "flipped_count": flipped_count,
        "warning_count": warning_count,
        "danger_count": danger_count,
        "health_score": round(health_score, 2)
    }

    return {
        "layers": layers_result,
        "statistics": statistics,
        "overall_health": overall_health,
        "summary": summary
    }
