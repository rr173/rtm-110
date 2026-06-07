from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from copy import deepcopy


@dataclass
class CargoItem:
    idx: int
    cargo_id: int
    cargo_name: str
    x: float
    y: float
    z: float
    length: float
    width: float
    height: float
    weight: float

    @property
    def cx(self) -> float:
        return self.x + self.length / 2

    @property
    def cy(self) -> float:
        return self.y + self.width / 2

    @property
    def cz(self) -> float:
        return self.z + self.height / 2

    @property
    def volume(self) -> float:
        return self.length * self.width * self.height


def _projection_overlap_xy(a: CargoItem, b: CargoItem) -> bool:
    """检查两个货物在 x-y 平面上的投影是否有重叠"""
    if a.x >= b.x + b.length - 0.001 or b.x >= a.x + a.length - 0.001:
        return False
    if a.y >= b.y + b.width - 0.001 or b.y >= a.y + a.width - 0.001:
        return False
    return True


def _projection_overlap_xz(a: CargoItem, b: CargoItem) -> bool:
    """检查两个货物在 x-z 平面上的投影是否有重叠（从箱门方向看的投影）"""
    if a.x >= b.x + b.length - 0.001 or b.x >= a.x + a.length - 0.001:
        return False
    if a.z >= b.z + b.height - 0.001 or b.z >= a.z + a.height - 0.001:
        return False
    return True


def _projection_overlap_yz(a: CargoItem, b: CargoItem) -> bool:
    """检查两个货物在 y-z 平面上的投影是否有重叠"""
    if a.y >= b.y + b.width - 0.001 or b.y >= a.y + a.width - 0.001:
        return False
    if a.z >= b.z + b.height - 0.001 or b.z >= a.z + a.height - 0.001:
        return False
    return True


def _is_supported_by(cargo: CargoItem, supporter: CargoItem) -> bool:
    """检查 cargo 是否被 supporter 直接支撑（在下方）"""
    if abs((cargo.z) - (supporter.z + supporter.height)) > 0.001:
        return False
    return _projection_overlap_xy(cargo, supporter)


def _blocks_entry_path(blocker: CargoItem, blocked: CargoItem, container_width: float) -> bool:
    """
    检查 blocker 是否挡住了 blocked 的入箱路径
    箱门在 y = container_width 一侧，货物从 y 大的一侧进入，向 y 小的方向移动
    
    规则：
    1. blocker 在 blocked 更靠近箱门的一侧（blocker.y + blocker.width > blocked.y + blocked.width）
       或者说 blocker 的 y 范围有一部分在 blocked 的 y 范围的外侧（更大的 y 值）
    2. 两者在 x-z 平面上的投影有重叠
    """
    blocker_front = blocker.y + blocker.width
    blocked_front = blocked.y + blocked.width

    if blocker_front <= blocked_front + 0.001:
        return False

    if not _projection_overlap_xz(blocker, blocked):
        return False

    return True


def build_dependency_graph(
    cargos: List[CargoItem],
    container_width: float
) -> Dict[int, List[int]]:
    """
    构建依赖关系图
    返回：key 是货物 idx，value 是该货物依赖的货物 idx 列表（这些货物必须先放）
    
    依赖规则：
    1. 支撑依赖：被支撑的货物依赖于支撑它的货物（支撑货物必须先放）
    2. 入箱路径依赖：被挡住的货物依赖于挡住它的货物（挡住的货物必须后放？不对...
    
    重新思考：
    - 如果 A 挡住了 B 的入箱路径（A 在 B 前面，更靠近箱门），那么 B 必须在 A 之前放入
      因为 B 放入时，A 还不在那里挡路
    - 如果 B 在 A 的上面（A 支撑 B），那么 A 必须在 B 之前放入
    
    所以：
    - dependencies[B] 包含 A 表示：B 依赖于 A，即 A 必须先于 B 放入
    """
    dependencies: Dict[int, List[int]] = {c.idx: [] for c in cargos}

    for i, cargo_i in enumerate(cargos):
        for j, cargo_j in enumerate(cargos):
            if i == j:
                continue

            if _is_supported_by(cargo_i, cargo_j):
                if cargo_j.idx not in dependencies[cargo_i.idx]:
                    dependencies[cargo_i.idx].append(cargo_j.idx)

            if _blocks_entry_path(cargo_i, cargo_j, container_width):
                if cargo_i.idx not in dependencies[cargo_j.idx]:
                    dependencies[cargo_j.idx].append(cargo_i.idx)

    return dependencies


