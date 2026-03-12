"""Chain resolver — topological sort, type resolution, structural validation.

Given a WorkflowGraphDef, produces a list of ResolvedNode in execution order
plus a list of validation warnings/errors.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Literal

from app.workflows.contracts import (
    DataType,
    EdgeKind,
    NodeContract,
    get_contract,
    type_compatible,
)
from app.workflows.models import WorkflowGraphDef, WorkflowStepDef


@dataclass
class ChainValidationError:
    step_id: str | None
    code: str  # "unmatched_fork", "illegal_back_edge", etc.
    message: str
    severity: Literal["error", "warning"]


@dataclass
class ResolvedPort:
    connected_step_id: str
    port_name: str
    edge_kind: EdgeKind
    data_type: DataType


@dataclass
class ResolvedNode:
    step_id: str
    position: int  # topo-order index
    role: Literal["entry", "middle", "terminal"]
    node_type: str
    inbound: list[ResolvedPort] = field(default_factory=list)
    outbound: list[ResolvedPort] = field(default_factory=list)
    resolved_input_type: DataType = DataType.ANY
    resolved_output_type: DataType = DataType.ANY
    parallel_group: str | None = None  # fork step_id
    loop_group: str | None = None  # loop step_id
    depth: int = 0  # nesting level


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_adjacency(
    graph: WorkflowGraphDef,
) -> tuple[
    dict[str, list[tuple[str, EdgeKind]]],  # forward edges: src -> [(dst, kind)]
    dict[str, int],  # in-degree
    set[str],  # all step IDs
]:
    """Build forward adjacency list from graph step fields."""
    forward: dict[str, list[tuple[str, EdgeKind]]] = defaultdict(list)
    in_degree: dict[str, int] = defaultdict(int)
    all_ids: set[str] = set()

    for step in graph.steps:
        all_ids.add(step.id)
        in_degree.setdefault(step.id, 0)

        if step.next_step:
            forward[step.id].append((step.next_step, EdgeKind.DEFAULT))
            in_degree[step.next_step] = in_degree.get(step.next_step, 0) + 1

        if step.next_steps:
            for target in step.next_steps:
                forward[step.id].append((target, EdgeKind.BRANCH))
                in_degree[target] = in_degree.get(target, 0) + 1

        if step.on_true:
            forward[step.id].append((step.on_true, EdgeKind.TRUE))
            in_degree[step.on_true] = in_degree.get(step.on_true, 0) + 1

        if step.on_false:
            forward[step.id].append((step.on_false, EdgeKind.FALSE))
            in_degree[step.on_false] = in_degree.get(step.on_false, 0) + 1

        if step.loop_body_entry:
            forward[step.id].append((step.loop_body_entry, EdgeKind.DEFAULT))
            in_degree[step.loop_body_entry] = in_degree.get(step.loop_body_entry, 0) + 1

    return forward, in_degree, all_ids


def _detect_back_edges(
    graph: WorkflowGraphDef,
    forward: dict[str, list[tuple[str, EdgeKind]]],
    all_ids: set[str],
) -> set[tuple[str, str]]:
    """DFS coloring to detect back-edges."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {sid: WHITE for sid in all_ids}
    back_edges: set[tuple[str, str]] = set()

    def dfs(node: str) -> None:
        color[node] = GRAY
        for target, _kind in forward.get(node, []):
            if target not in color:
                continue
            if color[target] == GRAY:
                back_edges.add((node, target))
            elif color[target] == WHITE:
                dfs(target)
        color[node] = BLACK

    # Start DFS from entry point first (if known) so back-edges
    # are detected in the correct direction
    entry_id = graph.entry_step_id if graph.entry_step_id in all_ids else None
    if entry_id and color.get(entry_id) == WHITE:
        dfs(entry_id)
    for sid in all_ids:
        if color[sid] == WHITE:
            dfs(sid)

    return back_edges


