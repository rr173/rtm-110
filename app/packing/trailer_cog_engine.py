from typing import List, Dict, Tuple
from dataclasses import dataclass, field
from copy import deepcopy
import itertools


@dataclass
class TrailerSpec:
    total_length: float
    platform_length: float
    platform_width: float
    front_axle_position: float
    rear_axle_position: float
    front_axle_max_load: float
    rear_axle_max_load: float
    total_max_weight: float

    @property
    def wheelbase(self) -> float:
        return self.rear_axle_position - self.front_axle_position


@dataclass
class BoxSpec:
    box_id: int
    box_name: str
    length: float
    width: float
    weight: float
    cog_offset_x: float = 0.0

    @property
    def half_length(self) -> float:
        return self.length / 2

    @property
    def half_width(self) -> float:
        return self.width / 2


@dataclass
class PlacedBox:
    box_id: int
    box_name: str
    x: float
    y: float
    length: float
    width: float
    weight: float
    cog_offset_x: float

    @property
    def cog_x_abs(self) -> float:
        return self.x + self.length / 2 + self.cog_offset_x

    @property
    def left_y(self) -> float:
        return self.y

    @property
    def right_y(self) -> float:
        return self.y + self.width

    @property
    def center_y(self) -> float:
        return self.y + self.width / 2


def calculate_axle_loads(
    trailer: TrailerSpec,
    boxes: List[PlacedBox]
) -> Tuple[float, float]:
    """
    计算前后轴荷（基于杠杆原理）
    设总重 W，重心距前轴距离 d，轴距 L
    前轴承重 = W * (L - d) / L
    后轴承重 = W * d / L
    其中 d 为重心到前轴的水平距离（向后为正）
    """
    total_weight = sum(b.weight for b in boxes)
    if total_weight <= 0.001:
        return 0.0, 0.0

    cog_x = sum(b.weight * b.cog_x_abs for b in boxes) / total_weight

    distance_from_front_axle = cog_x - trailer.front_axle_position
    wheelbase = trailer.wheelbase

    if wheelbase <= 0.001:
        return total_weight / 2, total_weight / 2

    rear_axle_load = total_weight * distance_from_front_axle / wheelbase
    front_axle_load = total_weight - rear_axle_load

    return front_axle_load, rear_axle_load


def calculate_left_right_weights(
    trailer: TrailerSpec,
    boxes: List[PlacedBox]
) -> Tuple[float, float]:
    """
    计算左右侧重量
    以拖车宽度中心线为界，按箱子在左右两侧的面积比例分配重量
    """
    center_y = trailer.platform_width / 2
    left_weight = 0.0
    right_weight = 0.0

    for box in boxes:
        box_left = box.y
        box_right = box.y + box.width
        box_area = box.width

        overlap_left = min(box_right, center_y) - max(box_left, 0)
        overlap_right = min(box_right, trailer.platform_width) - max(box_left, center_y)

        overlap_left = max(0.0, overlap_left)
        overlap_right = max(0.0, overlap_right)

        if box_area > 0.001:
            left_ratio = overlap_left / box_area
            right_ratio = overlap_right / box_area
        else:
            left_ratio = 0.5
            right_ratio = 0.5

        left_weight += box.weight * left_ratio
        right_weight += box.weight * right_ratio

    return left_weight, right_weight


def check_left_right_balance(
    trailer: TrailerSpec,
    boxes: List[PlacedBox],
    max_ratio: float = 0.15
) -> Tuple[bool, float, float, float]:
    """
    检查左右平衡
    返回: (是否在范围内, 左右偏差比例, 左侧重量, 右侧重量)
    """
    left_weight, right_weight = calculate_left_right_weights(trailer, boxes)
    total = left_weight + right_weight

    if total <= 0.001:
        return True, 0.0, 0.0, 0.0

    ratio = abs(left_weight - right_weight) / total
    within_limit = ratio <= max_ratio
    return within_limit, ratio, left_weight, right_weight


