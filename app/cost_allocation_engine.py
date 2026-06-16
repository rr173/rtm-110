from sqlalchemy.orm import Session
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from app import models, crud


MM3_TO_CBM = 1e9


def _mm3_to_cbm(length_mm: float, width_mm: float, height_mm: float) -> float:
    return (length_mm * width_mm * height_mm) / MM3_TO_CBM


def _round2(value: float) -> float:
    return round(value, 2)


def _allocate_with_rounding_adjustment(
    total_amount: float,
    items: List[Dict[str, Any]],
    weight_key: str,
    target_key: str,
    amount_key: str = None,
) -> None:
    """
    按权重比例分摊 total_amount 到各 items，自动处理尾差，确保 sum(items[target_key]) == total_amount（精确到分）。

    参数:
        total_amount: 待分摊的总额
        items: 待分摊的货物列表（每项是 dict，会原地修改 target_key 字段）
        weight_key: 权重字段名（如 volume_cbm 用于按体积比例）
        target_key: 结果写入的字段名
        amount_key: 可选，如果已在 items 中预先计算了每个item的精确分摊额，用这个字段；否则按 weight_key 计算

    算法: 最大余数法
        1. 先计算每件货物的精确分摊额，向下取整到分（或四舍五入）
        2. 计算尾差 = 总额 - sum(已取整的各份额)
        3. 按权重从大到小排序，逐件加 0.01，直到尾差用完
    """
    if total_amount <= 0 or not items:
        for item in items:
            item[target_key] = 0.0
        return

    total_weight = sum(float(item.get(weight_key, 0)) for item in items)
    if total_weight <= 0:
        for item in items:
            item[target_key] = 0.0
        return

    precise_amounts = []
    for i, item in enumerate(items):
        if amount_key and amount_key in item:
            precise = float(item[amount_key])
        else:
            w = float(item.get(weight_key, 0))
            precise = total_amount * w / total_weight
        precise_amounts.append(precise)

    floored = [_round2(p) for p in precise_amounts]

    total_floored = sum(floored)
    rounding_diff = _round2(total_amount - total_floored)
    diff_cents = int(round(rounding_diff * 100))

    if diff_cents != 0:
        indexed = []
        for i, item in enumerate(items):
            w = float(item.get(weight_key, 0))
            remainder = precise_amounts[i] - floored[i]
            indexed.append((i, w, remainder, precise_amounts[i]))

        if diff_cents > 0:
            indexed.sort(key=lambda x: (-x[2], -x[1], x[0]))
            for k in range(diff_cents):
                idx = indexed[k % len(indexed)][0]
                floored[idx] = _round2(floored[idx] + 0.01)
        else:
            indexed.sort(key=lambda x: (x[2], x[1], x[0]))
            for k in range(abs(diff_cents)):
                idx = indexed[k % len(indexed)][0]
                floored[idx] = _round2(floored[idx] - 0.01)

    for i, item in enumerate(items):
        item[target_key] = floored[i]


def _get_hazard_class_for_cargo(db: Session, packed_cargo: models.PackedCargo) -> Optional[int]:
    if hasattr(packed_cargo, 'hazard_class') and packed_cargo.hazard_class:
        return packed_cargo.hazard_class
    cargo = crud.get_cargo(db, cargo_id=packed_cargo.cargo_id)
    if cargo and cargo.hazard_class:
        return cargo.hazard_class
    return None


def _get_temperature_class(packed_cargo: models.PackedCargo) -> str:
    tc = getattr(packed_cargo, 'temperature_class', None) or 'AMBIENT'
    if hasattr(tc, 'value'):
        tc = tc.value
    return str(tc).upper()


def _group_packed_cargos_by_box(
    db: Session,
    plan: models.PackingPlan,
    packed_cargos: List[models.PackedCargo]
) -> List[Dict[str, Any]]:
    boxes = [{
        "box_index": 1,
        "plan_id": plan.id,
        "container_id": plan.container_id,
        "container_name": plan.container_name,
        "packed_cargos": packed_cargos,
    }]
    return boxes


