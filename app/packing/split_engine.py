from typing import List, Dict, Tuple
from dataclasses import dataclass, field
from copy import deepcopy
from collections import defaultdict

from app.packing.algorithm import Box, pack_boxes


@dataclass
class ContainerSpec:
    id: int
    name: str
    length: float
    width: float
    height: float
    max_weight: float

    @property
    def volume(self) -> float:
        return self.length * self.width * self.height

    def can_fit_single(self, box: Box) -> bool:
        orientations = []
        l, w, h = box.length, box.width, box.height
        orientations.append((l, w, h))
        if box.can_rotate_horizontal:
            orientations.append((w, l, h))
        if box.can_flip:
            orientations.append((l, h, w))
            orientations.append((w, h, l))
            if box.can_rotate_horizontal:
                orientations.append((h, l, w))
                orientations.append((h, w, l))

        for bl, bw, bh in orientations:
            if (bl <= self.length + 0.001 and
                    bw <= self.width + 0.001 and
                    bh <= self.height + 0.001 and
                    box.weight <= self.max_weight + 0.001):
                return True
        return False


@dataclass
class AllocatedBox:
    box_index: int
    container_spec: ContainerSpec
    boxes: List[Box] = field(default_factory=list)

    @property
    def total_volume(self) -> float:
        return sum(b.length * b.width * b.height for b in self.boxes)

    @property
    def total_weight(self) -> float:
        return sum(b.weight for b in self.boxes)

    @property
    def volume_utilization(self) -> float:
        if self.container_spec.volume <= 0:
            return 0.0
        return self.total_volume / self.container_spec.volume

    def can_fit_estimated(self, box: Box) -> bool:
        if self.total_weight + box.weight > self.container_spec.max_weight + 0.001:
            return False

        box_volume = box.length * box.width * box.height
        if self.total_volume + box_volume > self.container_spec.volume + 0.001:
            return False

        return True


def _sort_boxes_by_volume(boxes: List[Box], reverse: bool = True) -> List[Box]:
    return sorted(boxes, key=lambda b: b.length * b.width * b.height, reverse=reverse)


def _select_container_for_box(box: Box, containers: List[ContainerSpec],
                              prefer_larger: bool = False) -> ContainerSpec:
    fitting = []
    for c in containers:
        if c.can_fit_single(box):
            fitting.append(c)

    if not fitting:
        return max(containers, key=lambda c: c.volume)

    if prefer_larger:
        return max(fitting, key=lambda c: c.volume)
    else:
        return min(fitting, key=lambda c: c.volume)


def _first_fit_decreasing(
        boxes: List[Box],
        containers: List[ContainerSpec],
        prefer_larger_container: bool = False
) -> List[AllocatedBox]:
    sorted_boxes = _sort_boxes_by_volume(boxes, reverse=True)

    allocated: List[AllocatedBox] = []
    box_index_counter = 0

    for box in sorted_boxes:
        best_box = None
        best_fit_score = -1.0

        for ab in allocated:
            if not ab.can_fit_estimated(box):
                continue

            new_util = (ab.total_volume + box.length * box.width * box.height) / ab.container_spec.volume
            if new_util > best_fit_score:
                best_fit_score = new_util
                best_box = ab

        if best_box is not None:
            best_box.boxes.append(box)
        else:
            container = _select_container_for_box(box, containers, prefer_larger=prefer_larger_container)
            new_box = AllocatedBox(
                box_index=box_index_counter,
                container_spec=container,
                boxes=[box]
            )
            allocated.append(new_box)
            box_index_counter += 1

    return allocated


def _verify_and_adjust(
        allocated: List[AllocatedBox]
) -> Tuple[List[AllocatedBox], List[Box]]:
    verified_boxes: List[AllocatedBox] = []
    leftover_boxes: List[Box] = []

    for ab in allocated:
        result = pack_boxes(
            container_length=ab.container_spec.length,
            container_width=ab.container_spec.width,
            container_height=ab.container_spec.height,
            container_max_weight=ab.container_spec.max_weight,
            boxes=ab.boxes
        )

        placed_count_by_id = defaultdict(int)
        for pc in result["placed_cargos"]:
            placed_count_by_id[pc["cargo_id"]] += 1

        placed_boxes = []
        unplaced_boxes = []
        temp_count_by_id = defaultdict(int)

        for box in ab.boxes:
            cid = box.cargo_id
            if temp_count_by_id[cid] < placed_count_by_id.get(cid, 0):
                placed_boxes.append(box)
                temp_count_by_id[cid] += 1
            else:
                unplaced_boxes.append(box)

        verified_box = AllocatedBox(
            box_index=ab.box_index,
            container_spec=ab.container_spec,
            boxes=placed_boxes
        )
        verified_boxes.append(verified_box)
        leftover_boxes.extend(unplaced_boxes)

    return verified_boxes, leftover_boxes


def _balance_utilization(allocated: List[AllocatedBox]) -> List[AllocatedBox]:
    if len(allocated) <= 1:
        return allocated

    improved = True
    max_iterations = 20
    iteration = 0

    while improved and iteration < max_iterations:
        improved = False
        iteration += 1

        sorted_ab = sorted(allocated, key=lambda ab: ab.volume_utilization)
        lowest = sorted_ab[0]
        highest = sorted_ab[-1]

        if highest.volume_utilization - lowest.volume_utilization < 0.05:
            break

        for i in range(len(highest.boxes) - 1, -1, -1):
            box = highest.boxes[i]
            box_vol = box.length * box.width * box.height

            if not lowest.can_fit_estimated(box):
                continue

            new_lowest_vol = lowest.total_volume + box_vol
            new_highest_vol = highest.total_volume - box_vol

            old_diff = highest.volume_utilization - lowest.volume_utilization
            new_lowest_util = new_lowest_vol / lowest.container_spec.volume
            new_highest_util = new_highest_vol / highest.container_spec.volume
            new_diff = abs(new_highest_util - new_lowest_util)

            if new_diff < old_diff - 0.01:
                moved_box = highest.boxes.pop(i)
                lowest.boxes.append(moved_box)
                improved = True
                break

    return allocated


