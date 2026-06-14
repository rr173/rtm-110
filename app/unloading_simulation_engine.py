from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class CargoState:
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
    stop_order: int
    unload_order: int
    is_removed: bool = False
    is_temporary_out: bool = False

    @property
    def x_max(self) -> float:
        return self.x + self.length

    @property
    def y_max(self) -> float:
        return self.y + self.width

    @property
    def z_max(self) -> float:
        return self.z + self.height


@dataclass
class SimulationMove:
    move_type: str
    packed_cargo_id: int
    cargo_id: int
    cargo_name: str
    stop_order: int
    move_sequence: int
    reason: Optional[str] = None


@dataclass
class StopSimulationResult:
    stop_id: int
    stop_order: int
    stop_name: str
    rehandle_count: int = 0
    unload_count: int = 0
    remaining_count: int = 0
    has_deadlock: bool = False
    deadlock_cargo_ids: List[int] = field(default_factory=list)
    moves: List[SimulationMove] = field(default_factory=list)
    remaining_cargos_state: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SimulationResult:
    total_stops: int
    total_cargos: int
    total_rehandle_count: int = 0
    worst_stop_order: Optional[int] = None
    worst_stop_rehandle_count: int = 0
    has_deadlock: bool = False
    deadlock_stop_order: Optional[int] = None
    deadlock_cargo_ids: List[int] = field(default_factory=list)
    poorly_stacked_cargo_ids: List[int] = field(default_factory=list)
    stop_results: List[StopSimulationResult] = field(default_factory=list)


def _boxes_overlap_xy(a: CargoState, b: CargoState) -> bool:
    x_overlap = not (a.x_max <= b.x or b.x_max <= a.x)
    y_overlap = not (a.y_max <= b.y or b.y_max <= a.y)
    return x_overlap and y_overlap


def _is_blocking(blocker: CargoState, target: CargoState) -> bool:
    if blocker.is_removed or blocker.is_temporary_out:
        return False
    if target.is_removed or target.is_temporary_out:
        return False
    if blocker.stop_order <= target.stop_order:
        return False
    if not _boxes_overlap_xy(blocker, target):
        return False
    return blocker.z > target.z


def _find_blocking_cargos(
    target: CargoState,
    all_cargos: List[CargoState]
) -> List[CargoState]:
    blockers = []
    for cargo in all_cargos:
        if cargo.packed_cargo_id == target.packed_cargo_id:
            continue
        if _is_blocking(cargo, target):
            blockers.append(cargo)
    return blockers


def _find_accessible_cargos_for_stop(
    stop_order: int,
    all_cargos: List[CargoState]
) -> List[CargoState]:
    accessible = []
    for cargo in all_cargos:
        if cargo.is_removed or cargo.is_temporary_out:
            continue
        if cargo.stop_order != stop_order:
            continue
        blockers = _find_blocking_cargos(cargo, all_cargos)
        if not blockers:
            accessible.append(cargo)
    return accessible


def _is_any_blocking(blocker: CargoState, target: CargoState) -> bool:
    if blocker.is_removed or blocker.is_temporary_out:
        return False
    if target.is_removed or target.is_temporary_out:
        return False
    if not _boxes_overlap_xy(blocker, target):
        return False
    return blocker.z > target.z


def _find_any_blocking_cargos(
    target: CargoState,
    all_cargos: List[CargoState]
) -> List[CargoState]:
    blockers = []
    for cargo in all_cargos:
        if cargo.packed_cargo_id == target.packed_cargo_id:
            continue
        if _is_any_blocking(cargo, target):
            blockers.append(cargo)
    return blockers