def _analyze_box_cargos(
    db: Session,
    packed_cargos: List[models.PackedCargo]
) -> Dict[str, Any]:
    total_weight = 0.0
    total_volume_cbm = 0.0
    hazard_classes = set()
    temp_classes = set()
    cargos_meta = []

    TEMP_PRIORITY = {"FROZEN": 3, "REFRIGERATED": 2, "AMBIENT": 1}

    for pc in packed_cargos:
        vol = _mm3_to_cbm(pc.length, pc.width, pc.height)
        wt = float(pc.weight or 0)
        hc = _get_hazard_class_for_cargo(db, pc)
        tc = _get_temperature_class(pc)

        total_weight += wt
        total_volume_cbm += vol
        if hc:
            hazard_classes.add(hc)
        temp_classes.add(tc)

        cargos_meta.append({
            "packed_cargo_id": pc.id,
            "cargo_id": pc.cargo_id,
            "cargo_name": pc.cargo_name,
            "volume_cbm": _round2(vol),
            "weight_kg": wt,
            "hazard_class": hc,
            "temperature_class": tc,
        })

    sorted_temps = sorted(
        [t for t in temp_classes if t in TEMP_PRIORITY],
        key=lambda t: TEMP_PRIORITY[t],
        reverse=True
    )
    temperature_mode = sorted_temps[0] if sorted_temps else "AMBIENT"

    highest_hazard = min(hazard_classes) if hazard_classes else None

    return {
        "total_weight_kg": _round2(total_weight),
        "total_volume_cbm": _round2(total_volume_cbm),
        "cargo_count": len(packed_cargos),
        "hazard_classes": sorted(list(hazard_classes)),
        "highest_hazard_class": highest_hazard,
        "has_hazard": len(hazard_classes) > 0,
        "temperature_classes": list(temp_classes),
        "temperature_mode": temperature_mode,
        "cargos_meta": cargos_meta,
    }


def _calculate_overweight_surcharge(
    rate_config: models.ContainerRateConfig,
    actual_weight_kg: float,
    container_max_weight: float,
) -> Tuple[float, Dict[str, Any]]:
    threshold = float(rate_config.overweight_threshold_kg or 0)
    if threshold <= 0:
        threshold = float(container_max_weight or 0)
    if threshold <= 0 or actual_weight_kg <= threshold:
        return 0.0, {
            "threshold_kg": _round2(threshold),
            "actual_weight_kg": _round2(actual_weight_kg),
            "overweight_kg": 0.0,
            "surcharge_type": "none",
            "amount": 0.0,
        }

    overweight_kg = actual_weight_kg - threshold
    flat_amt = float(rate_config.overweight_surcharge_flat or 0)
    per_kg_amt = float(rate_config.overweight_surcharge_per_kg or 0)

    total = 0.0
    types = []
    if flat_amt > 0:
        total += flat_amt
        types.append("flat")
    if per_kg_amt > 0:
        per_kg_total = overweight_kg * per_kg_amt
        total += per_kg_total
        types.append("per_kg")

    return _round2(total), {
        "threshold_kg": _round2(threshold),
        "actual_weight_kg": _round2(actual_weight_kg),
        "overweight_kg": _round2(overweight_kg),
        "surcharge_type": "+".join(types) if types else "none",
        "flat_amount": _round2(flat_amt),
        "per_kg_rate": _round2(per_kg_amt),
        "per_kg_amount": _round2(overweight_kg * per_kg_amt),
        "amount": _round2(total),
    }


def _calculate_temperature_surcharge(
    rate_config: models.ContainerRateConfig,
    temperature_mode: str,
    temp_classes_present: set,
) -> Tuple[float, float, Dict[str, Any]]:
    reefer_applied = False
    frozen_applied = False
    reefer_amount = 0.0
    frozen_amount = 0.0

    if temperature_mode in ("REFRIGERATED", "FROZEN"):
        reefer_applied = True
        reefer_amount = float(rate_config.reefer_surcharge or 0)

    if temperature_mode == "FROZEN":
        frozen_applied = True
        frozen_amount = float(rate_config.frozen_surcharge or 0)

    details = {
        "mode": temperature_mode,
        "temp_classes_present": sorted(list(temp_classes_present)),
        "reefer_applied": reefer_applied,
        "reefer_amount": _round2(reefer_amount),
        "frozen_applied": frozen_applied,
        "frozen_amount": _round2(frozen_amount),
        "total_reefer_related": _round2(reefer_amount + frozen_amount),
    }
    return _round2(reefer_amount), _round2(frozen_amount), details


