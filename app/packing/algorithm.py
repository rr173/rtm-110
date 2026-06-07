from typing import List, Tuple, Dict
from dataclasses import dataclass


@dataclass
class Box:
    cargo_id: int
    cargo_name: str
    length: float
    width: float
    height: float
    weight: float
    can_rotate_horizontal: bool
    can_flip: bool
    max_top_load: float


@dataclass
class PlacedBox:
    cargo_id: int
    cargo_name: str
    x: float
    y: float
    z: float
    length: float
    width: float
    height: float
    weight: float
    max_top_load: float
    orientation: str


@dataclass
class ExtremePoint:
    x: float
    y: float
    z: float


def get_orientations(box: Box) -> List[Tuple[float, float, float, str]]:
    orientations = []
    l, w, h = box.length, box.width, box.height

    orientations.append((l, w, h, "original"))

    if box.can_rotate_horizontal:
        orientations.append((w, l, h, "rotated_90"))

    if box.can_flip:
        orientations.append((l, h, w, "flipped_l"))
        orientations.append((w, h, l, "flipped_w"))
        if box.can_rotate_horizontal:
            orientations.append((h, l, w, "flipped_rotated_l"))
            orientations.append((h, w, l, "flipped_rotated_w"))

    seen = set()
    unique = []
    for o in orientations:
        key = (round(o[0], 3), round(o[1], 3), round(o[2], 3))
        if key not in seen:
            seen.add(key)
            unique.append(o)
    return unique


def is_supported(placed_boxes: List[PlacedBox], bx: float, by: float, bz: float,
                 bl: float, bw: float) -> bool:
    if bz <= 0.001:
        return True

    bottom_area = bl * bw
    supported_area = 0.0

    for pb in placed_boxes:
        pb_top_z = pb.z + pb.height
        if abs(pb_top_z - bz) > 0.001:
            continue

        x_overlap_start = max(bx, pb.x)
        x_overlap_end = min(bx + bl, pb.x + pb.length)
        y_overlap_start = max(by, pb.y)
        y_overlap_end = min(by + bw, pb.y + pb.width)

        if x_overlap_end > x_overlap_start and y_overlap_end > y_overlap_start:
            overlap_area = (x_overlap_end - x_overlap_start) * (y_overlap_end - y_overlap_start)
            supported_area += overlap_area

    return supported_area >= bottom_area * 0.999


def get_supporting_boxes(placed_boxes: List[PlacedBox], bx: float, by: float, bz: float,
                         bl: float, bw: float) -> List[Tuple[PlacedBox, float]]:
    """返回所有直接支撑新箱子的箱子及其接触面积"""
    supporters = []
    for pb in placed_boxes:
        pb_top_z = pb.z + pb.height
        if abs(pb_top_z - bz) > 0.001:
            continue

        x_overlap_start = max(bx, pb.x)
        x_overlap_end = min(bx + bl, pb.x + pb.length)
        y_overlap_start = max(by, pb.y)
        y_overlap_end = min(by + bw, pb.y + pb.width)

        if x_overlap_end > x_overlap_start and y_overlap_end > y_overlap_start:
            overlap_area = (x_overlap_end - x_overlap_start) * (y_overlap_end - y_overlap_start)
            supporters.append((pb, overlap_area))
    return supporters


def check_weight_bearing(placed_boxes: List[PlacedBox], bx: float, by: float, bz: float,
                         bl: float, bw: float, b_weight: float) -> bool:
    """检查承压限制：新箱子重量按接触面积比例分配给各支撑箱"""
    if bz <= 0.001:
        return True

    supporters = get_supporting_boxes(placed_boxes, bx, by, bz, bl, bw)
    if not supporters:
        return False

    total_contact_area = sum(area for _, area in supporters)
    if total_contact_area <= 0.001:
        return False

    for pb, contact_area in supporters:
        weight_ratio = contact_area / total_contact_area
        load_on_pb = b_weight * weight_ratio
        if load_on_pb > pb.max_top_load + 0.001:
            return False

    return True


