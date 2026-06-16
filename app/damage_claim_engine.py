from typing import List, Dict, Any, Tuple
from datetime import datetime
import math

DAMAGE_STATUS_INTACT = "intact"
DAMAGE_STATUS_MINOR = "minor_damage"
DAMAGE_STATUS_SEVERE = "severe_damage"
DAMAGE_STATUS_LOST = "lost"

DAMAGE_TYPE_CRUSH = "crush"
DAMAGE_TYPE_WET = "wet"
DAMAGE_TYPE_TILT = "tilt"
DAMAGE_TYPE_TEMPERATURE = "temperature"
DAMAGE_TYPE_CHEMICAL = "chemical"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

RESPONSIBILITY_CARRIER = "carrier"
RESPONSIBILITY_PACKER = "packer"
RESPONSIBILITY_SHIPPER = "shipper"
RESPONSIBILITY_FORCE_MAJEURE = "force_majeure"

CLAIM_RATIO_MINOR = 0.5
CLAIM_RATIO_SEVERE = 0.8
CLAIM_RATIO_LOST = 1.0

PRESSURE_THRESHOLD_RATIO = 0.9
COG_OFFSET_THRESHOLD = 0.1


def _calculate_top_pressure(
    target_cargo: Dict[str, Any],
    all_cargos: List[Dict[str, Any]]
) -> float:
    total_weight = 0.0
    tx1, ty1, tz1 = target_cargo["x"], target_cargo["y"], target_cargo["z"]
    tx2 = tx1 + target_cargo["length"]
    ty2 = ty1 + target_cargo["width"]
    tz2 = tz1 + target_cargo["height"]

    for cargo in all_cargos:
        if cargo.get("id") == target_cargo.get("id"):
            continue
        cx1, cy1, cz1 = cargo["x"], cargo["y"], cargo["z"]
        cx2 = cx1 + cargo["length"]
        cy2 = cy1 + cargo["width"]

        overlap_x = max(0, min(tx2, cx2) - max(tx1, cx1))
        overlap_y = max(0, min(ty2, cy2) - max(ty1, cy1))
        overlap_area = overlap_x * overlap_y

        if overlap_area > 0 and cz1 >= tz2 - 1:
            total_weight += cargo.get("weight", 0)

    return total_weight


def _is_door_side(cargo: Dict[str, Any], container_length: float) -> bool:
    return cargo["x"] + cargo["length"] >= container_length - 10


def _is_bottom_layer(cargo: Dict[str, Any]) -> bool:
    return cargo["z"] <= 10


def _calculate_stack_layer(
    target_cargo: Dict[str, Any],
    all_cargos: List[Dict[str, Any]]
) -> int:
    layer = 1
    tz = target_cargo["z"]
    height = target_cargo["height"]

    for cargo in all_cargos:
        if cargo.get("id") == target_cargo.get("id"):
            continue
        if cargo["z"] + cargo["height"] <= tz + 1:
            cx1, cy1 = cargo["x"], cargo["y"]
            cx2 = cx1 + cargo["length"]
            cy2 = cy1 + cargo["width"]
            tx1, ty1 = target_cargo["x"], target_cargo["y"]
            tx2 = tx1 + target_cargo["length"]
            ty2 = ty1 + target_cargo["width"]

            overlap_x = max(0, min(tx2, cx2) - max(tx1, cx1))
            overlap_y = max(0, min(ty2, cy2) - max(ty1, cy1))
            overlap_area = overlap_x * overlap_y

            if overlap_area > 0:
                layer += 1

    return layer


def _get_adjacent_cargos(
    target_cargo: Dict[str, Any],
    all_cargos: List[Dict[str, Any]],
    max_distance: float = 100.0
) -> List[Dict[str, Any]]:
    adjacent = []
    tx1, ty1, tz1 = target_cargo["x"], target_cargo["y"], target_cargo["z"]
    tx2 = tx1 + target_cargo["length"]
    ty2 = ty1 + target_cargo["width"]
    tz2 = tz1 + target_cargo["height"]

    for cargo in all_cargos:
        if cargo.get("id") == target_cargo.get("id"):
            continue
        cx1, cy1, cz1 = cargo["x"], cargo["y"], cargo["z"]
        cx2 = cx1 + cargo["length"]
        cy2 = cy1 + cargo["width"]
        cz2 = cz1 + cargo["height"]

        dx = max(0, max(tx1 - cx2, cx1 - tx2))
        dy = max(0, max(ty1 - cy2, cy1 - ty2))
        dz = max(0, max(tz1 - cz2, cz1 - tz2))

        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        if distance <= max_distance:
            adjacent.append(cargo)

    return adjacent