def split_cargos_into_boxes(
        boxes: List[Box],
        containers: List[ContainerSpec],
        max_iterations: int = 5
) -> Dict:
    if not boxes:
        return {
            "total_boxes": 0,
            "total_cargos": 0,
            "placed_cargos_count": 0,
            "unplaced_cargos": [],
            "total_weight": 0.0,
            "average_volume_utilization": 0.0,
            "container_usage": [],
            "boxes": [],
            "recommendation": "无货物需要装箱"
        }

    if not containers:
        return {
            "total_boxes": 0,
            "total_cargos": len(boxes),
            "placed_cargos_count": 0,
            "unplaced_cargos": [
                {"cargo_id": b.cargo_id, "cargo_name": b.cargo_name, "reason": "无可用箱型"}
                for b in boxes
            ],
            "total_weight": 0.0,
            "average_volume_utilization": 0.0,
            "container_usage": [],
            "boxes": [],
            "recommendation": "没有可用的箱型"
        }

    remaining_boxes = deepcopy(boxes)
    all_allocated: List[AllocatedBox] = []

    iteration = 0
    while remaining_boxes and iteration < max_iterations:
        iteration += 1

        prefer_larger = (iteration % 2 == 1)
        allocated = _first_fit_decreasing(remaining_boxes, containers, prefer_larger)

        verified, leftover = _verify_and_adjust(allocated)

        all_allocated.extend(verified)
        remaining_boxes = leftover

    all_allocated = [ab for ab in all_allocated if ab.boxes]

    for idx, ab in enumerate(all_allocated):
        ab.box_index = idx

    all_allocated = _balance_utilization(all_allocated)

    for idx, ab in enumerate(all_allocated):
        ab.box_index = idx

    final_boxes = []
    total_placed = 0
    total_weight = 0.0
    total_utilization = 0.0
    container_count: Dict[int, int] = {}
    all_unplaced: List[Box] = []

    for ab in all_allocated:
        result = pack_boxes(
            container_length=ab.container_spec.length,
            container_width=ab.container_spec.width,
            container_height=ab.container_spec.height,
            container_max_weight=ab.container_spec.max_weight,
            boxes=ab.boxes
        )

        placed_cargos = result["placed_cargos"]

        placed_count_by_id = defaultdict(int)
        for pc in placed_cargos:
            placed_count_by_id[pc["cargo_id"]] += 1

        temp_count_by_id = defaultdict(int)
        for box in ab.boxes:
            cid = box.cargo_id
            if temp_count_by_id[cid] < placed_count_by_id.get(cid, 0):
                temp_count_by_id[cid] += 1
            else:
                all_unplaced.append(box)

        box_plan = {
            "box_index": ab.box_index,
            "container_id": ab.container_spec.id,
            "container_name": ab.container_spec.name,
            "container_length": ab.container_spec.length,
            "container_width": ab.container_spec.width,
            "container_height": ab.container_spec.height,
            "placed_cargos": placed_cargos,
            "placed_count": len(placed_cargos),
            "total_weight": result["total_weight"],
            "volume_utilization": result["volume_utilization"],
            "center_of_gravity": result["center_of_gravity"],
            "cog_within_limit": result["cog_within_limit"],
            "cog_offset_x_ratio": result["cog_offset_x_ratio"],
            "cog_offset_y_ratio": result["cog_offset_y_ratio"],
        }
        final_boxes.append(box_plan)

        total_placed += len(placed_cargos)
        total_weight += result["total_weight"]
        total_utilization += result["volume_utilization"]

        cid = ab.container_spec.id
        container_count[cid] = container_count.get(cid, 0) + 1

    all_unplaced.extend(remaining_boxes)

    unplaced_final = []
    seen_unplaced = set()
    for b in all_unplaced:
        key = (b.cargo_id, b.cargo_name)
        if key not in seen_unplaced:
            seen_unplaced.add(key)
            unplaced_final.append({
                "cargo_id": b.cargo_id,
                "cargo_name": b.cargo_name,
                "reason": "无法装入任何箱型"
            })

    container_usage = []
    for c in containers:
        cnt = container_count.get(c.id, 0)
        if cnt > 0:
            container_usage.append({
                "container_id": c.id,
                "container_name": c.name,
                "count": cnt
            })

    avg_util = total_utilization / len(final_boxes) if final_boxes else 0.0

    if not unplaced_final:
        recommendation = f"共使用 {len(final_boxes)} 个箱子，平均体积利用率 {avg_util * 100:.1f}%，总重量 {total_weight:.1f}kg"
    else:
        recommendation = f"共使用 {len(final_boxes)} 个箱子，还有 {len(unplaced_final)} 种货物未能全部装入"

    return {
        "total_boxes": len(final_boxes),
        "total_cargos": len(boxes),
        "placed_cargos_count": total_placed,
        "unplaced_cargos": unplaced_final,
        "total_weight": total_weight,
        "average_volume_utilization": avg_util,
        "container_usage": container_usage,
        "boxes": final_boxes,
        "recommendation": recommendation
    }