def boxes_overlap(x1: float, y1: float, z1: float, l1: float, w1: float, h1: float,
                  x2: float, y2: float, z2: float, l2: float, w2: float, h2: float) -> bool:
    if x1 >= x2 + l2 - 0.001 or x2 >= x1 + l1 - 0.001:
        return False
    if y1 >= y2 + w2 - 0.001 or y2 >= y1 + w1 - 0.001:
        return False
    if z1 >= z2 + h2 - 0.001 or z2 >= z1 + h1 - 0.001:
        return False
    return True


def can_place_at(placed_boxes: List[PlacedBox], bx: float, by: float, bz: float,
                 bl: float, bw: float, bh: float, container_l: float, container_w: float,
                 container_h: float) -> bool:
    if bx < -0.001 or by < -0.001 or bz < -0.001:
        return False
    if bx + bl > container_l + 0.001 or by + bw > container_w + 0.001 or bz + bh > container_h + 0.001:
        return False

    for pb in placed_boxes:
        if boxes_overlap(bx, by, bz, bl, bw, bh,
                         pb.x, pb.y, pb.z, pb.length, pb.width, pb.height):
            return False

    return True


def generate_extreme_points(placed: PlacedBox) -> List[ExtremePoint]:
    points = []
    points.append(ExtremePoint(placed.x + placed.length, placed.y, placed.z))
    points.append(ExtremePoint(placed.x, placed.y + placed.width, placed.z))
    points.append(ExtremePoint(placed.x, placed.y, placed.z + placed.height))
    points.append(ExtremePoint(placed.x + placed.length, placed.y + placed.width, placed.z))
    points.append(ExtremePoint(placed.x + placed.length, placed.y, placed.z + placed.height))
    points.append(ExtremePoint(placed.x, placed.y + placed.width, placed.z + placed.height))
    return points


def is_point_dominated(ep: ExtremePoint, other: ExtremePoint) -> bool:
    return (other.x <= ep.x + 0.001 and
            other.y <= ep.y + 0.001 and
            other.z <= ep.z + 0.001 and
            (other.x < ep.x - 0.001 or other.y < ep.y - 0.001 or other.z < ep.z - 0.001))


def prune_extreme_points(points: List[ExtremePoint], placed_boxes: List[PlacedBox],
                         container_l: float, container_w: float, container_h: float) -> List[ExtremePoint]:
    unique = []
    seen = set()
    for ep in points:
        key = (round(ep.x, 2), round(ep.y, 2), round(ep.z, 2))
        if key not in seen:
            seen.add(key)
            if ep.x <= container_l + 0.001 and ep.y <= container_w + 0.001 and ep.z <= container_h + 0.001:
                unique.append(ep)

    pruned = []
    for i, ep1 in enumerate(unique):
        dominated = False
        for j, ep2 in enumerate(unique):
            if i == j:
                continue
            if is_point_dominated(ep1, ep2):
                dominated = True
                break
        if not dominated:
            pruned.append(ep1)

    return pruned


def calculate_cog(placed_boxes: List[PlacedBox]) -> Tuple[float, float, float]:
    total_weight = sum(pb.weight for pb in placed_boxes)
    if total_weight == 0:
        return (0, 0, 0)

    cx = sum(pb.weight * (pb.x + pb.length / 2) for pb in placed_boxes) / total_weight
    cy = sum(pb.weight * (pb.y + pb.width / 2) for pb in placed_boxes) / total_weight
    cz = sum(pb.weight * (pb.z + pb.height / 2) for pb in placed_boxes) / total_weight

    return (cx, cy, cz)