def _check_crush_damage(
    inspection_item: Dict[str, Any],
    all_cargos: List[Dict[str, Any]],
    plan_data: Dict[str, Any]
) -> Dict[str, Any]:
    result = {
        "cause": DAMAGE_TYPE_CRUSH,
        "is_applicable": False,
        "confidence": CONFIDENCE_LOW,
        "responsibility": RESPONSIBILITY_PACKER,
        "evidence": [],
        "detail": {}
    }

    top_pressure = inspection_item.get("top_pressure_weight", 0)
    max_top_load = inspection_item.get("max_top_load", 0)

    if max_top_load <= 0:
        return result

    pressure_ratio = top_pressure / max_top_load if max_top_load > 0 else 0

    if pressure_ratio >= PRESSURE_THRESHOLD_RATIO:
        result["is_applicable"] = True
        result["detail"] = {
            "top_pressure_kg": round(top_pressure, 2),
            "max_top_load_kg": round(max_top_load, 2),
            "pressure_ratio": round(pressure_ratio, 4),
            "threshold_ratio": PRESSURE_THRESHOLD_RATIO
        }

        if pressure_ratio >= 1.0:
            result["confidence"] = CONFIDENCE_HIGH
            result["evidence"].append(f"上方累计承压({top_pressure:.1f}kg)超过承压上限({max_top_load:.1f}kg)，超限比例{((pressure_ratio-1)*100):.1f}%")
        elif pressure_ratio >= PRESSURE_THRESHOLD_RATIO:
            result["confidence"] = CONFIDENCE_MEDIUM
            result["evidence"].append(f"上方累计承压({top_pressure:.1f}kg)达到承压上限的{pressure_ratio*100:.1f}%，已超过90%预警阈值")

        result["responsibility"] = RESPONSIBILITY_PACKER
        result["evidence"].append("装箱方负责货物堆叠方案设计，承压超标属于装载方案问题")

    return result


def _check_wet_damage(
    inspection_item: Dict[str, Any],
    all_cargos: List[Dict[str, Any]],
    plan_data: Dict[str, Any]
) -> Dict[str, Any]:
    result = {
        "cause": DAMAGE_TYPE_WET,
        "is_applicable": False,
        "confidence": CONFIDENCE_LOW,
        "responsibility": RESPONSIBILITY_CARRIER,
        "evidence": [],
        "detail": {}
    }

    is_door_side = inspection_item.get("is_door_side", False)
    is_bottom = inspection_item.get("is_bottom_layer", False)

    if is_door_side or is_bottom:
        result["is_applicable"] = True

        reasons = []
        if is_door_side:
            reasons.append("箱门侧位置")
        if is_bottom:
            reasons.append("底层位置")

        result["detail"] = {
            "is_door_side": is_door_side,
            "is_bottom_layer": is_bottom,
            "risk_factors": reasons
        }

        if is_door_side and is_bottom:
            result["confidence"] = CONFIDENCE_HIGH
            result["evidence"].append(f"货物位于箱门侧最外层且处于底层，是浸湿风险最高的位置")
        elif is_door_side:
            result["confidence"] = CONFIDENCE_MEDIUM
            result["evidence"].append(f"货物位于箱门侧最外层，箱门密封不严易导致雨水渗入")
        else:
            result["confidence"] = CONFIDENCE_MEDIUM
            result["evidence"].append(f"货物位于底层，可能因箱底积水或冷凝水浸湿")

        result["responsibility"] = RESPONSIBILITY_CARRIER
        result["evidence"].append("运输途中的防雨、防潮由承运方负责")

    return result