def _calculate_hazard_surcharge(
    db: Session,
    rate_config: models.ContainerRateConfig,
    hazard_classes_present: List[int],
    cargos_meta: List[Dict[str, Any]],
) -> Tuple[float, Dict[str, Any], Dict[int, float]]:
    by_class_config = rate_config.hazard_surcharge_by_class or {}
    per_kg_rate = float(rate_config.hazard_surcharge_per_kg or 0)

    by_class_amount = 0.0
    by_class_breakdown = {}
    for hc in hazard_classes_present:
        amt = float(by_class_config.get(str(hc), 0))
        by_class_amount += amt
        by_class_breakdown[str(hc)] = _round2(amt)

    per_kg_by_class_total = {}
    per_kg_amount = 0.0
    for cm in cargos_meta:
        hc = cm.get("hazard_class")
        if hc:
            wt = float(cm.get("weight_kg", 0))
            amt = wt * per_kg_rate
            per_kg_amount += amt
            per_kg_by_class_total.setdefault(hc, 0.0)
            per_kg_by_class_total[hc] += amt

    per_kg_breakdown = {
        str(k): _round2(v) for k, v in per_kg_by_class_total.items()
    }

    total = _round2(by_class_amount + per_kg_amount)
    details = {
        "hazard_classes": sorted(hazard_classes_present),
        "by_class_breakdown": by_class_breakdown,
        "by_class_total": _round2(by_class_amount),
        "per_kg_rate": _round2(per_kg_rate),
        "per_kg_breakdown": per_kg_breakdown,
        "per_kg_total": _round2(per_kg_amount),
        "total": total,
    }

    per_cargo_dedicated = {}
    for cm in cargos_meta:
        hc = cm.get("hazard_class")
        if hc:
            class_amt = float(by_class_config.get(str(hc), 0))
            hazard_count_in_class = sum(
                1 for x in cargos_meta if x.get("hazard_class") == hc
            )
            per_cargo_class_share = class_amt / hazard_count_in_class if hazard_count_in_class > 0 else 0
            wt = float(cm.get("weight_kg", 0))
            per_cargo_per_kg = wt * per_kg_rate
            per_cargo_dedicated[cm["packed_cargo_id"]] = _round2(
                per_cargo_class_share + per_cargo_per_kg
            )

    return total, details, per_cargo_dedicated


def _calculate_per_cargo_temp_dedicated(
    cargos_meta: List[Dict[str, Any]],
    temperature_mode: str,
    reefer_amount: float,
    frozen_amount: float,
) -> Dict[int, float]:
    dedicated = {}

    if temperature_mode not in ("REFRIGERATED", "FROZEN"):
        return dedicated

    reefer_cargo_ids = [
        cm["packed_cargo_id"] for cm in cargos_meta
        if cm.get("temperature_class") in ("REFRIGERATED", "FROZEN")
    ]
    frozen_cargo_ids = [
        cm["packed_cargo_id"] for cm in cargos_meta
        if cm.get("temperature_class") == "FROZEN"
    ]

    reefer_share = reefer_amount / len(reefer_cargo_ids) if reefer_cargo_ids else 0
    frozen_share = frozen_amount / len(frozen_cargo_ids) if frozen_cargo_ids else 0

    for cm in cargos_meta:
        pid = cm["packed_cargo_id"]
        tc = cm.get("temperature_class")
        amt = 0.0
        if tc in ("REFRIGERATED", "FROZEN") and reefer_share > 0:
            amt += reefer_share
        if tc == "FROZEN" and frozen_share > 0:
            amt += frozen_share
        if amt > 0:
            dedicated[pid] = _round2(amt)

    return dedicated


def _allocate_shared_costs(
    shared_total: float,
    cargos_meta: List[Dict[str, Any]],
    total_volume_cbm: float,
) -> Dict[int, Dict[str, float]]:
    allocations = {}

    if shared_total <= 0 or total_volume_cbm <= 0:
        for cm in cargos_meta:
            allocations[cm["packed_cargo_id"]] = {
                "base_freight": 0.0,
                "overweight": 0.0,
                "volume_ratio": 0.0,
                "shared_portion": 0.0,
            }
        return allocations

    for cm in cargos_meta:
        vol = float(cm.get("volume_cbm", 0))
        ratio = vol / total_volume_cbm if total_volume_cbm > 0 else 0
        allocations[cm["packed_cargo_id"]] = {
            "volume_ratio": _round2(ratio),
            "shared_portion_total": _round2(shared_total * ratio),
        }

    return allocations