def drop_box(placed_boxes: List[PlacedBox], bx: float, by: float, bz: float,
             bl: float, bw: float) -> float:
    """让箱子自由下落到被支撑的位置"""
    if bz <= 0.001:
        return 0.0

    final_z = 0.0

    for pb in placed_boxes:
        pb_top = pb.z + pb.height
        if pb_top > bz + 0.001:
            continue

        x_overlap_start = max(bx, pb.x)
        x_overlap_end = min(bx + bl, pb.x + pb.length)
        y_overlap_start = max(by, pb.y)
        y_overlap_end = min(by + bw, pb.y + pb.width)

        if x_overlap_end > x_overlap_start + 0.001 and y_overlap_end > y_overlap_start + 0.001:
            overlap_area = (x_overlap_end - x_overlap_start) * (y_overlap_end - y_overlap_start)
            bottom_area = bl * bw
            if overlap_area >= bottom_area * 0.5:
                if pb_top > final_z + 0.001:
                    final_z = pb_top

    return final_z


def calculate_cog_offset(cog_x: float, cog_y: float, container_l: float, container_w: float) -> Tuple[float, float]:
    """计算重心相对于中心的偏移比例"""
    center_x = container_l / 2
    center_y = container_w / 2
    offset_x_ratio = abs(cog_x - center_x) / container_l
    offset_y_ratio = abs(cog_y - center_y) / container_w
    return offset_x_ratio, offset_y_ratio


def predict_new_cog(placed_boxes: List[PlacedBox], new_box_weight: float,
                    new_box_cx: float, new_box_cy: float, new_box_cz: float
                    ) -> Tuple[float, float, float]:
    """预测放置新箱子后的重心"""
    current_weight = sum(pb.weight for pb in placed_boxes)
    new_total_weight = current_weight + new_box_weight

    if new_total_weight <= 0.001:
        return (new_box_cx, new_box_cy, new_box_cz)

    if current_weight <= 0.001:
        return (new_box_cx, new_box_cy, new_box_cz)

    current_cx, current_cy, current_cz = calculate_cog(placed_boxes)

    new_cx = (current_cx * current_weight + new_box_cx * new_box_weight) / new_total_weight
    new_cy = (current_cy * current_weight + new_box_cy * new_box_weight) / new_total_weight
    new_cz = (current_cz * current_weight + new_box_cz * new_box_weight) / new_total_weight

    return (new_cx, new_cy, new_cz)


def get_dynamic_cog_limit(placed_count: int, total_count: int) -> float:
    """
    动态重心限制：前几件不限制，逐渐收紧
    - 前10件：完全不限制（先装进去再说）
    - 10-20件：放宽到30%
    - 20件以上：20%（比原来15%更合理）
    """
    if placed_count < 10:
        return 1.0
    elif placed_count < 20:
        return 0.30
    else:
        return 0.20


