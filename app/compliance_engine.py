from sqlalchemy.orm import Session
from typing import List, Dict, Tuple, Any
import math
from datetime import datetime

from app import models, crud


def _cargo_centroid(pc) -> Tuple[float, float, float]:
    return (
        pc.x + pc.length / 2.0,
        pc.y + pc.width / 2.0,
        pc.z + pc.height / 2.0,
    )


def _min_distance_between_boxes(box_a, box_b) -> float:
    ax1, ay1, az1 = box_a.x, box_a.y, box_a.z
    ax2, ay2, az2 = box_a.x + box_a.length, box_a.y + box_a.width, box_a.z + box_a.height
    bx1, by1, bz1 = box_b.x, box_b.y, box_b.z
    bx2, by2, bz2 = box_b.x + box_b.length, box_b.y + box_b.width, box_b.z + box_b.height

    dx = max(0.0, max(ax1 - bx2, bx1 - ax2))
    dy = max(0.0, max(ay1 - by2, by1 - ay2))
    dz = max(0.0, max(az1 - bz2, bz1 - az2))

    return math.sqrt(dx * dx + dy * dy + dz * dz)


def run_hazard_segregation_check(db: Session, plan_id: int) -> Tuple[bool, List[Dict[str, Any]]]:
    plan = crud.get_packing_plan(db, plan_id=plan_id)
    if not plan:
        return False, [{"error": "方案不存在"}]

    packed_cargos = crud.get_packed_cargos(db, plan_id=plan_id)
    hazard_cargos = []
    for pc in packed_cargos:
        cargo = crud.get_cargo(db, cargo_id=pc.cargo_id)
        hz_class = cargo.hazard_class if cargo else None
        if hz_class is not None:
            hazard_cargos.append((pc, hz_class, cargo))

    violations = []
    n = len(hazard_cargos)
    for i in range(n):
        for j in range(i + 1, n):
            pc_a, hz_a, cargo_a = hazard_cargos[i]
            pc_b, hz_b, cargo_b = hazard_cargos[j]
            if hz_a == hz_b:
                matrix_entry = crud.get_hazard_matrix(db, hz_a, hz_b)
                if not matrix_entry or matrix_entry.min_distance_mm <= 0:
                    continue
            matrix_entry = crud.get_hazard_matrix(db, hz_a, hz_b)
            if not matrix_entry:
                continue
            required_dist = matrix_entry.min_distance_mm
            actual_dist = _min_distance_between_boxes(pc_a, pc_b)
            if actual_dist < required_dist:
                violations.append({
                    "cargo_a_id": pc_a.cargo_id,
                    "cargo_a_name": pc_a.cargo_name,
                    "hazard_class_a": hz_a,
                    "cargo_b_id": pc_b.cargo_id,
                    "cargo_b_name": pc_b.cargo_name,
                    "hazard_class_b": hz_b,
                    "actual_distance_mm": round(actual_dist, 2),
                    "required_distance_mm": required_dist,
                    "segregation_level": matrix_entry.segregation_level,
                    "description": matrix_entry.description,
                    "position_a": {"x": pc_a.x, "y": pc_a.y, "z": pc_a.z},
                    "position_b": {"x": pc_b.x, "y": pc_b.y, "z": pc_b.z},
                })

    return len(violations) == 0, violations