def calculate_and_allocate_for_plan(
    db: Session,
    plan_id: int,
    scheme_id: int,
    calculated_by: str = None,
    remarks: str = None,
    recalculate: bool = False,
) -> Dict[str, Any]:
    plan = crud.get_packing_plan(db, plan_id=plan_id)
    if not plan:
        return {"error": f"配载方案 {plan_id} 不存在"}

    scheme = crud.get_rate_scheme(db, scheme_id=scheme_id)
    if not scheme:
        return {"error": f"费率方案 {scheme_id} 不存在"}

    if not plan.content_hash:
        plan.content_hash = crud.compute_plan_content_hash(db, plan.id)
        if not plan.version:
            plan.version = 1
        db.commit()
        db.refresh(plan)

    if not recalculate:
        existing = crud.find_existing_calculation(
            db,
            plan_id=plan.id,
            scheme_id=scheme.id,
            plan_version=plan.version,
            plan_content_hash=plan.content_hash,
        )
        if existing:
            return {
                "reused": True,
                "calculation_id": existing.id,
                "calculation_no": existing.calculation_no,
                "message": "已存在相同版本与内容的费用计算结果,直接复用",
            }

    rate_config = crud.get_container_rate_config(db, scheme.id, plan.container_id)
    if not rate_config:
        container = crud.get_container(db, container_id=plan.container_id)
        container_name = container.name if container else f"Container-{plan.container_id}"
        return {
            "error": f"费率方案 '{scheme.scheme_name}' 未配置箱型 '{container_name}' 的费率"
        }

    container = crud.get_container(db, container_id=plan.container_id)
    container_max_weight = float(container.max_weight) if container else 0.0

    packed_cargos = crud.get_packed_cargos(db, plan_id=plan.id)
    if not packed_cargos:
        return {"error": f"配载方案 {plan.plan_no} 没有已装载货物,无法计算费用"}

    boxes = _group_packed_cargos_by_box(db, plan, packed_cargos)

    box_details_data = []
    cargo_allocations_data = []

    total_base_freight = 0.0
    total_overweight = 0.0
    total_reefer = 0.0
    total_frozen = 0.0
    total_hazard = 0.0

    for box in boxes:
        box_index = box["box_index"]
        pc_list = box["packed_cargos"]
        analysis = _analyze_box_cargos(db, pc_list)

        base_freight = float(rate_config.base_freight or 0)
        overweight_amount, overweight_details = _calculate_overweight_surcharge(
            rate_config,
            analysis["total_weight_kg"],
            container_max_weight,
        )
        reefer_amount, frozen_amount, temp_details = _calculate_temperature_surcharge(
            rate_config,
            analysis["temperature_mode"],
            set(analysis["temperature_classes"]),
        )
        hazard_amount, hazard_details, per_cargo_hazard_dedicated = _calculate_hazard_surcharge(
            db,
            rate_config,
            analysis["hazard_classes"],
            analysis["cargos_meta"],
        )

        per_cargo_temp_dedicated = _calculate_per_cargo_temp_dedicated(
            analysis["cargos_meta"],
            analysis["temperature_mode"],
            reefer_amount,
            frozen_amount,
        )

        subtotal_shared = _round2(base_freight + overweight_amount)
        dedicated_temp_total = _round2(sum(per_cargo_temp_dedicated.values()))
        dedicated_hazard_total = _round2(sum(per_cargo_hazard_dedicated.values()))
        subtotal_dedicated = _round2(reefer_amount + frozen_amount + hazard_amount)
        subtotal_all = _round2(subtotal_shared + subtotal_dedicated)

        box_details_data.append({
            "plan_id": plan.id,
            "container_id": plan.container_id,
            "container_name": plan.container_name,
            "box_index": box_index,
            "actual_weight_kg": analysis["total_weight_kg"],
            "total_cargo_volume_cbm": analysis["total_volume_cbm"],
            "cargo_count": analysis["cargo_count"],
            "has_hazard": analysis["has_hazard"],
            "highest_hazard_class": analysis["highest_hazard_class"],
            "temperature_mode": analysis["temperature_mode"],
            "base_freight": _round2(base_freight),
            "overweight_surcharge": overweight_amount,
            "overweight_details": overweight_details,
            "reefer_surcharge": _round2(reefer_amount),
            "frozen_surcharge": _round2(frozen_amount),
            "hazard_surcharge": hazard_amount,
            "hazard_details": hazard_details,
            "temperature_details": temp_details,
            "subtotal_shared": subtotal_shared,
            "subtotal_dedicated": subtotal_dedicated,
            "subtotal_all": subtotal_all,
        })

        total_base_freight += base_freight
        total_overweight += overweight_amount
        total_reefer += reefer_amount
        total_frozen += frozen_amount
        total_hazard += hazard_amount

        alloc_items = []
        total_volume = analysis["total_volume_cbm"]
        for cm in analysis["cargos_meta"]:
            pid = cm["packed_cargo_id"]
            vol = float(cm.get("volume_cbm", 0))
            ratio = vol / total_volume if total_volume > 0 else 0
            item = {
                "packed_cargo_id": pid,
                "cargo_id": cm["cargo_id"],
                "cargo_name": cm["cargo_name"],
                "volume_cbm": vol,
                "volume_ratio": _round2(ratio),
                "weight_kg": cm.get("weight_kg", 0),
                "hazard_class": cm.get("hazard_class"),
                "temperature_class": cm.get("temperature_class"),
                "precise_base_freight": base_freight * ratio if base_freight > 0 else 0.0,
                "precise_overweight": overweight_amount * ratio if overweight_amount > 0 else 0.0,
                "precise_reefer": 0.0,
                "precise_frozen": 0.0,
                "precise_hazard": 0.0,
                "allocated_base_freight": 0.0,
                "allocated_overweight_surcharge": 0.0,
                "allocated_reefer_surcharge": 0.0,
                "allocated_frozen_surcharge": 0.0,
                "allocated_hazard_surcharge": 0.0,
            }
            alloc_items.append(item)

        _allocate_with_rounding_adjustment(
            _round2(base_freight),
            alloc_items,
            weight_key="volume_cbm",
            target_key="allocated_base_freight",
            amount_key="precise_base_freight",
        )

        _allocate_with_rounding_adjustment(
            _round2(overweight_amount),
            alloc_items,
            weight_key="volume_cbm",
            target_key="allocated_overweight_surcharge",
            amount_key="precise_overweight",
        )

        reefer_cargos = [it for it in alloc_items
                         if it["temperature_class"] in ("REFRIGERATED", "FROZEN")]
        if reefer_cargos and reefer_amount > 0:
            for it in reefer_cargos:
                it["precise_reefer"] = reefer_amount / len(reefer_cargos)
            _allocate_with_rounding_adjustment(
                _round2(reefer_amount),
                reefer_cargos,
                weight_key="volume_cbm",
                target_key="allocated_reefer_surcharge",
                amount_key="precise_reefer",
            )

        frozen_cargos = [it for it in alloc_items
                         if it["temperature_class"] == "FROZEN"]
        if frozen_cargos and frozen_amount > 0:
            for it in frozen_cargos:
                it["precise_frozen"] = frozen_amount / len(frozen_cargos)
            _allocate_with_rounding_adjustment(
                _round2(frozen_amount),
                frozen_cargos,
                weight_key="volume_cbm",
                target_key="allocated_frozen_surcharge",
                amount_key="precise_frozen",
            )

        hazard_classes = analysis["hazard_classes"]
        for hc in hazard_classes:
            hc_cargos = [it for it in alloc_items if it["hazard_class"] == hc]
            if not hc_cargos:
                continue
            class_amt = float(per_cargo_hazard_dedicated.get(it["packed_cargo_id"], 0.0)
                              for it in hc_cargos).__iter__().__next__() if hc_cargos else 0.0
            total_hazard_for_class = _round2(sum(
                float(per_cargo_hazard_dedicated.get(it["packed_cargo_id"], 0.0))
                for it in hc_cargos
            ))
            if total_hazard_for_class > 0:
                for it in hc_cargos:
                    it["precise_hazard"] = float(per_cargo_hazard_dedicated.get(it["packed_cargo_id"], 0.0))
                _allocate_with_rounding_adjustment(
                    total_hazard_for_class,
                    hc_cargos,
                    weight_key="volume_cbm",
                    target_key="allocated_hazard_surcharge",
                    amount_key="precise_hazard",
                )

        for item in alloc_items:
            shared_portion = _round2(item["allocated_base_freight"] + item["allocated_overweight_surcharge"])
            dedicated_portion = _round2(
                item["allocated_reefer_surcharge"]
                + item["allocated_frozen_surcharge"]
                + item["allocated_hazard_surcharge"]
            )
            total_alloc = _round2(shared_portion + dedicated_portion)

            cargo_allocations_data.append({
                "plan_id": plan.id,
                "packed_cargo_id": item["packed_cargo_id"],
                "cargo_id": item["cargo_id"],
                "cargo_name": item["cargo_name"],
                "box_index": box_index,
                "volume_cbm": item["volume_cbm"],
                "volume_ratio": item["volume_ratio"],
                "weight_kg": item["weight_kg"],
                "hazard_class": item["hazard_class"],
                "temperature_class": item["temperature_class"],
                "allocated_base_freight": item["allocated_base_freight"],
                "allocated_overweight_surcharge": item["allocated_overweight_surcharge"],
                "allocated_reefer_surcharge": item["allocated_reefer_surcharge"],
                "allocated_frozen_surcharge": item["allocated_frozen_surcharge"],
                "allocated_hazard_surcharge": item["allocated_hazard_surcharge"],
                "shared_portion": shared_portion,
                "dedicated_portion": dedicated_portion,
                "total_allocated": total_alloc,
                "allocation_breakdown": {
                    "shared_breakdown": {
                        "base_freight": item["allocated_base_freight"],
                        "overweight_surcharge": item["allocated_overweight_surcharge"],
                        "total_shared": shared_portion,
                    },
                    "dedicated_breakdown": {
                        "reefer_surcharge": item["allocated_reefer_surcharge"],
                        "frozen_surcharge": item["allocated_frozen_surcharge"],
                        "hazard_surcharge": item["allocated_hazard_surcharge"],
                        "total_dedicated": dedicated_portion,
                    },
                    "verification": {
                        "sum_shared_plus_dedicated": total_alloc,
                        "sum_component_wise": _round2(
                            item["allocated_base_freight"]
                            + item["allocated_overweight_surcharge"]
                            + item["allocated_reefer_surcharge"]
                            + item["allocated_frozen_surcharge"]
                            + item["allocated_hazard_surcharge"]
                        ),
                    },
                },
            })

    total_cost = _round2(
        total_base_freight + total_overweight
        + total_reefer + total_frozen
        + total_hazard
    )

    calc_data = {
        "scheme_id": scheme.id,
        "plan_id": plan.id,
        "plan_no": plan.plan_no,
        "plan_version": plan.version or 1,
        "plan_content_hash": plan.content_hash,
        "total_base_freight": _round2(total_base_freight),
        "total_overweight_surcharge": _round2(total_overweight),
        "total_reefer_surcharge": _round2(total_reefer),
        "total_frozen_surcharge": _round2(total_frozen),
        "total_hazard_surcharge": _round2(total_hazard),
        "total_cost": total_cost,
        "currency": scheme.currency or "CNY",
        "calculation_status": "completed",
        "remarks": remarks,
        "calculated_by": calculated_by,
    }

    try:
        db_calc = crud.create_cost_calculation(
            db,
            calc_data,
            box_details_data,
            cargo_allocations_data,
        )
    except Exception as e:
        return {"error": f"保存费用计算结果失败: {str(e)}"}

    return {
        "reused": False,
        "calculation_id": db_calc.id,
        "calculation_no": db_calc.calculation_no,
        "plan_id": plan.id,
        "plan_no": plan.plan_no,
        "scheme_id": scheme.id,
        "scheme_name": scheme.scheme_name,
        "total_cost": total_cost,
        "currency": scheme.currency,
        "box_count": len(box_details_data),
        "cargo_count": len(cargo_allocations_data),
    }