def _check_tilt_damage(
    inspection_item: Dict[str, Any],
    all_cargos: List[Dict[str, Any]],
    plan_data: Dict[str, Any]
) -> Dict[str, Any]:
    result = {
        "cause": DAMAGE_TYPE_TILT,
        "is_applicable": False,
        "confidence": CONFIDENCE_LOW,
        "responsibility": RESPONSIBILITY_PACKER,
        "evidence": [],
        "detail": {}
    }

    cog_offset_x = plan_data.get("cog_offset_x_ratio", 0)
    cog_offset_y = plan_data.get("cog_offset_y_ratio", 0)
    max_offset = max(abs(cog_offset_x), abs(cog_offset_y))

    stack_layer = inspection_item.get("stack_layer", 1)

    if max_offset > COG_OFFSET_THRESHOLD or stack_layer > 2:
        result["is_applicable"] = True
        result["detail"] = {
            "cog_offset_x_ratio": cog_offset_x,
            "cog_offset_y_ratio": cog_offset_y,
            "max_offset_ratio": max_offset,
            "stack_layer": stack_layer,
            "offset_threshold": COG_OFFSET_THRESHOLD
        }

        if max_offset > COG_OFFSET_THRESHOLD and stack_layer > 2:
            result["confidence"] = CONFIDENCE_HIGH
            result["evidence"].append(f"整箱重心偏移{max_offset*100:.1f}%（超过10%阈值），且货物位于第{stack_layer}层高风险层位")
        elif max_offset > COG_OFFSET_THRESHOLD:
            result["confidence"] = CONFIDENCE_MEDIUM
            result["evidence"].append(f"整箱重心偏移{max_offset*100:.1f}%，超过10%安全阈值，运输中易发生倾倒")
        elif stack_layer > 3:
            result["confidence"] = CONFIDENCE_MEDIUM
            result["evidence"].append(f"货物位于第{stack_layer}层，堆叠较高，运输颠簸中易倾倒")
        else:
            result["confidence"] = CONFIDENCE_LOW
            result["evidence"].append(f"货物位于第{stack_layer}层，存在一定倾倒风险")

        if max_offset > COG_OFFSET_THRESHOLD:
            result["responsibility"] = RESPONSIBILITY_PACKER
            result["evidence"].append("重心偏移超标属于装箱配载方案问题，装箱方应承担责任")
        else:
            result["responsibility"] = RESPONSIBILITY_CARRIER
            result["evidence"].append("运输过程中的颠簸和急刹车可能导致高层货物倾倒，承运方承担运输责任")

    return result


def _check_temperature_damage(
    inspection_item: Dict[str, Any],
    all_cargos: List[Dict[str, Any]],
    plan_data: Dict[str, Any]
) -> Dict[str, Any]:
    result = {
        "cause": DAMAGE_TYPE_TEMPERATURE,
        "is_applicable": False,
        "confidence": CONFIDENCE_LOW,
        "responsibility": RESPONSIBILITY_PACKER,
        "evidence": [],
        "detail": {}
    }

    temp_class = inspection_item.get("temperature_class", "AMBIENT")
    if temp_class == "AMBIENT":
        return result

    adjacent_cargos = _get_adjacent_cargos(inspection_item, all_cargos, max_distance=200)
    conflicting_cargos = []

    TEMP_ORDER = {"FROZEN": 0, "REFRIGERATED": 1, "AMBIENT": 2}

    for adj in adjacent_cargos:
        adj_temp = adj.get("temperature_class", "AMBIENT")
        if adj_temp != temp_class and adj_temp != "AMBIENT":
            level_diff = abs(TEMP_ORDER.get(temp_class, 1) - TEMP_ORDER.get(adj_temp, 1))
            if level_diff >= 1:
                conflicting_cargos.append({
                    "cargo_id": adj.get("cargo_id"),
                    "cargo_name": adj.get("cargo_name"),
                    "temperature_class": adj_temp,
                    "distance_mm": _calculate_distance(inspection_item, adj)
                })

    if conflicting_cargos:
        result["is_applicable"] = True
        result["detail"] = {
            "cargo_temp_class": temp_class,
            "conflicting_count": len(conflicting_cargos),
            "conflicting_cargos": conflicting_cargos
        }

        if len(conflicting_cargos) >= 2:
            result["confidence"] = CONFIDENCE_HIGH
            result["evidence"].append(f"该{temp_class}级温控货物周围有{len(conflicting_cargos)}件温控等级冲突的货物，温度失控风险极高")
        else:
            result["confidence"] = CONFIDENCE_MEDIUM
            result["evidence"].append(f"该{temp_class}级温控货物与{conflicting_cargos[0]['cargo_name']}({conflicting_cargos[0]['temperature_class']})温控等级冲突")

        result["responsibility"] = RESPONSIBILITY_PACKER
        result["evidence"].append("温控货物混装属于配载方案问题，装箱方应承担责任")

    return result