def run_weight_deviation_check(db: Session, plan_id: int, tolerance_ratio: float = 0.02) -> Tuple[bool, List[Dict[str, Any]]]:
    plan = crud.get_packing_plan(db, plan_id=plan_id)
    if not plan:
        return False, [{"error": "方案不存在"}]

    violations = []
    packed_cargos = crud.get_packed_cargos(db, plan_id=plan_id)
    actual_total = 0.0
    declared_total = 0.0
    has_any_declared = False

    for pc in packed_cargos:
        cargo = crud.get_cargo(db, cargo_id=pc.cargo_id)
        actual_w = pc.weight
        actual_total += actual_w
        if cargo and cargo.declared_weight is not None:
            declared_w = cargo.declared_weight
            declared_total += declared_w
            has_any_declared = True
            if actual_w > 0:
                deviation = abs(declared_w - actual_w) / actual_w
                if deviation > tolerance_ratio:
                    violations.append({
                        "cargo_id": pc.cargo_id,
                        "cargo_name": pc.cargo_name,
                        "declared_weight_kg": declared_w,
                        "actual_weight_kg": actual_w,
                        "deviation_ratio": round(deviation, 4),
                        "tolerance_ratio": tolerance_ratio,
                        "is_total": False,
                    })

    if plan.declared_weight is not None and actual_total > 0:
        total_deviation = abs(plan.declared_weight - actual_total) / actual_total
        if total_deviation > tolerance_ratio:
            violations.append({
                "cargo_id": None,
                "cargo_name": "__TOTAL__",
                "declared_weight_kg": plan.declared_weight,
                "actual_weight_kg": round(actual_total, 2),
                "deviation_ratio": round(total_deviation, 4),
                "tolerance_ratio": tolerance_ratio,
                "is_total": True,
            })
    elif has_any_declared and declared_total > 0 and actual_total > 0:
        total_deviation = abs(declared_total - actual_total) / actual_total
        if total_deviation > tolerance_ratio:
            violations.append({
                "cargo_id": None,
                "cargo_name": "__TOTAL_SUM__",
                "declared_weight_kg": round(declared_total, 2),
                "actual_weight_kg": round(actual_total, 2),
                "deviation_ratio": round(total_deviation, 4),
                "tolerance_ratio": tolerance_ratio,
                "is_total": True,
            })

    return len(violations) == 0, violations


def run_declared_name_match_check(db: Session, plan_id: int) -> Tuple[bool, List[Dict[str, Any]]]:
    plan = crud.get_packing_plan(db, plan_id=plan_id)
    if not plan:
        return False, [{"error": "方案不存在"}]

    violations = []
    packed_cargos = crud.get_packed_cargos(db, plan_id=plan_id)

    for pc in packed_cargos:
        cargo = crud.get_cargo(db, cargo_id=pc.cargo_id)
        if not cargo:
            violations.append({
                "cargo_id": pc.cargo_id,
                "cargo_name": pc.cargo_name,
                "declared_name": None,
                "issue": "货物记录不存在，无法匹配申报品名",
                "severity": "error"
            })
            continue
        if not cargo.declared_name:
            violations.append({
                "cargo_id": pc.cargo_id,
                "cargo_name": pc.cargo_name,
                "declared_name": None,
                "issue": "缺少申报品名(declared_name为空)",
                "severity": "error"
            })
            continue
        normalized_actual = (cargo.name or "").strip().lower()
        normalized_declared = (cargo.declared_name or "").strip().lower()
        if not normalized_actual or not normalized_declared:
            violations.append({
                "cargo_id": pc.cargo_id,
                "cargo_name": pc.cargo_name,
                "declared_name": cargo.declared_name,
                "issue": "品名或申报品名为空字符串",
                "severity": "error"
            })
            continue
        if normalized_actual != normalized_declared:
            violations.append({
                "cargo_id": pc.cargo_id,
                "cargo_name": pc.cargo_name,
                "declared_name": cargo.declared_name,
                "issue": f"录入品名({cargo.name})与申报品名({cargo.declared_name})不一致",
                "severity": "error"
            })

    return len(violations) == 0, violations