def get_calculation_detail(
    db: Session,
    calculation_id: int = None,
    calculation_no: str = None,
) -> Dict[str, Any]:
    calc = crud.get_cost_calculation(db, calculation_id=calculation_id, calculation_no=calculation_no)
    if not calc:
        return {"error": "费用计算记录不存在"}

    scheme = crud.get_rate_scheme(db, scheme_id=calc.scheme_id)
    plan = crud.get_packing_plan(db, plan_id=calc.plan_id)

    box_details = crud.get_box_details(db, calc.id)
    cargo_allocations = crud.get_cargo_allocations(db, calc.id)

    box_list = []
    for bd in box_details:
        box_list.append({
            "id": bd.id,
            "calculation_id": bd.calculation_id,
            "box_index": bd.box_index,
            "container_id": bd.container_id,
            "container_name": bd.container_name,
            "actual_weight_kg": bd.actual_weight_kg,
            "total_cargo_volume_cbm": bd.total_cargo_volume_cbm,
            "cargo_count": bd.cargo_count,
            "has_hazard": bd.has_hazard,
            "highest_hazard_class": bd.highest_hazard_class,
            "temperature_mode": bd.temperature_mode,
            "base_freight": bd.base_freight,
            "overweight_surcharge": bd.overweight_surcharge,
            "overweight_details": bd.overweight_details or {},
            "reefer_surcharge": bd.reefer_surcharge,
            "frozen_surcharge": bd.frozen_surcharge,
            "hazard_surcharge": bd.hazard_surcharge,
            "hazard_details": bd.hazard_details or {},
            "temperature_details": bd.temperature_details or {},
            "subtotal_shared": bd.subtotal_shared,
            "subtotal_dedicated": bd.subtotal_dedicated,
            "subtotal_all": bd.subtotal_all,
            "created_at": bd.created_at.isoformat() if bd.created_at else "",
        })

    alloc_list = []
    for ca in cargo_allocations:
        alloc_list.append({
            "id": ca.id,
            "calculation_id": ca.calculation_id,
            "box_detail_id": ca.box_detail_id,
            "packed_cargo_id": ca.packed_cargo_id,
            "cargo_id": ca.cargo_id,
            "cargo_name": ca.cargo_name,
            "box_index": ca.box_index,
            "volume_cbm": ca.volume_cbm,
            "volume_ratio": ca.volume_ratio,
            "weight_kg": ca.weight_kg,
            "hazard_class": ca.hazard_class,
            "temperature_class": ca.temperature_class,
            "allocated_base_freight": ca.allocated_base_freight,
            "allocated_overweight_surcharge": ca.allocated_overweight_surcharge,
            "allocated_reefer_surcharge": ca.allocated_reefer_surcharge,
            "allocated_frozen_surcharge": ca.allocated_frozen_surcharge,
            "allocated_hazard_surcharge": ca.allocated_hazard_surcharge,
            "total_allocated": ca.total_allocated,
            "shared_portion": ca.shared_portion,
            "dedicated_portion": ca.dedicated_portion,
            "allocation_breakdown": ca.allocation_breakdown or {},
            "created_at": ca.created_at.isoformat() if ca.created_at else "",
        })

    return {
        "id": calc.id,
        "calculation_no": calc.calculation_no,
        "scheme_id": calc.scheme_id,
        "scheme_code": scheme.scheme_code if scheme else "",
        "scheme_name": scheme.scheme_name if scheme else "",
        "carrier": scheme.carrier if scheme else "",
        "plan_id": calc.plan_id,
        "plan_no": calc.plan_no,
        "plan_version": calc.plan_version,
        "plan_content_hash": calc.plan_content_hash,
        "currency": calc.currency,
        "total_base_freight": calc.total_base_freight,
        "total_overweight_surcharge": calc.total_overweight_surcharge,
        "total_reefer_surcharge": calc.total_reefer_surcharge,
        "total_frozen_surcharge": calc.total_frozen_surcharge,
        "total_hazard_surcharge": calc.total_hazard_surcharge,
        "total_cost": calc.total_cost,
        "calculation_status": calc.calculation_status,
        "error_message": calc.error_message,
        "remarks": calc.remarks,
        "calculated_by": calc.calculated_by,
        "created_at": calc.created_at.isoformat() if calc.created_at else "",
        "box_count": len(box_list),
        "total_cargo_count": len(alloc_list),
        "box_details": box_list,
        "cargo_allocations": alloc_list,
    }