def check_axle_limits(
    trailer: TrailerSpec,
    front_load: float,
    rear_load: float
) -> Tuple[bool, float, float]:
    """
    检查轴荷是否在限制内
    负轴荷（轴承受拉力）也视为超限（有翻车风险）
    返回: (是否都在限制内, 前轴超限比例, 后轴超限比例)
    """
    front_over = max(0.0, front_load - trailer.front_axle_max_load) / max(trailer.front_axle_max_load, 0.001)
    rear_over = max(0.0, rear_load - trailer.rear_axle_max_load) / max(trailer.rear_axle_max_load, 0.001)

    front_under = max(0.0, -front_load) / max(trailer.front_axle_max_load, 0.001)
    rear_under = max(0.0, -rear_load) / max(trailer.rear_axle_max_load, 0.001)

    total_load = front_load + rear_load
    total_over = max(0.0, total_load - trailer.total_max_weight) / max(trailer.total_max_weight, 0.001)

    front_violation = max(front_over, front_under)
    rear_violation = max(rear_over, rear_under)

    overall_over = max(front_violation, rear_violation, total_over)
    within_limit = overall_over <= 0.001

    return within_limit, front_violation, rear_violation


def calculate_score(
    trailer: TrailerSpec,
    boxes: List[PlacedBox]
) -> float:
    """
    计算当前布局的综合评分（越低越好）
    评分因素：
    1. 轴荷均衡度（理想的50:50）
    2. 轴荷超限惩罚
    3. 左右平衡
    """
    front_load, rear_load = calculate_axle_loads(trailer, boxes)
    total_load = front_load + rear_load

    axle_within, front_over, rear_over = check_axle_limits(trailer, front_load, rear_load)

    total_over = max(0.0, total_load - trailer.total_max_weight) / max(trailer.total_max_weight, 0.001)

    if total_load > 0.001:
        front_ratio = front_load / total_load
        balance_score = abs(front_ratio - 0.5) * 2
    else:
        balance_score = 1.0

    lr_within, lr_ratio, _, _ = check_left_right_balance(trailer, boxes)

    over_penalty = (front_over + rear_over + total_over) * 100

    lr_penalty = lr_ratio * 10

    score = balance_score + over_penalty + lr_penalty

    return score


def _boxes_overlap_x(a: PlacedBox, b: PlacedBox) -> bool:
    """检查两个箱子在 x 方向是否重叠"""
    if a.x >= b.x + b.length - 0.001 or b.x >= a.x + a.length - 0.001:
        return False
    return True


def _boxes_overlap_y(a: PlacedBox, b: PlacedBox) -> bool:
    """检查两个箱子在 y 方向是否重叠"""
    if a.y >= b.y + b.width - 0.001 or b.y >= a.y + a.width - 0.001:
        return False
    return True


def _boxes_overlap(a: PlacedBox, b: PlacedBox) -> bool:
    """检查两个箱子是否重叠"""
    return _boxes_overlap_x(a, b) and _boxes_overlap_y(a, b)


def _is_valid_position(
    trailer: TrailerSpec,
    placed_boxes: List[PlacedBox],
    new_box: PlacedBox
) -> bool:
    """检查新箱子位置是否有效（不超出拖车边界，不与其他箱子重叠）"""
    if new_box.x < -0.001 or new_box.y < -0.001:
        return False
    if new_box.x + new_box.length > trailer.platform_length + 0.001:
        return False
    if new_box.y + new_box.width > trailer.platform_width + 0.001:
        return False

    for pb in placed_boxes:
        if _boxes_overlap(new_box, pb):
            return False

    return True