def _topo_sort(
    entry_id: str,
    forward: dict[str, list[tuple[str, EdgeKind]]],
    in_degree: dict[str, int],
    back_edges: set[tuple[str, str]],
    all_ids: set[str],
) -> list[str]:
    """Kahn's algorithm on forward edges (excluding back-edges)."""
    # Adjust in-degree by removing back-edges
    adjusted_in_degree = dict(in_degree)
    for src, dst in back_edges:
        adjusted_in_degree[dst] = max(0, adjusted_in_degree.get(dst, 0) - 1)

    queue: deque[str] = deque()
    # Entry point goes first
    if adjusted_in_degree.get(entry_id, 0) == 0:
        queue.append(entry_id)

    for sid in all_ids:
        if sid != entry_id and adjusted_in_degree.get(sid, 0) == 0:
            queue.append(sid)

    result: list[str] = []
    visited: set[str] = set()

    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        result.append(node)

        for target, _kind in forward.get(node, []):
            if (node, target) in back_edges:
                continue  # skip back-edges
            adjusted_in_degree[target] -= 1
            if adjusted_in_degree[target] == 0 and target not in visited:
                queue.append(target)

    # Append any remaining (unreachable) nodes
    for sid in all_ids:
        if sid not in visited:
            result.append(sid)

    return result


def _match_fork_join_pairs(
    topo_order: list[str],
    step_map: dict[str, WorkflowStepDef],
) -> dict[str, str]:
    """Stack-based pairing of fork/join nodes."""
    pairs: dict[str, str] = {}
    stack: list[str] = []

    for sid in topo_order:
        step = step_map.get(sid)
        if not step:
            continue
        if step.type == "fork":
            stack.append(sid)
        elif step.type == "join":
            if stack:
                fork_id = stack.pop()
                pairs[fork_id] = sid
            # If no fork on stack, it's an unmatched join (caught in validation)

    return pairs