def pack_boxes(container_length: float, container_width: float, container_height: float,
               container_max_weight: float, boxes: List[Box]) -> Dict:
    """
    三维装箱算法 - 极值点法
    约束：
    - 底部支撑：至少99.9%底面被支撑
    - 箱壁限制：不超出集装箱
    - 总重量：不超过载重上限
    - 承压限制：上面的货不能超过下面货的承压上限（按接触面积比例分配重量）
    - 翻转约束：不可翻转的货物保持原方向
    - 重心平衡：优先选重心居中的位置，动态调整限制避免卡掉太多货
    """
    sorted_boxes = sorted(boxes, key=lambda b: (b.length * b.width * b.height, b.weight), reverse=True)
    total_boxes = len(sorted_boxes)

    extreme_points = [ExtremePoint(0, 0, 0)]
    placed_boxes: List[PlacedBox] = []
    unplaced_boxes = []
    total_weight = 0.0

    center_x = container_length / 2
    center_y = container_width / 2

    for box in sorted_boxes:
        placed = False
        orientations = get_orientations(box)

        best_placement = None
        best_score = float('inf')

        current_limit = get_dynamic_cog_limit(len(placed_boxes), total_boxes)

        for ep_idx, ep in enumerate(extreme_points):
            for (bl, bw, bh, orientation) in orientations:
                if total_weight + box.weight > container_max_weight + 0.001:
                    continue

                if ep.x + bl > container_length + 0.001:
                    continue
                if ep.y + bw > container_width + 0.001:
                    continue
                if ep.z + bh > container_height + 0.001:
                    continue

                dropped_z = drop_box(placed_boxes, ep.x, ep.y, ep.z, bl, bw)

                if not can_place_at(placed_boxes, ep.x, ep.y, dropped_z, bl, bw, bh,
                                    container_length, container_width, container_height):
                    continue

                if not is_supported(placed_boxes, ep.x, ep.y, dropped_z, bl, bw):
                    continue

                if not check_weight_bearing(placed_boxes, ep.x, ep.y, dropped_z, bl, bw, box.weight):
                    continue

                new_cx = ep.x + bl / 2
                new_cy = ep.y + bw / 2
                new_cz = dropped_z + bh / 2

                future_cog_x, future_cog_y, future_cog_z = predict_new_cog(
                    placed_boxes, box.weight, new_cx, new_cy, new_cz
                )

                offset_x_ratio = abs(future_cog_x - center_x) / container_length
                offset_y_ratio = abs(future_cog_y - center_y) / container_width
                cog_offset_score = offset_x_ratio + offset_y_ratio

                if offset_x_ratio > current_limit or offset_y_ratio > current_limit:
                    continue

                score = (dropped_z * 1000000
                         + cog_offset_score * 100000
                         + ep.y * 100
                         + ep.x)

                if score < best_score:
                    best_score = score
                    best_placement = (ep_idx, ep.x, ep.y, dropped_z, bl, bw, bh, orientation)

        if best_placement is not None:
            ep_idx, px, py, pz, pl, pw, ph, orientation = best_placement

            placed_box = PlacedBox(
                cargo_id=box.cargo_id,
                cargo_name=box.cargo_name,
                x=px,
                y=py,
                z=pz,
                length=pl,
                width=pw,
                height=ph,
                weight=box.weight,
                max_top_load=box.max_top_load,
                orientation=orientation
            )

            placed_boxes.append(placed_box)
            total_weight += box.weight

            used_ep = extreme_points.pop(ep_idx)

            new_points = generate_extreme_points(placed_box)
            extreme_points.extend(new_points)
            extreme_points = prune_extreme_points(extreme_points, placed_boxes,
                                                  container_length, container_width, container_height)

            extreme_points.sort(key=lambda ep: ep.z * 10000000 + ep.y * 10000 + ep.x)

            placed = True

        if not placed:
            unplaced_boxes.append({
                "cargo_id": box.cargo_id,
                "cargo_name": box.cargo_name,
                "reason": "无法找到合适的摆放位置"
            })

    total_volume = container_length * container_width * container_height
    used_volume = sum(pb.length * pb.width * pb.height for pb in placed_boxes)
    volume_utilization = used_volume / total_volume if total_volume > 0 else 0

    cog_x, cog_y, cog_z = calculate_cog(placed_boxes)

    offset_x_ratio = abs(cog_x - center_x) / container_length
    offset_y_ratio = abs(cog_y - center_y) / container_width

    final_cog_limit = 0.20
    cog_within_limit = offset_x_ratio <= final_cog_limit and offset_y_ratio <= final_cog_limit

    placed_cargo_list = []
    for pb in placed_boxes:
        placed_cargo_list.append({
            "cargo_id": pb.cargo_id,
            "cargo_name": pb.cargo_name,
            "x": pb.x,
            "y": pb.y,
            "z": pb.z,
            "length": pb.length,
            "width": pb.width,
            "height": pb.height,
            "weight": pb.weight,
            "orientation": pb.orientation
        })

    return {
        "placed_cargos": placed_cargo_list,
        "unplaced_cargos": unplaced_boxes,
        "total_weight": total_weight,
        "volume_utilization": volume_utilization,
        "center_of_gravity": {
            "x": cog_x,
            "y": cog_y,
            "z": cog_z
        },
        "cog_within_limit": cog_within_limit,
        "cog_offset_x_ratio": offset_x_ratio,
        "cog_offset_y_ratio": offset_y_ratio
    }