def _find_optimal_x_position(
    trailer: TrailerSpec,
    placed_boxes: List[PlacedBox],
    box_spec: BoxSpec,
    y_pos: float
) -> Tuple[float, float]:
    """
    对于给定的 y 位置，找到最佳的 x 位置
    使用贪心策略：尝试多个 x 位置，选择轴荷最均衡的
    """
    best_x = 0.0
    best_score = float('inf')

    test_box = PlacedBox(
        box_id=box_spec.box_id,
        box_name=box_spec.box_name,
        x=0,
        y=y_pos,
        length=box_spec.length,
        width=box_spec.width,
        weight=box_spec.weight,
        cog_offset_x=box_spec.cog_offset_x
    )

    x_step = max(50.0, box_spec.length / 20)

    x = 0.0
    while x + box_spec.length <= trailer.platform_length + 0.001:
        test_box.x = x

        if _is_valid_position(trailer, placed_boxes, test_box):
            temp_boxes = placed_boxes + [test_box]
            score = calculate_score(trailer, temp_boxes)

            if score < best_score:
                best_score = score
                best_x = x

        x += x_step

    return best_x, best_score


def _optimize_single_box_y(
    trailer: TrailerSpec,
    placed_boxes: List[PlacedBox],
    box_spec: BoxSpec
) -> Tuple[float, float, float]:
    """
    优化单个箱子的位置（y方向扫描，x方向优化）
    返回: (最佳x, 最佳y, 最佳评分)
    """
    best_x = 0.0
    best_y = 0.0
    best_score = float('inf')

    y_step = max(50.0, box_spec.width / 10)

    y = 0.0
    while y + box_spec.width <= trailer.platform_width + 0.001:
        x, score = _find_optimal_x_position(trailer, placed_boxes, box_spec, y)

        if score < best_score:
            best_score = score
            best_x = x
            best_y = y

        y += y_step

    return best_x, best_y, best_score


def optimize_box_positions(
    trailer: TrailerSpec,
    box_specs: List[BoxSpec]
) -> Dict:
    """
    多箱联合重心优化算法

    算法思路：
    1. 按重量从大到小排序（大箱子先放，影响更大）
    2. 逐个放置箱子，每个箱子都尝试找到最优位置
    3. 放置完成后进行局部优化（微调每个箱子的位置）
    4. 目标：前后轴荷都不超限且尽量均衡，左右偏差不超15%

    Args:
        trailer: 拖车参数
        box_specs: 待装载的箱子列表

    Returns:
        包含优化结果的字典
    """
    sorted_boxes = sorted(box_specs, key=lambda b: b.weight, reverse=True)

    placed_boxes: List[PlacedBox] = []

    for box_spec in sorted_boxes:
        best_x, best_y, best_score = _optimize_single_box_y(
            trailer, placed_boxes, box_spec
        )

        placed_box = PlacedBox(
            box_id=box_spec.box_id,
            box_name=box_spec.box_name,
            x=best_x,
            y=best_y,
            length=box_spec.length,
            width=box_spec.width,
            weight=box_spec.weight,
            cog_offset_x=box_spec.cog_offset_x
        )
        placed_boxes.append(placed_box)

    placed_boxes = _local_optimization(trailer, placed_boxes)

    front_load, rear_load = calculate_axle_loads(trailer, placed_boxes)
    total_weight = sum(b.weight for b in placed_boxes)

    if total_weight > 0.001:
        front_ratio = front_load / total_weight
        rear_ratio = rear_load / total_weight
    else:
        front_ratio = 0.5
        rear_ratio = 0.5

    axle_within, front_over, rear_over = check_axle_limits(trailer, front_load, rear_load)

    total_over = max(0.0, total_weight - trailer.total_max_weight) / max(trailer.total_max_weight, 0.001)
    overall_axle_ok = axle_within and total_over <= 0.001

    lr_within, lr_ratio, left_weight, right_weight = check_left_right_balance(trailer, placed_boxes)

    cog_x = sum(b.weight * b.cog_x_abs for b in placed_boxes) / max(total_weight, 0.001) if total_weight > 0 else 0
    cog_y = sum(b.weight * b.center_y for b in placed_boxes) / max(total_weight, 0.001) if total_weight > 0 else 0

    score = calculate_score(trailer, placed_boxes)

    recommendations = []
    if not overall_axle_ok:
        if front_over > 0:
            recommendations.append(f"前轴超载 {front_over*100:.1f}%")
        if rear_over > 0:
            recommendations.append(f"后轴超载 {rear_over*100:.1f}%")
        if total_over > 0:
            recommendations.append(f"总重超限 {total_over*100:.1f}%")
    if not lr_within:
        recommendations.append(f"左右偏差 {lr_ratio*100:.1f}%，超出15%限制")

    if not recommendations:
        if front_ratio > 0.55:
            recommendations.append("前轴偏重，建议将重物后移")
        elif front_ratio < 0.45:
            recommendations.append("后轴偏重，建议将重物前移")
        else:
            recommendations.append("轴荷分配良好")

    result_boxes = []
    for pb in placed_boxes:
        result_boxes.append({
            "box_id": pb.box_id,
            "box_name": pb.box_name,
            "x": pb.x,
            "y": pb.y,
            "length": pb.length,
            "width": pb.width,
            "weight": pb.weight,
            "cog_offset_x": pb.cog_offset_x
        })

    return {
        "total_boxes": len(placed_boxes),
        "total_weight": total_weight,
        "front_axle_load": front_load,
        "rear_axle_load": rear_load,
        "front_axle_load_ratio": front_ratio,
        "rear_axle_load_ratio": rear_ratio,
        "axles_within_limit": overall_axle_ok,
        "left_right_balance_ratio": lr_ratio,
        "left_right_within_limit": lr_within,
        "left_weight": left_weight,
        "right_weight": right_weight,
        "cog_x": cog_x,
        "cog_y": cog_y,
        "score": score,
        "recommendation": "；".join(recommendations) if recommendations else "装载方案优良",
        "loaded_boxes": result_boxes
    }