def _check_deadlock(
    remaining_cargos: List[CargoState],
    current_stop_order: int
) -> Tuple[bool, List[int]]:
    future_cargos = [
        c for c in remaining_cargos
        if not c.is_removed and c.stop_order > current_stop_order
    ]

    if not future_cargos:
        return False, []

    deadlock_cargo_ids = []
    for cargo in future_cargos:
        blockers = _find_any_blocking_cargos(cargo, remaining_cargos)
        if not blockers:
            continue
        has_overdue_blocker = any(
            b.stop_order <= current_stop_order for b in blockers
        )
        if has_overdue_blocker:
            deadlock_cargo_ids.append(cargo.packed_cargo_id)
            continue
        all_blockers_later = all(b.stop_order > cargo.stop_order for b in blockers)
        if all_blockers_later:
            has_chain = False
            for blocker in blockers:
                blocker_blockers = _find_any_blocking_cargos(blocker, remaining_cargos)
                if blocker_blockers:
                    blocker_all_later = all(bb.stop_order > blocker.stop_order for bb in blocker_blockers)
                    if blocker_all_later:
                        has_chain = True
                        break
            if has_chain:
                deadlock_cargo_ids.append(cargo.packed_cargo_id)

    if deadlock_cargo_ids:
        return True, deadlock_cargo_ids
    return False, []


def _identify_poorly_stacked_cargos(
    all_cargos: List[CargoState]
) -> List[int]:
    poorly_stacked = []
    for later_cargo in all_cargos:
        for earlier_cargo in all_cargos:
            if earlier_cargo.stop_order >= later_cargo.stop_order:
                continue
            if _boxes_overlap_xy(earlier_cargo, later_cargo) and earlier_cargo.z < later_cargo.z:
                if later_cargo.packed_cargo_id not in poorly_stacked:
                    poorly_stacked.append(later_cargo.packed_cargo_id)
                break
    return poorly_stacked