def _calculate_distance(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    ax1, ay1, az1 = a["x"], a["y"], a["z"]
    ax2 = ax1 + a["length"]
    ay2 = ay1 + a["width"]
    az2 = az1 + a["height"]

    bx1, by1, bz1 = b["x"], b["y"], b["z"]
    bx2 = bx1 + b["length"]
    by2 = by1 + b["width"]
    bz2 = bz1 + b["height"]

    dx = max(0, max(ax1 - bx2, bx1 - ax2))
    dy = max(0, max(ay1 - by2, by1 - ay2))
    dz = max(0, max(az1 - bz2, bz1 - az2))

    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _check_chemical_damage(
    inspection_item: Dict[str, Any],
    all_cargos: List[Dict[str, Any]],
    plan_data: Dict[str, Any],
    hazard_matrix: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    result = {
        "cause": DAMAGE_TYPE_CHEMICAL,
        "is_applicable": False,
        "confidence": CONFIDENCE_LOW,
        "responsibility": RESPONSIBILITY_PACKER,
        "evidence": [],
        "detail": {}
    }

    hazard_class = inspection_item.get("hazard_class")
    if hazard_class is not None:
        return result

    adjacent_cargos = _get_adjacent_cargos(inspection_item, all_cargos, max_distance=500)
    nearby_hazards = []

    for adj in adjacent_cargos:
        adj_hazard = adj.get("hazard_class")
        if adj_hazard is not None:
            distance = _calculate_distance(inspection_item, adj)
            min_required_distance = 1000

            if hazard_matrix:
                for rule in hazard_matrix:
                    if (rule.get("class_a") == hazard_class or rule.get("class_b") == hazard_class):
                        min_required_distance = max(min_required_distance, rule.get("min_distance_mm", 1000))

            if distance < min_required_distance:
                nearby_hazards.append({
                    "cargo_id": adj.get("cargo_id"),
                    "cargo_name": adj.get("cargo_name"),
                    "hazard_class": adj_hazard,
                    "distance_mm": round(distance, 1),
                    "min_required_distance_mm": min_required_distance
                })

    if nearby_hazards:
        result["is_applicable"] = True
        result["detail"] = {
            "nearby_hazard_count": len(nearby_hazards),
            "nearby_hazards": nearby_hazards
        }

        closest = min(nearby_hazards, key=lambda h: h["distance_mm"])
        distance_ratio = closest["distance_mm"] / closest["min_required_distance_mm"] if closest["min_required_distance_mm"] > 0 else 0

        if distance_ratio < 0.3:
            result["confidence"] = CONFIDENCE_HIGH
            result["evidence"].append(f"与危险品{closest['cargo_name']}({closest['hazard_class']}类)距离仅{closest['distance_mm']:.0f}mm，远低于安全距离{closest['min_required_distance_mm']:.0f}mm，化学污染风险极高")
        elif distance_ratio < 0.6:
            result["confidence"] = CONFIDENCE_MEDIUM
            result["evidence"].append(f"与危险品{closest['cargo_name']}({closest['hazard_class']}类)距离{closest['distance_mm']:.0f}mm，低于安全距离{closest['min_required_distance_mm']:.0f}mm")
        else:
            result["confidence"] = CONFIDENCE_LOW
            result["evidence"].append(f"附近有危险品{closest['cargo_name']}({closest['hazard_class']}类)，距离{closest['distance_mm']:.0f}mm，存在一定污染风险")

        result["responsibility"] = RESPONSIBILITY_PACKER
        result["evidence"].append("危险品隔离距离不足属于配载方案问题，装箱方应承担责任")

    return result


def infer_damage_cause(
    inspection_item: Dict[str, Any],
    all_cargos: List[Dict[str, Any]],
    plan_data: Dict[str, Any],
    container_length: float,
    hazard_matrix: List[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    damage_status = inspection_item.get("damage_status", DAMAGE_STATUS_INTACT)
    if damage_status == DAMAGE_STATUS_INTACT:
        return []

    damage_type = inspection_item.get("damage_type")
    if not damage_type:
        return []

    all_cargos_with_id = []
    for idx, c in enumerate(all_cargos):
        c_with_id = dict(c)
        c_with_id["id"] = c.get("id", idx)
        all_cargos_with_id.append(c_with_id)

    item_with_id = dict(inspection_item)
    if "position_x" in item_with_id:
        item_with_id["x"] = item_with_id["position_x"]
        item_with_id["y"] = item_with_id["position_y"]
        item_with_id["z"] = item_with_id["position_z"]

    top_pressure = _calculate_top_pressure(item_with_id, all_cargos_with_id)
    stack_layer = _calculate_stack_layer(item_with_id, all_cargos_with_id)
    is_door_side = _is_door_side(item_with_id, container_length)
    is_bottom = _is_bottom_layer(item_with_id)

    inspection_item_enriched = dict(inspection_item)
    if "position_x" in inspection_item_enriched:
        inspection_item_enriched["x"] = inspection_item_enriched["position_x"]
        inspection_item_enriched["y"] = inspection_item_enriched["position_y"]
        inspection_item_enriched["z"] = inspection_item_enriched["position_z"]
    inspection_item_enriched["top_pressure_weight"] = top_pressure
    inspection_item_enriched["stack_layer"] = stack_layer
    inspection_item_enriched["is_door_side"] = is_door_side
    inspection_item_enriched["is_bottom_layer"] = is_bottom

    all_checks = [
        _check_crush_damage(inspection_item_enriched, all_cargos_with_id, plan_data),
        _check_wet_damage(inspection_item_enriched, all_cargos_with_id, plan_data),
        _check_tilt_damage(inspection_item_enriched, all_cargos_with_id, plan_data),
        _check_temperature_damage(inspection_item_enriched, all_cargos_with_id, plan_data),
        _check_chemical_damage(inspection_item_enriched, all_cargos_with_id, plan_data, hazard_matrix),
    ]

    applicable_checks = [c for c in all_checks if c["is_applicable"]]

    if damage_type:
        matching_checks = [c for c in applicable_checks if c["cause"] == damage_type]
        if matching_checks:
            applicable_checks = matching_checks

    confidence_order = {CONFIDENCE_HIGH: 3, CONFIDENCE_MEDIUM: 2, CONFIDENCE_LOW: 1}
    applicable_checks.sort(key=lambda x: confidence_order.get(x["confidence"], 0), reverse=True)

    results = []
    for check in applicable_checks:
        result = {
            "inferred_cause": check["cause"],
            "confidence_level": check["confidence"],
            "responsibility": check["responsibility"],
            "evidence_list": check["evidence"],
            "inference_detail": check["detail"],
            "explanation": "；".join(check["evidence"])
        }
        results.append(result)

    if not results and damage_type:
        results.append({
            "inferred_cause": damage_type,
            "confidence_level": CONFIDENCE_LOW,
            "responsibility": RESPONSIBILITY_FORCE_MAJEURE,
            "evidence_list": ["无明确致损证据，需进一步调查"],
            "inference_detail": {},
            "explanation": "根据现有信息无法明确判定致损原因，建议进一步调查"
        })

    return results


def calculate_claim_amount(
    declared_value: float,
    damage_status: str
) -> Tuple[float, float]:
    if damage_status == DAMAGE_STATUS_MINOR:
        ratio = CLAIM_RATIO_MINOR
    elif damage_status == DAMAGE_STATUS_SEVERE:
        ratio = CLAIM_RATIO_SEVERE
    elif damage_status == DAMAGE_STATUS_LOST:
        ratio = CLAIM_RATIO_LOST
    else:
        ratio = 0.0

    amount = declared_value * ratio
    return ratio, amount


def determine_primary_responsibility(inferences: List[Dict[str, Any]]) -> str:
    if not inferences:
        return RESPONSIBILITY_FORCE_MAJEURE

    confidence_order = {CONFIDENCE_HIGH: 3, CONFIDENCE_MEDIUM: 2, CONFIDENCE_LOW: 1}

    responsibility_scores = {}
    for inf in inferences:
        resp = inf.get("responsibility", RESPONSIBILITY_FORCE_MAJEURE)
        conf = inf.get("confidence_level", CONFIDENCE_LOW)
        score = confidence_order.get(conf, 1)
        responsibility_scores[resp] = responsibility_scores.get(resp, 0) + score

    if not responsibility_scores:
        return RESPONSIBILITY_FORCE_MAJEURE

    return max(responsibility_scores.items(), key=lambda x: x[1])[0]


def generate_claim_summary(
    inspection_items: List[Dict[str, Any]],
    inferences_by_item: Dict[int, List[Dict[str, Any]]]
) -> Dict[str, Any]:
    total_declared_value = 0.0
    total_claim_amount = 0.0
    minor_damage_amount = 0.0
    severe_damage_amount = 0.0
    lost_amount = 0.0

    responsibility_amounts = {
        RESPONSIBILITY_CARRIER: 0.0,
        RESPONSIBILITY_PACKER: 0.0,
        RESPONSIBILITY_SHIPPER: 0.0,
        RESPONSIBILITY_FORCE_MAJEURE: 0.0,
    }

    claim_items = []

    for item in inspection_items:
        damage_status = item.get("damage_status", DAMAGE_STATUS_INTACT)
        if damage_status == DAMAGE_STATUS_INTACT:
            continue

        declared_value = item.get("declared_value", 0)
        ratio, claim_amount = calculate_claim_amount(declared_value, damage_status)

        total_declared_value += declared_value
        total_claim_amount += claim_amount

        if damage_status == DAMAGE_STATUS_MINOR:
            minor_damage_amount += claim_amount
        elif damage_status == DAMAGE_STATUS_SEVERE:
            severe_damage_amount += claim_amount
        elif damage_status == DAMAGE_STATUS_LOST:
            lost_amount += claim_amount

        item_id = item.get("id")
        inferences = inferences_by_item.get(item_id, [])
        primary_resp = determine_primary_responsibility(inferences)

        responsibility_amounts[primary_resp] = responsibility_amounts.get(primary_resp, 0) + claim_amount

        claim_items.append({
            "inspection_item_id": item_id,
            "cargo_id": item.get("cargo_id"),
            "cargo_name": item.get("cargo_name"),
            "damage_status": damage_status,
            "damage_type": item.get("damage_type"),
            "declared_value": declared_value,
            "claim_ratio": ratio,
            "claim_amount": round(claim_amount, 2),
            "primary_responsibility": primary_resp,
        })

    return {
        "total_declared_value": round(total_declared_value, 2),
        "total_claim_amount": round(total_claim_amount, 2),
        "minor_damage_amount": round(minor_damage_amount, 2),
        "severe_damage_amount": round(severe_damage_amount, 2),
        "lost_amount": round(lost_amount, 2),
        "carrier_responsibility_amount": round(responsibility_amounts[RESPONSIBILITY_CARRIER], 2),
        "packer_responsibility_amount": round(responsibility_amounts[RESPONSIBILITY_PACKER], 2),
        "shipper_responsibility_amount": round(responsibility_amounts[RESPONSIBILITY_SHIPPER], 2),
        "force_majeure_amount": round(responsibility_amounts[RESPONSIBILITY_FORCE_MAJEURE], 2),
        "claim_items": claim_items,
    }


def analyze_damage_and_generate_claim(
    inspection_data: Dict[str, Any],
    plan_data: Dict[str, Any],
    packed_cargos: List[Dict[str, Any]],
    container_length: float,
    hazard_matrix: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    inspection_items = inspection_data.get("inspection_items", [])

    all_cargos_for_analysis = []
    for pc in packed_cargos:
        cargo_dict = {
            "id": pc.get("id", pc.get("packed_cargo_id")),
            "packed_cargo_id": pc.get("id", pc.get("packed_cargo_id")),
            "cargo_id": pc.get("cargo_id"),
            "cargo_name": pc.get("cargo_name"),
            "x": pc.get("x", pc.get("position_x")),
            "y": pc.get("y", pc.get("position_y")),
            "z": pc.get("z", pc.get("position_z")),
            "length": pc.get("length"),
            "width": pc.get("width"),
            "height": pc.get("height"),
            "weight": pc.get("weight"),
            "max_top_load": pc.get("max_top_load", 0),
            "temperature_class": pc.get("temperature_class", "AMBIENT"),
            "hazard_class": pc.get("hazard_class"),
        }
        all_cargos_for_analysis.append(cargo_dict)

    inferences_by_item = {}
    all_inferences = []

    for item in inspection_items:
        item_id = item.get("id", item.get("packed_cargo_id"))
        damage_status = item.get("damage_status", DAMAGE_STATUS_INTACT)

        if damage_status == DAMAGE_STATUS_INTACT:
            continue

        inferences = infer_damage_cause(
            item,
            all_cargos_for_analysis,
            plan_data,
            container_length,
            hazard_matrix
        )

        inferences_by_item[item_id] = inferences

        for inf in inferences:
            inf_record = {
                "inspection_item_id": item_id,
                "cargo_id": item.get("cargo_id"),
                "cargo_name": item.get("cargo_name"),
                **inf
            }
            all_inferences.append(inf_record)

    claim_summary = generate_claim_summary(inspection_items, inferences_by_item)

    return {
        "inferences": all_inferences,
        "claim_summary": claim_summary,
        "inferences_by_item": inferences_by_item,
    }