def _local_optimization(
    trailer: TrailerSpec,
    placed_boxes: List[PlacedBox],
    iterations: int = 3
) -> List[PlacedBox]:
    """
    局部优化：反复微调每个箱子的位置，尝试找到更优解
    """
    current_boxes = deepcopy(placed_boxes)
    current_score = calculate_score(trailer, current_boxes)

    for iteration in range(iterations):
        improved = False

        for i, box in enumerate(current_boxes):
            other_boxes = [b for j, b in enumerate(current_boxes) if j != i]

            box_spec = BoxSpec(
                box_id=box.box_id,
                box_name=box.box_name,
                length=box.length,
                width=box.width,
                weight=box.weight,
                cog_offset_x=box.cog_offset_x
            )

            new_x, new_y, new_score = _optimize_single_box_y(
                trailer, other_boxes, box_spec
            )

            if new_score < current_score - 0.001:
                current_boxes[i].x = new_x
                current_boxes[i].y = new_y
                current_score = new_score
                improved = True

        if not improved:
            break

    return current_boxes


def _get_dynamic_lr_limit(remaining_count: int, total_count: int, base_limit: float) -> float:
    """
    动态左右平衡限制：箱子少时适当放宽
    - 只剩1个箱子：物理上不可能平衡，完全放宽
    - 只剩2个箱子：放宽到 50%
    - 3-5个箱子：放宽到 30%
    - 5个以上：严格按 base_limit
    """
    if remaining_count <= 1:
        return 1.0
    elif remaining_count == 2:
        return min(0.5, 1.0)
    elif remaining_count <= 5:
        return min(base_limit * 2, 0.3)
    else:
        return base_limit