def _resolve_port_type(
    contract: NodeContract,
    inbound_types: list[DataType],
) -> tuple[DataType, DataType]:
    """Resolve input/output types for a node given its inbound types."""
    # Determine resolved input
    if not inbound_types:
        resolved_in = DataType.VOID
    elif len(inbound_types) == 1:
        resolved_in = inbound_types[0]
    else:
        # Multiple inputs — use ANY
        resolved_in = DataType.ANY

    # Determine resolved output
    if not contract.outputs:
        return resolved_in, DataType.VOID

    out_type = contract.outputs[0].data_type
    if out_type == DataType.PASSTHROUGH:
        # Passthrough propagates the resolved input type
        return resolved_in, resolved_in
    return resolved_in, out_type


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_chain(
    graph: WorkflowGraphDef,
) -> tuple[list[ResolvedNode], list[ChainValidationError]]:
    """Walk graph -> topo sort -> resolve types -> validate structure."""
    warnings: list[ChainValidationError] = []

    if not graph.steps:
        return [], []

    step_map: dict[str, WorkflowStepDef] = {s.id: s for s in graph.steps}

    # 1. Build adjacency
    forward, in_degree, all_ids = _build_adjacency(graph)

    # 2. Detect back-edges
    back_edges = _detect_back_edges(graph, forward, all_ids)

    # Validate back-edges only target loop nodes
    for src, dst in back_edges:
        dst_step = step_map.get(dst)
        if dst_step and dst_step.type != "loop":
            warnings.append(ChainValidationError(
                step_id=src,
                code="illegal_back_edge",
                message=f"Back-edge from '{src}' to '{dst}' is only valid targeting loop nodes",
                severity="error",
            ))

    # 3. Topological sort
    topo_order = _topo_sort(graph.entry_step_id, forward, in_degree, back_edges, all_ids)

    # 4. Match fork/join pairs
    fork_join_pairs = _match_fork_join_pairs(topo_order, step_map)
    join_to_fork = {v: k for k, v in fork_join_pairs.items()}

    # Check for unmatched forks
    fork_ids = {s.id for s in graph.steps if s.type == "fork"}
    for fid in fork_ids:
        if fid not in fork_join_pairs:
            warnings.append(ChainValidationError(
                step_id=fid,
                code="unmatched_fork",
                message=f"Fork '{fid}' has no matching join node",
                severity="error",
            ))

    # Check for unmatched joins
    join_ids = {s.id for s in graph.steps if s.type == "join"}
    for jid in join_ids:
        if jid not in join_to_fork:
            warnings.append(ChainValidationError(
                step_id=jid,
                code="unmatched_join",
                message=f"Join '{jid}' has no matching fork node",
                severity="warning",
            ))

    # 5. Build reverse adjacency for inbound tracking
    reverse: dict[str, list[tuple[str, EdgeKind]]] = defaultdict(list)
    for src, targets in forward.items():
        for dst, kind in targets:
            reverse[dst].append((src, kind))

    # 6. Walk topo-order: resolve types
    resolved_types: dict[str, DataType] = {}
    resolved_nodes: list[ResolvedNode] = []
    reachable_from_entry: set[str] = set()

    # BFS to find reachable nodes
    bfs_queue: deque[str] = deque([graph.entry_step_id])
    while bfs_queue:
        node = bfs_queue.popleft()
        if node in reachable_from_entry:
            continue
        reachable_from_entry.add(node)
        for target, _ in forward.get(node, []):
            bfs_queue.append(target)
        # Also follow back-edges for reachability
        for src, dst in back_edges:
            if src == node:
                bfs_queue.append(dst)

    for pos, sid in enumerate(topo_order):
        step = step_map.get(sid)
        if not step:
            continue

        contract = get_contract(step.type)

        # Determine role
        if sid == graph.entry_step_id:
            role: Literal["entry", "middle", "terminal"] = "entry"
        elif not forward.get(sid):
            role = "terminal"
        else:
            role = "middle"

        # Gather inbound types
        inbound_types: list[DataType] = []
        inbound_ports: list[ResolvedPort] = []
        for src, kind in reverse.get(sid, []):
            src_type = resolved_types.get(src, DataType.ANY)
            inbound_types.append(src_type)
            inbound_ports.append(ResolvedPort(
                connected_step_id=src,
                port_name="default",
                edge_kind=kind,
                data_type=src_type,
            ))

        # Resolve types
        if contract:
            resolved_in, resolved_out = _resolve_port_type(contract, inbound_types)
        else:
            resolved_in = DataType.ANY
            resolved_out = DataType.ANY

        resolved_types[sid] = resolved_out

        # Build outbound ports
        outbound_ports: list[ResolvedPort] = []
        for dst, kind in forward.get(sid, []):
            outbound_ports.append(ResolvedPort(
                connected_step_id=dst,
                port_name="default",
                edge_kind=kind,
                data_type=resolved_out,
            ))

        # Determine parallel/loop group
        parallel_group = join_to_fork.get(sid) if step.type == "join" else None
        if not parallel_group:
            # Check if this node is inside a fork's branch
            for fork_id, join_id in fork_join_pairs.items():
                fork_pos = topo_order.index(fork_id) if fork_id in topo_order else -1
                join_pos = topo_order.index(join_id) if join_id in topo_order else -1
                if fork_pos < pos < join_pos:
                    parallel_group = fork_id
                    break

        rn = ResolvedNode(
            step_id=sid,
            position=pos,
            role=role,
            node_type=step.type,
            inbound=inbound_ports,
            outbound=outbound_ports,
            resolved_input_type=resolved_in,
            resolved_output_type=resolved_out,
            parallel_group=parallel_group,
        )
        resolved_nodes.append(rn)

        # Check if unreachable
        if sid not in reachable_from_entry:
            warnings.append(ChainValidationError(
                step_id=sid,
                code="orphan_node",
                message=f"Step '{sid}' is not reachable from entry point",
                severity="warning",
            ))

    # 7. Type compatibility checks
    for sid in topo_order:
        step = step_map.get(sid)
        if not step:
            continue
        contract = get_contract(step.type)
        if not contract or not contract.inputs:
            continue

        target_type = contract.inputs[0].data_type
        for src, kind in reverse.get(sid, []):
            src_type = resolved_types.get(src, DataType.ANY)
            if not type_compatible(src_type, target_type):
                warnings.append(ChainValidationError(
                    step_id=sid,
                    code="type_incompatible",
                    message=f"Output type '{src_type.value}' from '{src}' is incompatible with input type '{target_type.value}' on '{sid}'",
                    severity="warning",
                ))

    # 8. Loop validation
    for step in graph.steps:
        if step.type == "loop":
            if not step.loop_body_entry:
                warnings.append(ChainValidationError(
                    step_id=step.id,
                    code="missing_loop_body_entry",
                    message=f"Loop '{step.id}' has no loop_body_entry",
                    severity="error",
                ))
            # Check that at least one back-edge targets this loop
            has_back = any(dst == step.id for _, dst in back_edges)
            if not has_back and step.loop_body_entry:
                warnings.append(ChainValidationError(
                    step_id=step.id,
                    code="missing_loop_back_edge",
                    message=f"Loop '{step.id}' has no back-edge returning to it",
                    severity="warning",
                ))

    return resolved_nodes, warnings