def calculate_plan_score(
    volume_utilization: float,
    cog_offset_x_ratio: float,
    cog_offset_y_ratio: float,
    placed_count: int,
    total_cargos: int,
    cog_within_limit: bool
) -> float:
    """
    计算方案综合得分（越高越好）
    权重：
    - 体积利用率：40%
    - 重心稳定性：20%
    - 装载率（已装/总数）：40%（最重要，装不下一切免谈）

    惩罚机制：
    - 装载率低于50%：大幅减分
    - 装载率低于30%：直接不及格
    """
    placement_rate = placed_count / total_cargos if total_cargos > 0 else 0

    utilization_score = volume_utilization * 40

    cog_offset_total = cog_offset_x_ratio + cog_offset_y_ratio
    max_offset = 0.4
    cog_score = max(0, (1 - cog_offset_total / max_offset)) * 20
    if not cog_within_limit:
        cog_score *= 0.7

    placement_score = placement_rate * 40

    total_score = utilization_score + cog_score + placement_score

    if placement_rate < 0.3:
        total_score *= 0.3
    elif placement_rate < 0.5:
        total_score *= 0.6
    elif placement_rate < 0.7:
        total_score *= 0.85

    return round(total_score, 2)


def generate_recommendation(
    plan: dict,
    all_plans: list,
    rank: int
) -> str:
    """
    生成方案推荐理由
    """
    reasons = []
    placement_rate = plan["placed_count"] / plan["total_cargos"] if plan["total_cargos"] > 0 else 0

    if placement_rate < 0.5:
        reasons.append("⚠️ 装载率不足50%，不建议使用")

    if rank == 1 and placement_rate >= 0.5:
        reasons.append("综合评分最高，是最优选择")
    elif rank == 1 and placement_rate < 0.5:
        reasons.append("所有方案装载率都偏低，仅作参考")

    best_util = max(p["volume_utilization"] for p in all_plans)
    if plan["volume_utilization"] >= best_util - 0.001 and plan["volume_utilization"] > 0.05:
        reasons.append(f"体积利用率最高（{plan['volume_utilization']*100:.1f}%）")

    min_cog = min(p["cog_offset_x_ratio"] + p["cog_offset_y_ratio"] for p in all_plans)
    current_cog = plan["cog_offset_x_ratio"] + plan["cog_offset_y_ratio"]
    if current_cog <= min_cog + 0.001 and placement_rate >= 0.3:
        reasons.append("重心最稳定")

    max_placed = max(p["placed_count"] for p in all_plans)
    if plan["placed_count"] >= max_placed and plan["placed_count"] > 0:
        reasons.append(f"装载数量最多（{plan['placed_count']}/{plan['total_cargos']}件）")

    if plan["cog_within_limit"] and placement_rate >= 0.3:
        reasons.append("重心偏移在安全范围内")
    elif not plan["cog_within_limit"] and placement_rate >= 0.3:
        reasons.append("注意：重心偏移超出安全范围")

    if plan["unplaced_count"] > 0:
        reasons.append(f"有{plan['unplaced_count']}件货物未装入")

    return "；".join(reasons)


def rank_plans(plans: list) -> list:
    """
    对多个方案进行排名
    plans: 每个元素是包含方案信息的字典
    返回：带排名和推荐理由的方案列表
    """
    for plan in plans:
        score = calculate_plan_score(
            volume_utilization=plan["volume_utilization"],
            cog_offset_x_ratio=plan["cog_offset_x_ratio"],
            cog_offset_y_ratio=plan["cog_offset_y_ratio"],
            placed_count=plan["placed_count"],
            total_cargos=plan["total_cargos"],
            cog_within_limit=plan["cog_within_limit"]
        )
        plan["score"] = score

    sorted_plans = sorted(plans, key=lambda p: p["score"], reverse=True)

    for idx, plan in enumerate(sorted_plans):
        rank = idx + 1
        plan["rank"] = rank
        plan["recommendation"] = generate_recommendation(plan, sorted_plans, rank)

    return sorted_plans