def run_unloading_simulation(
    packed_cargos: List[Dict[str, Any]],
    stops: List[Dict[str, Any]],
    cargo_assignments: List[Dict[str, Any]]
) -> SimulationResult:
    stop_map = {s["stop_order"]: s for s in stops}
    assignment_map = {
        a["packed_cargo_id"]: a for a in cargo_assignments
    }

    cargo_states: List[CargoState] = []
    for pc in packed_cargos:
        packed_id = pc["id"] if isinstance(pc, dict) and "id" in pc else pc.id
        assignment = assignment_map.get(packed_id)
        if not assignment:
            continue

        cargo_states.append(CargoState(
            packed_cargo_id=packed_id,
            cargo_id=pc["cargo_id"] if isinstance(pc, dict) else pc.cargo_id,
            cargo_name=pc["cargo_name"] if isinstance(pc, dict) else pc.cargo_name,
            x=pc["x"] if isinstance(pc, dict) else pc.x,
            y=pc["y"] if isinstance(pc, dict) else pc.y,
            z=pc["z"] if isinstance(pc, dict) else pc.z,
            length=pc["length"] if isinstance(pc, dict) else pc.length,
            width=pc["width"] if isinstance(pc, dict) else pc.width,
            height=pc["height"] if isinstance(pc, dict) else pc.height,
            weight=pc["weight"] if isinstance(pc, dict) else pc.weight,
            stop_order=assignment["stop_order"],
            unload_order=assignment["unload_order"]
        ))

    total_cargos = len(cargo_states)
    total_stops = len(stops)
    total_rehandle_count = 0
    worst_stop_order = None
    worst_stop_rehandle_count = 0
    has_deadlock = False
    deadlock_stop_order = None
    deadlock_cargo_ids = []
    stop_results: List[StopSimulationResult] = []

    poorly_stacked = _identify_poorly_stacked_cargos(cargo_states)

    sorted_stops = sorted(stops, key=lambda s: s["stop_order"])
    move_sequence = 0

    for stop in sorted_stops:
        stop_order = stop["stop_order"]
        stop_id = stop["id"] if "id" in stop else None
        stop_name = stop["stop_name"]

        stop_result = StopSimulationResult(
            stop_id=stop_id,
            stop_order=stop_order,
            stop_name=stop_name
        )

        stop_cargos = [
            c for c in cargo_states
            if c.stop_order == stop_order and not c.is_removed
        ]
        stop_cargos.sort(key=lambda c: c.unload_order)

        rehandle_count = 0
        unload_count = 0

        for target_cargo in stop_cargos:
            if target_cargo.is_removed:
                continue

            while True:
                accessible = _find_accessible_cargos_for_stop(stop_order, cargo_states)
                accessible_ids = {c.packed_cargo_id for c in accessible}

                if target_cargo.packed_cargo_id in accessible_ids:
                    break

                blockers = _find_blocking_cargos(target_cargo, cargo_states)
                if not blockers:
                    break

                blockers.sort(key=lambda b: (b.z, b.stop_order), reverse=True)
                rehandle_candidate = blockers[0]

                move_sequence += 1
                rehandle_count += 1
                stop_result.moves.append(SimulationMove(
                    move_type="rehandle_out",
                    packed_cargo_id=rehandle_candidate.packed_cargo_id,
                    cargo_id=rehandle_candidate.cargo_id,
                    cargo_name=rehandle_candidate.cargo_name,
                    stop_order=stop_order,
                    move_sequence=move_sequence,
                    reason=f"挡住了{target_cargo.cargo_name}(ID:{target_cargo.cargo_id})，临时搬出"
                ))
                rehandle_candidate.is_temporary_out = True

            move_sequence += 1
            unload_count += 1
            target_cargo.is_removed = True
            stop_result.moves.append(SimulationMove(
                move_type="unload",
                packed_cargo_id=target_cargo.packed_cargo_id,
                cargo_id=target_cargo.cargo_id,
                cargo_name=target_cargo.cargo_name,
                stop_order=stop_order,
                move_sequence=move_sequence,
                reason="本站点卸货"
            ))

        temp_out_cargos = [c for c in cargo_states if c.is_temporary_out]
        for temp_cargo in temp_out_cargos:
            move_sequence += 1
            rehandle_count += 1
            stop_result.moves.append(SimulationMove(
                move_type="rehandle_in",
                packed_cargo_id=temp_cargo.packed_cargo_id,
                cargo_id=temp_cargo.cargo_id,
                cargo_name=temp_cargo.cargo_name,
                stop_order=stop_order,
                move_sequence=move_sequence,
                reason="卸货完成，将临时搬出的货物放回箱内"
            ))
            temp_cargo.is_temporary_out = False

        remaining = [c for c in cargo_states if not c.is_removed]
        stop_result.rehandle_count = rehandle_count
        stop_result.unload_count = unload_count
        stop_result.remaining_count = len(remaining)

        remaining_state = []
        for c in remaining:
            remaining_state.append({
                "packed_cargo_id": c.packed_cargo_id,
                "cargo_id": c.cargo_id,
                "cargo_name": c.cargo_name,
                "stop_order": c.stop_order,
                "x": c.x,
                "y": c.y,
                "z": c.z,
                "length": c.length,
                "width": c.width,
                "height": c.height,
                "weight": c.weight
            })
        stop_result.remaining_cargos_state = remaining_state

        deadlock, deadlock_ids = _check_deadlock(cargo_states, stop_order)
        if deadlock:
            stop_result.has_deadlock = True
            stop_result.deadlock_cargo_ids = deadlock_ids
            if not has_deadlock:
                has_deadlock = True
                deadlock_stop_order = stop_order
                deadlock_cargo_ids = deadlock_ids

        stop_results.append(stop_result)

        total_rehandle_count += rehandle_count
        if rehandle_count > worst_stop_rehandle_count:
            worst_stop_rehandle_count = rehandle_count
            worst_stop_order = stop_order

        if has_deadlock:
            break

    result = SimulationResult(
        total_stops=total_stops,
        total_cargos=total_cargos,
        total_rehandle_count=total_rehandle_count,
        worst_stop_order=worst_stop_order,
        worst_stop_rehandle_count=worst_stop_rehandle_count,
        has_deadlock=has_deadlock,
        deadlock_stop_order=deadlock_stop_order,
        deadlock_cargo_ids=deadlock_cargo_ids,
        poorly_stacked_cargo_ids=poorly_stacked,
        stop_results=stop_results
    )

    return result