def compare_rate_schemes_for_plan(
    db: Session,
    plan_id: int,
    scheme_ids: List[int],
) -> Dict[str, Any]:
    plan = crud.get_packing_plan(db, plan_id=plan_id)
    if not plan:
        return {"error": "配载方案不存在"}

    if len(scheme_ids) < 2:
        return {"error": "至少需要2个费率方案进行对比"}

    calc_results = []
    for sid in scheme_ids:
        scheme = crud.get_rate_scheme(db, scheme_id=sid)
        if not scheme:
            return {"error": f"费率方案 {sid} 不存在"}

        result = calculate_and_allocate_for_plan(
            db, plan.id, sid,
            calculated_by="rate-compare",
            remarks=f"费率对比: {scheme.scheme_name}",
            recalculate=False,
        )
        if "error" in result:
            return {"error": f"方案 {scheme.scheme_name} 计算失败: {result['error']}"}

        calc_id = result.get("calculation_id")
        if not calc_id:
            return {"error": f"未获取到方案 {scheme.scheme_name} 的计算结果ID"}

        detail = get_calculation_detail(db, calculation_id=calc_id)
        if "error" in detail:
            return {"error": f"获取方案 {scheme.scheme_name} 详情失败: {detail['error']}"}

        calc_results.append({
            "scheme": scheme,
            "detail": detail,
        })

    base = calc_results[0]
    base_detail = base["detail"]
    base_scheme = base["scheme"]

    compared_summaries = []
    total_diff_list = []
    all_cargo_data = {}

    for item in calc_results:
        scheme = item["scheme"]
        d = item["detail"]
        summary = {
            "id": d["id"],
            "scheme_id": scheme.id,
            "scheme_code": scheme.scheme_code,
            "scheme_name": scheme.scheme_name,
            "carrier": scheme.carrier,
            "calculation_id": d["id"],
            "calculation_no": d["calculation_no"],
            "plan_id": d["plan_id"],
            "plan_no": d["plan_no"],
            "plan_version": d["plan_version"],
            "calculation_status": d.get("calculation_status", "completed"),
            "currency": d["currency"],
            "total_base_freight": d["total_base_freight"],
            "total_overweight_surcharge": d["total_overweight_surcharge"],
            "total_reefer_surcharge": d["total_reefer_surcharge"],
            "total_frozen_surcharge": d["total_frozen_surcharge"],
            "total_hazard_surcharge": d["total_hazard_surcharge"],
            "total_cost": d["total_cost"],
            "box_count": d["box_count"],
            "total_cargo_count": d["total_cargo_count"],
            "created_at": d["created_at"],
        }

        diff_amt = d["total_cost"] - base_detail["total_cost"]
        diff_ratio = (diff_amt / base_detail["total_cost"]) if base_detail["total_cost"] > 0 else 0

        total_diff_list.append({
            **summary,
            "diff_amount_vs_base": _round2(diff_amt),
            "diff_ratio_vs_base": _round2(diff_ratio),
            "component_diffs": {
                "base_freight_diff": _round2(d["total_base_freight"] - base_detail["total_base_freight"]),
                "overweight_diff": _round2(d["total_overweight_surcharge"] - base_detail["total_overweight_surcharge"]),
                "reefer_diff": _round2(d["total_reefer_surcharge"] - base_detail["total_reefer_surcharge"]),
                "frozen_diff": _round2(d["total_frozen_surcharge"] - base_detail["total_frozen_surcharge"]),
                "hazard_diff": _round2(d["total_hazard_surcharge"] - base_detail["total_hazard_surcharge"]),
            },
        })

        for ca in d.get("cargo_allocations", []):
            key = (ca["packed_cargo_id"], ca["cargo_id"])
            all_cargo_data.setdefault(key, {
                "packed_cargo_id": ca["packed_cargo_id"],
                "cargo_id": ca["cargo_id"],
                "cargo_name": ca["cargo_name"],
                "box_index": ca["box_index"],
                "base_cost": 0.0,
                "compare_costs": {},
                "base_breakdown": {},
            })
            if scheme.id == base_scheme.id:
                all_cargo_data[key]["base_cost"] = ca["total_allocated"]
                all_cargo_data[key]["base_breakdown"] = {
                    "base_freight": ca["allocated_base_freight"],
                    "overweight": ca["allocated_overweight_surcharge"],
                    "reefer": ca["allocated_reefer_surcharge"],
                    "frozen": ca["allocated_frozen_surcharge"],
                    "hazard": ca["allocated_hazard_surcharge"],
                }
            else:
                all_cargo_data[key]["compare_costs"][scheme.id] = ca["total_allocated"]

        if scheme.id != base_scheme.id:
            compared_summaries.append(summary)

    per_cargo_diffs = []
    for key, info in all_cargo_data.items():
        base_cost = info["base_cost"]
        for sid, comp_cost in info["compare_costs"].items():
            diff = _round2(comp_cost - base_cost)
            ratio = _round2(diff / base_cost) if base_cost > 0 else 0.0
            scheme = next((s for s in scheme_ids if s == sid), None)
            per_cargo_diffs.append({
                "packed_cargo_id": info["packed_cargo_id"],
                "cargo_id": info["cargo_id"],
                "cargo_name": info["cargo_name"],
                "box_index": info["box_index"],
                "compare_scheme_id": sid,
                "base_cost": _round2(base_cost),
                "compare_cost": _round2(comp_cost),
                "diff_amount": diff,
                "diff_ratio": ratio,
                "breakdown": {
                    "base_breakdown": info["base_breakdown"],
                },
            })

    lowest_idx = 0
    lowest_cost = total_diff_list[0]["total_cost"]
    for i, td in enumerate(total_diff_list):
        if td["total_cost"] < lowest_cost:
            lowest_cost = td["total_cost"]
            lowest_idx = i

    if lowest_idx == 0:
        recommendation = (
            f"基准费率方案 '{base_scheme.scheme_name}' 总费用最低 "
            f"({base_detail['currency']} {_round2(lowest_cost)}), 建议保持使用基准方案"
        )
    else:
        td = total_diff_list[lowest_idx]
        save_amt = abs(td["diff_amount_vs_base"])
        recommendation = (
            f"推荐切换到 '{td['scheme_name']}' (方案编号: {td['scheme_code']}), "
            f"相比基准方案可节省 {base_detail['currency']} {save_amt} "
            f"(降幅 {_round2(abs(td['diff_ratio_vs_base']) * 100)}%)"
        )

    import uuid
    comparison_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"

    base_summary_dict = None
    for td in total_diff_list:
        if td["scheme_id"] == base_scheme.id:
            base_summary_dict = td
            break

    return {
        "comparison_id": comparison_id,
        "plan_id": plan.id,
        "plan_no": plan.plan_no,
        "plan_version": plan.version or 1,
        "currency": base_detail["currency"],
        "base_scheme": base_summary_dict,
        "compared_schemes": compared_summaries,
        "total_cost_diff_summary": total_diff_list,
        "per_cargo_diffs": per_cargo_diffs,
        "recommendation": recommendation,
    }