def run_full_compliance_audit(db: Session, plan_id: int, auditor: str = None) -> Dict[str, Any]:
    plan = crud.get_packing_plan(db, plan_id=plan_id)
    if not plan:
        return {"error": "方案不存在"}

    if not plan.content_hash:
        plan.content_hash = crud.compute_plan_content_hash(db, plan_id)
        db.commit()
        db.refresh(plan)

    if not plan.version:
        plan.version = 1
        db.commit()
        db.refresh(plan)

    hz_passed, hz_violations = run_hazard_segregation_check(db, plan_id)
    wt_passed, wt_violations = run_weight_deviation_check(db, plan_id)
    nm_passed, nm_violations = run_declared_name_match_check(db, plan_id)
    tp_passed, tp_violations = run_temperature_zone_check(db, plan_id)

    overall_passed = hz_passed and wt_passed and nm_passed and tp_passed

    audit_details = {
        "plan_info": {
            "plan_id": plan.id,
            "plan_no": plan.plan_no,
            "version": plan.version,
            "content_hash": plan.content_hash,
            "container_name": plan.container_name,
            "container_no": plan.container_no,
            "seal_no": plan.seal_no,
            "total_cargos": plan.total_cargos,
            "placed_count": plan.placed_count,
            "total_weight": plan.total_weight,
            "declared_weight": plan.declared_weight,
            "volume_utilization": plan.volume_utilization,
            "cog": {
                "x": plan.cog_x, "y": plan.cog_y, "z": plan.cog_z,
                "offset_x_ratio": plan.cog_offset_x_ratio,
                "offset_y_ratio": plan.cog_offset_y_ratio,
                "within_limit": plan.cog_within_limit,
            },
        },
        "checks_summary": {
            "hazard_segregation": {
                "passed": hz_passed,
                "violation_count": len(hz_violations),
                "description": "危险品分类相邻隔离校验"
            },
            "weight_deviation": {
                "passed": wt_passed,
                "violation_count": len(wt_violations),
                "description": "单箱申报重量偏差校验(阈值2%)"
            },
            "declared_name_match": {
                "passed": nm_passed,
                "violation_count": len(nm_violations),
                "description": "货物申报品名逐条匹配校验"
            },
            "temperature_zone": {
                "passed": tp_passed,
                "violation_count": len(tp_violations),
                "description": "冷链温控分区隔离校验(相邻缓冲+冷冻容积60%限制)"
            },
        },
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    remarks_parts = []
    if not hz_passed:
        remarks_parts.append(f"危险品隔离违规{len(hz_violations)}项")
    if not wt_passed:
        remarks_parts.append(f"重量偏差违规{len(wt_violations)}项")
    if not nm_passed:
        remarks_parts.append(f"品名匹配违规{len(nm_violations)}项")
    if not tp_passed:
        remarks_parts.append(f"温控分区违规{len(tp_violations)}项")
    remarks = "通过全部合规校验" if overall_passed else "校验失败: " + "; ".join(remarks_parts)

    audit_data = {
        "audit_no": crud.generate_audit_no(),
        "plan_id": plan_id,
        "plan_version": plan.version,
        "plan_content_hash": plan.content_hash,
        "is_passed": overall_passed,
        "hazard_check_passed": hz_passed,
        "weight_check_passed": wt_passed,
        "name_check_passed": nm_passed,
        "temperature_check_passed": tp_passed,
        "hazard_violations": hz_violations,
        "weight_violations": wt_violations,
        "name_violations": nm_violations,
        "temperature_violations": tp_violations,
        "audit_details": audit_details,
        "auditor": auditor,
        "remarks": remarks,
    }
    db_audit = crud.create_compliance_audit(db, audit_data)

    return {
        "audit_id": db_audit.id,
        "audit_no": db_audit.audit_no,
        "is_passed": overall_passed,
        "plan_id": plan_id,
        "plan_no": plan.plan_no,
        "plan_version": plan.version,
        "hazard_check_passed": hz_passed,
        "weight_check_passed": wt_passed,
        "name_check_passed": nm_passed,
        "temperature_check_passed": tp_passed,
        "hazard_violations_count": len(hz_violations),
        "weight_violations_count": len(wt_violations),
        "name_violations_count": len(nm_violations),
        "temperature_violations_count": len(tp_violations),
        "hazard_violations": hz_violations,
        "weight_violations": wt_violations,
        "name_violations": nm_violations,
        "temperature_violations": tp_violations,
        "remarks": remarks,
        "audit_details": audit_details,
        "audited_at": db_audit.audited_at.isoformat() if db_audit.audited_at else "",
    }


TEMPERATURE_PRIORITY = {
    "FROZEN": 3,
    "REFRIGERATED": 2,
    "AMBIENT": 1,
}

TEMPERATURE_LABELS = {
    "FROZEN": "冷冻(-18℃以下)",
    "REFRIGERATED": "冷藏(0-5℃)",
    "AMBIENT": "常温",
}


def _get_temperature_priority(tc: str) -> int:
    return TEMPERATURE_PRIORITY.get(tc, 1)


def _boxes_are_adjacent(box_a, box_b) -> bool:
    ax1, ay1, az1 = box_a.x, box_a.y, box_a.z
    ax2, ay2, az2 = box_a.x + box_a.length, box_a.y + box_a.width, box_a.z + box_a.height
    bx1, by1, bz1 = box_b.x, box_b.y, box_b.z
    bx2, by2, bz2 = box_b.x + box_b.length, box_b.y + box_b.width, box_b.z + box_b.height

    overlap_x = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    overlap_y = max(0.0, min(ay2, by2) - max(ay1, by1))
    overlap_z = max(0.0, min(az2, bz2) - max(az1, bz1))

    touch_x = abs(ax2 - bx1) < 0.1 or abs(bx2 - ax1) < 0.1
    touch_y = abs(ay2 - by1) < 0.1 or abs(by2 - ay1) < 0.1
    touch_z = abs(az2 - bz1) < 0.1 or abs(bz2 - az1) < 0.1

    if touch_x and overlap_y > 0 and overlap_z > 0:
        return True
    if touch_y and overlap_x > 0 and overlap_z > 0:
        return True
    if touch_z and overlap_x > 0 and overlap_y > 0:
        return True

    return False


def _get_cargo_temperature_class(db: Session, cargo_id: int, packed_cargo) -> str:
    if hasattr(packed_cargo, 'temperature_class') and packed_cargo.temperature_class:
        return packed_cargo.temperature_class
    cargo = crud.get_cargo(db, cargo_id=cargo_id)
    if cargo and hasattr(cargo, 'temperature_class') and cargo.temperature_class:
        return cargo.temperature_class
    return "AMBIENT"


def run_temperature_zone_check(
    db: Session, plan_id: int, frozen_volume_limit_ratio: float = 0.6
) -> Tuple[bool, List[Dict[str, Any]]]:
    plan = crud.get_packing_plan(db, plan_id=plan_id)
    if not plan:
        return False, [{"error": "方案不存在", "violation_type": "error"}]

    packed_cargos = crud.get_packed_cargos(db, plan_id=plan_id)
    container = crud.get_container(db, container_id=plan.container_id)
    if not container:
        return False, [{"error": "集装箱信息不存在", "violation_type": "error"}]

    violations = []
    n = len(packed_cargos)

    temp_info = []
    for pc in packed_cargos:
        tc = _get_cargo_temperature_class(db, pc.cargo_id, pc)
        volume = (pc.length * pc.width * pc.height) / 1e9
        temp_info.append({
            "packed": pc,
            "temperature_class": tc,
            "priority": _get_temperature_priority(tc),
            "volume_cbm": volume,
        })

    frozen_total_volume = sum(
        info["volume_cbm"] for info in temp_info if info["temperature_class"] == "FROZEN"
    )
    container_total_volume = (container.length * container.width * container.height) / 1e9
    frozen_volume_ratio = frozen_total_volume / container_total_volume if container_total_volume > 0 else 0

    if frozen_volume_ratio > frozen_volume_limit_ratio:
        violations.append({
            "violation_type": "frozen_volume_exceeded",
            "description": (
                f"冷冻货物总体积({frozen_total_volume:.3f} CBM)占集装箱可用容积"
                f"({container_total_volume:.3f} CBM)的比例为{frozen_volume_ratio*100:.1f}%，"
                f"超过最大允许比例{frozen_volume_limit_ratio*100:.0f}%"
            ),
            "frozen_volume_cbm": round(frozen_total_volume, 4),
            "container_volume_cbm": round(container_total_volume, 4),
            "frozen_volume_ratio": round(frozen_volume_ratio, 4),
            "max_allowed_ratio": frozen_volume_limit_ratio,
        })

    adjacent_pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            if _boxes_are_adjacent(temp_info[i]["packed"], temp_info[j]["packed"]):
                adjacent_pairs.append((i, j))

    checked_pairs = set()
    for i, j in adjacent_pairs:
        pair_key = tuple(sorted([i, j]))
        if pair_key in checked_pairs:
            continue
        checked_pairs.add(pair_key)

        info_a = temp_info[i]
        info_b = temp_info[j]
        tc_a = info_a["temperature_class"]
        tc_b = info_b["temperature_class"]
        prio_a = info_a["priority"]
        prio_b = info_b["priority"]

        if prio_a == prio_b:
            continue

        prio_diff = abs(prio_a - prio_b)
        if prio_diff >= 2:
            pc_a = info_a["packed"]
            pc_b = info_b["packed"]
            violations.append({
                "violation_type": "direct_adjacency",
                "cargo_a_id": pc_a.cargo_id,
                "cargo_a_name": pc_a.cargo_name,
                "temperature_class_a": tc_a,
                "temperature_class_a_label": TEMPERATURE_LABELS.get(tc_a, tc_a),
                "cargo_b_id": pc_b.cargo_id,
                "cargo_b_name": pc_b.cargo_name,
                "temperature_class_b": tc_b,
                "temperature_class_b_label": TEMPERATURE_LABELS.get(tc_b, tc_b),
                "position_a": {"x": pc_a.x, "y": pc_a.y, "z": pc_a.z},
                "position_b": {"x": pc_b.x, "y": pc_b.y, "z": pc_b.z},
                "description": (
                    f"{TEMPERATURE_LABELS.get(tc_a, tc_a)}货物({pc_a.cargo_name})与"
                    f"{TEMPERATURE_LABELS.get(tc_b, tc_b)}货物({pc_b.cargo_name})直接相邻，"
                    f"中间缺少{'' if prio_a > prio_b else TEMPERATURE_LABELS.get('REFRIGERATED', '冷藏')}"
                    f"缓冲层或隔热隔板"
                ),
            })

    return len(violations) == 0, violations


def _get_cargo_info(db: Session, cargo_id: int):
    return crud.get_cargo(db, cargo_id=cargo_id)


def _determine_stack_layer(z: float, all_zs: List[float]) -> int:
    if not all_zs:
        return 1
    unique_zs = sorted(set(round(z_val, 1) for z_val in all_zs))
    z_round = round(z, 1)
    for idx, zv in enumerate(unique_zs):
        if abs(z_round - zv) < 1.0:
            return idx + 1
    return len(unique_zs) + 1


def build_document_items(db: Session, plan_id: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    plan = crud.get_packing_plan(db, plan_id=plan_id)
    packed_cargos = crud.get_packed_cargos(db, plan_id=plan_id)
    container = crud.get_container(db, container_id=plan.container_id)

    all_z_values = [pc.z for pc in packed_cargos]
    items = []
    total_weight = 0.0
    total_volume_cbm = 0.0
    piece_count = 0

    for idx, pc in enumerate(sorted(packed_cargos, key=lambda p: (p.z, p.x, p.y))):
        cargo = _get_cargo_info(db, pc.cargo_id)
        volume_m3 = (pc.length * pc.width * pc.height) / 1e9
        total_weight += pc.weight
        total_volume_cbm += volume_m3
        piece_count += 1
        stack_layer = _determine_stack_layer(pc.z, all_z_values)
        items.append({
            "item_no": idx + 1,
            "cargo_id": pc.cargo_id,
            "cargo_name": pc.cargo_name,
            "declared_name": cargo.declared_name if cargo else None,
            "package_count": 1,
            "package_type": "CTN",
            "weight_kg": round(pc.weight, 2),
            "declared_weight_kg": cargo.declared_weight if cargo else None,
            "length_mm": pc.length,
            "width_mm": pc.width,
            "height_mm": pc.height,
            "volume_cbm": round(volume_m3, 6),
            "x_mm": pc.x,
            "y_mm": pc.y,
            "z_mm": pc.z,
            "stack_layer": stack_layer,
            "hazard_class": cargo.hazard_class if cargo else None,
            "marks_and_numbers": f"NO.{idx + 1}",
            "hs_code": None,
        })

    summary = {
        "total_packages": piece_count,
        "total_weight_kg": round(total_weight, 2),
        "total_volume_cbm": round(total_volume_cbm, 4),
        "cog_offset_ratio": round(max(abs(plan.cog_offset_x_ratio or 0), abs(plan.cog_offset_y_ratio or 0)), 4),
        "volume_utilization": round((plan.volume_utilization or 0) * 100, 2),
        "weight_utilization": round((total_weight / container.max_weight) * 100, 2) if container and container.max_weight else 0,
    }
    return items, summary


def generate_packing_list_content(
    plan, container, items: list, summary: dict,
    container_no: str, seal_no: str, issued_by: str
) -> Dict[str, Any]:
    return {
        "document_title": "PACKING LIST / 装箱清单",
        "document_no_ref": None,
        "shipper": "SYSTEM GENERATED",
        "consignee": "TO ORDER",
        "vessel_voyage": "NOT APPLICABLE",
        "port_of_loading": "NOT SPECIFIED",
        "port_of_discharge": "NOT SPECIFIED",
        "container_info": {
            "container_name": plan.container_name,
            "container_no": container_no or plan.container_no or "NOT ASSIGNED",
            "seal_no": seal_no or plan.seal_no or "NOT SEALED",
            "container_size": f"L{container.length}xW{container.width}xH{container.height}mm" if container else "N/A",
            "max_weight_kg": container.max_weight if container else None,
        },
        "summary": summary,
        "cargo_items": items,
        "declaration": {
            "issued_by": issued_by or "SYSTEM",
            "declaration_text": "兹声明上述装箱信息与实际装载情况完全一致，所有货物已正确申报。"
                               " We hereby declare that the above packing information is fully "
                               "consistent with the actual loading condition and all cargoes have been properly declared.",
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def generate_clc_content(
    plan, container, items: list, summary: dict,
    container_no: str, seal_no: str, issued_by: str
) -> Dict[str, Any]:
    layered_items = {}
    for it in items:
        layer = it["stack_layer"]
        layered_items.setdefault(layer, []).append(it)

    return {
        "document_title": "CONTAINER LOADING CERTIFICATE / 集装箱装载证明",
        "document_no_ref": None,
        "certificate_scope": "本证书证明所列集装箱已按以下所列明细完成装载并施加铅封。",
        "container_info": {
            "container_name": plan.container_name,
            "container_no": container_no or plan.container_no or "NOT ASSIGNED",
            "seal_no": seal_no or plan.seal_no or "NOT SEALED",
            "container_size": f"L{container.length}xW{container.width}xH{container.height}mm" if container else "N/A",
            "max_weight_kg": container.max_weight if container else None,
        },
        "loading_metrics": {
            **summary,
            "cog_info": {
                "cog_x_mm": plan.cog_x,
                "cog_y_mm": plan.cog_y,
                "cog_z_mm": plan.cog_z,
                "cog_offset_x_ratio": plan.cog_offset_x_ratio,
                "cog_offset_y_ratio": plan.cog_offset_y_ratio,
                "cog_within_limit": plan.cog_within_limit,
            }
        },
        "layered_loading": {
            f"Layer_{layer}": {
                "layer_no": layer,
                "piece_count": len(its),
                "layer_weight_kg": round(sum(i["weight_kg"] for i in its), 2),
                "items": its
            }
            for layer, its in sorted(layered_items.items())
        },
        "certification_statement": (
            "This is to certify that the above mentioned container has been loaded, "
            "stuffed and sealed in accordance with the declared packing list. "
            "All cargo particulars, weights and positions are confirmed accurate."
        ),
        "authorized_signatory": {
            "name": issued_by or "SYSTEM AUTHORIZED",
            "title": "Loading Supervisor",
            "signed_at": datetime.utcnow().isoformat() + "Z",
        }
    }


def generate_customs_documents(
    db: Session,
    plan_id: int,
    document_type: str = "BOTH",
    issued_by: str = None,
    override_container_no: str = None,
    override_seal_no: str = None,
    force_audit: bool = True
) -> Dict[str, Any]:
    plan = crud.get_packing_plan(db, plan_id=plan_id)
    if not plan:
        return {"error": "方案不存在"}

    if not plan.content_hash:
        plan.content_hash = crud.compute_plan_content_hash(db, plan_id)
    if not plan.version:
        plan.version = 1
    db.commit()
    db.refresh(plan)

    latest_audit = crud.get_latest_passed_audit(db, plan_id)
    need_new_audit = (
        latest_audit is None
        or latest_audit.plan_version != plan.version
        or latest_audit.plan_content_hash != plan.content_hash
    )
    if need_new_audit:
        if not force_audit:
            return {
                "error": "该方案尚无有效合规审计结论，请先执行合规校验。",
                "need_audit": True
            }
        audit_result = run_full_compliance_audit(db, plan_id, auditor=issued_by)
        if not audit_result.get("is_passed", False):
            return {
                "error": "合规校验未通过，无法生成海关申报单据。",
                "audit_result": audit_result
            }
        latest_audit = crud.get_compliance_audit(db, audit_id=audit_result["audit_id"])

    container = crud.get_container(db, container_id=plan.container_id)
    container_no = override_container_no or plan.container_no
    seal_no = override_seal_no or plan.seal_no
    doc_header = {
        "container_no": container_no,
        "seal_no": seal_no,
        "issued_by": issued_by,
    }
    items, summary = build_document_items(db, plan_id)

    created = {}
    if document_type in ("PACKING_LIST", "BOTH"):
        doc_content = generate_packing_list_content(
            plan, container, items, summary, container_no, seal_no, issued_by
        )
        doc = crud.create_customs_document(
            db=db,
            doc_type="PACKING_LIST",
            plan_id=plan.id,
            plan_version=plan.version,
            plan_content_hash=plan.content_hash,
            audit_id=latest_audit.id,
            doc_header=doc_header,
            doc_summary=summary,
            document_content=doc_content,
            document_items=items,
        )
        doc_content["document_no_ref"] = doc.document_no
        created["PACKING_LIST"] = doc
        db.query(models.CustomsDocument).filter(models.CustomsDocument.id == doc.id).update(
            {"document_content": doc_content}
        )
        db.commit()

    if document_type in ("CLC", "BOTH"):
        doc_content = generate_clc_content(
            plan, container, items, summary, container_no, seal_no, issued_by
        )
        doc = crud.create_customs_document(
            db=db,
            doc_type="CLC",
            plan_id=plan.id,
            plan_version=plan.version,
            plan_content_hash=plan.content_hash,
            audit_id=latest_audit.id,
            doc_header=doc_header,
            doc_summary=summary,
            document_content=doc_content,
            document_items=items,
        )
        doc_content["document_no_ref"] = doc.document_no
        created["CLC"] = doc
        db.query(models.CustomsDocument).filter(models.CustomsDocument.id == doc.id).update(
            {"document_content": doc_content}
        )
        db.commit()

    result = {
        "plan_id": plan.id,
        "plan_no": plan.plan_no,
        "plan_version": plan.version,
        "audit_id": latest_audit.id,
        "audit_no": latest_audit.audit_no,
        "created_documents": {},
    }
    for dtype, doc in created.items():
        db.refresh(doc)
        result["created_documents"][dtype] = {
            "document_id": doc.id,
            "document_no": doc.document_no,
            "document_type": doc.document_type,
            "status": doc.status,
            "issued_at": doc.issued_at.isoformat() if doc.issued_at else "",
            "total_packages": doc.total_packages,
            "total_weight_kg": doc.total_weight_kg,
            "total_volume_cbm": doc.total_volume_cbm,
        }
    return result