def calculate_cog(placed: List[CargoItem]) -> Tuple[float, float, float]:
    """计算已放置货物的重心"""
    total_weight = sum(c.weight for c in placed)
    if total_weight <= 0.001:
        return (0, 0, 0)

    cx = sum(c.weight * c.cx for c in placed) / total_weight
    cy = sum(c.weight * c.cy for c in placed) / total_weight
    cz = sum(c.weight * c.cz for c in placed) / total_weight

    return (cx, cy, cz)


def check_cog_limit(
    placed: List[CargoItem],
    container_length: float,
    container_width: float,
    max_offset_ratio: float = 0.20
) -> Tuple[bool, float, float]:
    """
    检查重心偏移是否在限制范围内
    返回：(是否在范围内, x方向偏移比例, y方向偏移比例)
    """
    if not placed:
        return (True, 0.0, 0.0)

    cog_x, cog_y, _ = calculate_cog(placed)
    center_x = container_length / 2
    center_y = container_width / 2

    offset_x_ratio = abs(cog_x - center_x) / container_length
    offset_y_ratio = abs(cog_y - center_y) / container_width

    within_limit = offset_x_ratio <= max_offset_ratio and offset_y_ratio <= max_offset_ratio
    return (within_limit, offset_x_ratio, offset_y_ratio)


def _get_dynamic_cog_limit(placed_count: int, total_count: int, base_limit: float) -> float:
    """
    动态重心限制：前几件适当放宽，逐渐收紧
    - 前3件：完全不限制（先装进去再说，物理上单个货不可能满足20%）
    - 3-5件：放宽到 2 * base_limit
    - 5-10件：放宽到 1.5 * base_limit
    - 10件以上：严格按 base_limit
    """
    if placed_count < 3:
        return 1.0
    elif placed_count < 5:
        return min(base_limit * 2.0, 1.0)
    elif placed_count < 10:
        return min(base_limit * 1.5, 1.0)
    else:
        return base_limit


def generate_packing_sequence(
    container_length: float,
    container_width: float,
    container_height: float,
    placed_cargos: List[dict],
    max_cog_offset_ratio: float = 0.20
) -> Dict:
    """
    生成物理可行的装箱操作序列
    
    算法思路：
    1. 将所有已放置货物转换为 CargoItem
    2. 构建依赖关系图（支撑关系 + 入箱路径遮挡关系）
    3. 使用贪心策略选择每一步放入的货物：
       - 只选择所有依赖都已满足的货物
       - 优先选择满足当前动态重心限制的货物
       - 在可选货物中选择使得新增后重心偏移最小的
       - 重心偏移相同时，选择体积大的先放（更稳定）
    
    物理约束：
    - 入箱路径：从箱门方向看，后放的货不能被先放的挡住入箱路径
    - 支撑关系：下面的货必须先放
    - 重心偏移：任何中间状态重心偏移不超过限制（动态放宽策略）
    
    Args:
        container_length: 集装箱长度
        container_width: 集装箱宽度  
        container_height: 集装箱高度
        placed_cargos: 已放置货物列表（从方案中读取）
        max_cog_offset_ratio: 最大重心偏移比例（默认20%）
    
    Returns:
        包含序列信息的字典
    """
    cargos = []
    for idx, cargo_dict in enumerate(placed_cargos):
        cargos.append(CargoItem(
            idx=idx,
            cargo_id=cargo_dict["cargo_id"],
            cargo_name=cargo_dict["cargo_name"],
            x=cargo_dict["x"],
            y=cargo_dict["y"],
            z=cargo_dict["z"],
            length=cargo_dict["length"],
            width=cargo_dict["width"],
            height=cargo_dict["height"],
            weight=cargo_dict["weight"]
        ))

    dependencies = build_dependency_graph(cargos, container_width)

    remaining = set(c.idx for c in cargos)
    placed_set = set()
    sequence = []
    placed_cargos_list: List[CargoItem] = []

    total_count = len(cargos)
    step = 0

    while remaining:
        step += 1

        candidates = []
        for idx in remaining:
            deps = dependencies[idx]
            if all(d in placed_set for d in deps):
                candidates.append(idx)

        if not candidates:
            remaining_list = list(remaining)
            fallback_idx = remaining_list[0]
            candidates = [fallback_idx]

        current_limit = _get_dynamic_cog_limit(len(placed_cargos_list), total_count, max_cog_offset_ratio)

        feasible_candidates = []
        infeasible_candidates = []

        for idx in candidates:
            cargo = next(c for c in cargos if c.idx == idx)
            temp_placed = placed_cargos_list + [cargo]

            within_limit, offset_x, offset_y = check_cog_limit(
                temp_placed, container_length, container_width, current_limit
            )

            cog_score = offset_x + offset_y
            volume_score = -cargo.volume / 1000000

            score = cog_score * 1000 + volume_score

            if within_limit:
                feasible_candidates.append((idx, score, offset_x, offset_y))
            else:
                infeasible_candidates.append((idx, score, offset_x, offset_y))

        if feasible_candidates:
            feasible_candidates.sort(key=lambda x: x[1])
            best_idx = feasible_candidates[0][0]
            best_offset_x = feasible_candidates[0][2]
            best_offset_y = feasible_candidates[0][3]
        else:
            infeasible_candidates.sort(key=lambda x: x[1])
            best_idx = infeasible_candidates[0][0]
            best_offset_x = infeasible_candidates[0][2]
            best_offset_y = infeasible_candidates[0][3]

        cargo = next(c for c in cargos if c.idx == best_idx)
        placed_cargos_list.append(cargo)
        placed_set.add(best_idx)
        remaining.remove(best_idx)

        cog_x, cog_y, cog_z = calculate_cog(placed_cargos_list)

        within_final_limit, final_offset_x, final_offset_y = check_cog_limit(
            placed_cargos_list, container_length, container_width, max_cog_offset_ratio
        )

        sequence.append({
            "step": step,
            "cargo_idx": best_idx,
            "cargo_id": cargo.cargo_id,
            "cargo_name": cargo.cargo_name,
            "position": {
                "x": cargo.x,
                "y": cargo.y,
                "z": cargo.z
            },
            "dimensions": {
                "length": cargo.length,
                "width": cargo.width,
                "height": cargo.height
            },
            "weight": cargo.weight,
            "cog_after": {
                "x": cog_x,
                "y": cog_y,
                "z": cog_z
            },
            "cog_offset_x_ratio": final_offset_x,
            "cog_offset_y_ratio": final_offset_y,
            "cog_within_limit": within_final_limit,
            "dynamic_limit_used": current_limit
        })

    all_placed = len(sequence) == len(cargos)

    final_cog_x, final_cog_y, final_cog_z = calculate_cog(placed_cargos_list)
    final_within, final_offset_x, final_offset_y = check_cog_limit(
        placed_cargos_list, container_length, container_width, max_cog_offset_ratio
    )

    all_steps_within_limit = all(s["cog_within_limit"] for s in sequence)

    return {
        "total_steps": len(sequence),
        "cargo_count": len(cargos),
        "all_placed": all_placed,
        "all_steps_within_limit": all_steps_within_limit,
        "max_cog_offset_ratio": max_cog_offset_ratio,
        "final_cog": {
            "x": final_cog_x,
            "y": final_cog_y,
            "z": final_cog_z
        },
        "final_cog_within_limit": final_within,
        "final_cog_offset_x_ratio": final_offset_x,
        "final_cog_offset_y_ratio": final_offset_y,
        "sequence": sequence
    }