def generate_unload_sequence(
    trailer: TrailerSpec,
    loaded_boxes: List[PlacedBox],
    max_lr_ratio: float = 0.15
) -> Dict:
    """
    生成卸载顺序（反向思考：从满载开始，每次卸掉一个箱子）
    要求：任何中间状态轴荷不超限、左右偏差不超15%
    （箱子很少时动态放宽限制，因为物理上不可能完全平衡）

    策略：
    1. 每次选择一个箱子卸载，使得卸载后的状态仍然满足约束
    2. 优先卸载使得重心更均衡的箱子
    3. 如果没有安全的卸载选择，选一个影响最小的（记录警告）

    Args:
        trailer: 拖车参数
        loaded_boxes: 已装载的箱子
        max_lr_ratio: 最大左右偏差比例

    Returns:
        卸载序列信息
    """
    total_count = len(loaded_boxes)
    remaining_boxes = deepcopy(loaded_boxes)
    sequence = []
    step_num = 0
    all_steps_valid = True
    invalid_steps_count = 0

    while remaining_boxes:
        step_num += 1
        remaining_count = len(remaining_boxes)
        current_lr_limit = _get_dynamic_lr_limit(remaining_count, total_count, max_lr_ratio)

        best_idx = -1
        best_score = float('inf')
        best_valid = False

        for i, box in enumerate(remaining_boxes):
            after_boxes = [b for j, b in enumerate(remaining_boxes) if j != i]

            front_before, rear_before = calculate_axle_loads(trailer, remaining_boxes)
            front_after, rear_after = calculate_axle_loads(trailer, after_boxes)

            axle_within_before, _, _ = check_axle_limits(trailer, front_before, rear_before)
            axle_within_after, _, _ = check_axle_limits(trailer, front_after, rear_after)

            lr_within_before, lr_ratio_before, left_before, right_before = check_left_right_balance(
                trailer, remaining_boxes, current_lr_limit
            )
            lr_within_after, lr_ratio_after, _, _ = check_left_right_balance(
                trailer, after_boxes, current_lr_limit
            )

            valid_after = axle_within_after and lr_within_after

            score_after = calculate_score(trailer, after_boxes)

            candidate_score = score_after + (0 if valid_after else 100)

            if valid_after:
                if not best_valid or candidate_score < best_score:
                    best_score = candidate_score
                    best_idx = i
                    best_valid = True
            else:
                if not best_valid:
                    if candidate_score < best_score:
                        best_score = candidate_score
                        best_idx = i

        if best_idx < 0:
            break

        removed_box = remaining_boxes.pop(best_idx)

        front_before, rear_before = calculate_axle_loads(
            trailer, remaining_boxes + [removed_box]
        )
        front_after, rear_after = calculate_axle_loads(trailer, remaining_boxes)

        lr_within_before_base, lr_ratio_before_base, left_before, right_before = check_left_right_balance(
            trailer, remaining_boxes + [removed_box], max_lr_ratio
        )
        axle_within_before, _, _ = check_axle_limits(trailer, front_before, rear_before)

        boxes_before_count = len(remaining_boxes) + 1
        is_last_steps = boxes_before_count <= 1

        step_valid_base = (axle_within_before and lr_within_before_base) or is_last_steps
        if not step_valid_base:
            all_steps_valid = False
            invalid_steps_count += 1

        sequence.append({
            "step_number": step_num,
            "box_id": removed_box.box_id,
            "box_name": removed_box.box_name,
            "front_axle_load_before": front_before,
            "rear_axle_load_before": rear_before,
            "front_axle_load_after": front_after,
            "rear_axle_load_after": rear_after,
            "left_weight_before": left_before,
            "right_weight_before": right_before,
            "left_right_ratio_before": lr_ratio_before_base,
            "left_right_within_limit_before": lr_within_before_base,
            "axles_within_limit_before": axle_within_before,
            "dynamic_limit_used": current_lr_limit,
        })

    return {
        "sequence": sequence,
        "all_steps_valid": all_steps_valid,
        "invalid_steps_count": invalid_steps_count,
        "total_steps": len(sequence)
    }