def get_step_snapshot(
    container_length: float,
    container_width: float,
    container_height: float,
    placed_cargos: List[dict],
    sequence_result: Dict,
    step_number: int
) -> Dict:
    """
    获取第 N 步的装箱快照
    
    Args:
        container_length: 集装箱长度
        container_width: 集装箱宽度
        container_height: 集装箱高度
        placed_cargos: 所有已放置货物（完整列表）
        sequence_result: generate_packing_sequence 的结果
        step_number: 步数（从 1 开始，0 表示空箱）
    
    Returns:
        快照信息
    """
    sequence = sequence_result["sequence"]
    total_steps = sequence_result["total_steps"]

    if step_number < 0:
        step_number = 0
    if step_number > total_steps:
        step_number = total_steps

    if step_number == 0:
        return {
            "step": 0,
            "total_steps": total_steps,
            "placed_count": 0,
            "placed_cargos": [],
            "cog": {"x": 0, "y": 0, "z": 0},
            "cog_within_limit": True,
            "cog_offset_x_ratio": 0.0,
            "cog_offset_y_ratio": 0.0,
            "last_placed": None
        }

    placed_indices = set()
    for i in range(step_number):
        placed_indices.add(sequence[i]["cargo_idx"])

    placed_list = [c for idx, c in enumerate(placed_cargos) if idx in placed_indices]

    step_info = sequence[step_number - 1]

    return {
        "step": step_number,
        "total_steps": total_steps,
        "placed_count": step_number,
        "placed_cargos": placed_list,
        "cog": step_info["cog_after"],
        "cog_within_limit": step_info["cog_within_limit"],
        "cog_offset_x_ratio": step_info["cog_offset_x_ratio"],
        "cog_offset_y_ratio": step_info["cog_offset_y_ratio"],
        "last_placed": {
            "cargo_idx": step_info["cargo_idx"],
            "cargo_id": step_info["cargo_id"],
            "cargo_name": step_info["cargo_name"],
            "position": step_info["position"],
            "dimensions": step_info["dimensions"],
            "weight": step_info["weight"]
        }
    }
