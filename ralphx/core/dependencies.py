"""Dependency graph for story ordering and phase detection.

Handles:
- Building dependency graphs from work items
- Topological sorting for implementation order
- Auto-detecting phases based on dependency chains
- Finding stories ready to implement (all dependencies complete)
"""

from collections import defaultdict
from typing import Optional


class DependencyGraph:
    """Manages story dependencies for phase-based implementation."""

    def __init__(self, items: list[dict]):
        """Initialize graph from work items.

        Args:
            items: List of work item dicts with 'id' and optional 'dependencies'.
        """
        self.items = {item["id"]: item for item in items}
        self.graph: dict[str, list[str]] = {}  # id -> list of items that depend on it
        self.reverse_graph: dict[str, list[str]] = {}  # id -> list of dependencies
        # Track invalid dependency references for diagnostics
        self.missing_dependencies: dict[str, list[str]] = {}  # item_id -> list of missing dep IDs
        self._build_graph(items)

    def _build_graph(self, items: list[dict]) -> None:
        """Build adjacency lists from items."""
        # Initialize all nodes
        for item in items:
            item_id = item["id"]
            self.graph[item_id] = []
            self.reverse_graph[item_id] = []

        # Build edges
        for item in items:
            item_id = item["id"]
            deps = item.get("dependencies") or []
            for dep_id in deps:
                if dep_id in self.items:
                    # Valid dependency - add edge
                    self.graph[dep_id].append(item_id)
                    self.reverse_graph[item_id].append(dep_id)
                else:
                    # Invalid dependency - track for diagnostics
                    if item_id not in self.missing_dependencies:
                        self.missing_dependencies[item_id] = []
                    self.missing_dependencies[item_id].append(dep_id)

    def topological_sort(self) -> list[str]:
        """Return item IDs in dependency order (dependencies first).

        Uses Kahn's algorithm for topological sorting.
        Handles cycles by breaking them (items with unmet deps go last).

        Returns:
            List of item IDs in implementation order.
        """
        # Calculate in-degree for each node
        in_degree = {item_id: len(deps) for item_id, deps in self.reverse_graph.items()}

        # Start with items that have no dependencies
        queue = [item_id for item_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            # Sort queue by priority for deterministic order
            queue.sort(key=lambda x: (self.items[x].get("priority") or 999, x))
            current = queue.pop(0)
            result.append(current)

            # Reduce in-degree for items that depend on current
            for dependent in self.graph[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # Handle remaining items (cycles or missing dependencies)
        remaining = [item_id for item_id in self.items if item_id not in result]
        if remaining:
            # Sort remaining by priority
            remaining.sort(key=lambda x: (self.items[x].get("priority") or 999, x))
            result.extend(remaining)

        return result

    def detect_phases(self, max_batch_size: int = 10) -> dict[int, list[str]]:
        """Auto-group items into phases based on dependency chains.

        Phase 1: Items with no dependencies (foundation)
        Phase 2: Items that only depend on Phase 1
        Phase 3: Items that only depend on Phase 1 or 2
        ... and so on

        Args:
            max_batch_size: Maximum items per phase (splits large phases).

        Returns:
            Dict mapping phase number (1-indexed) to list of item IDs.
        """
        phases: dict[int, list[str]] = {}
        assigned: set[str] = set()
        phase_num = 1

        while len(assigned) < len(self.items):
            # Find items whose dependencies are all assigned
            phase_items = []
            for item_id in self.items:
                if item_id in assigned:
                    continue
                deps = self.reverse_graph.get(item_id, [])
                if all(dep in assigned for dep in deps):
                    phase_items.append(item_id)

            if not phase_items:
                # Cycle detected - add remaining items to final phase
                remaining = [i for i in self.items if i not in assigned]
                remaining.sort(key=lambda x: (self.items[x].get("priority") or 999, x))
                phase_items = remaining

            # Sort by priority within phase
            phase_items.sort(key=lambda x: (self.items[x].get("priority") or 999, x))

            # Split if exceeds max batch size
            while phase_items:
                batch = phase_items[:max_batch_size]
                phases[phase_num] = batch
                assigned.update(batch)
                phase_items = phase_items[max_batch_size:]
                if phase_items:
                    phase_num += 1

            phase_num += 1

        return phases

    def detect_phases_by_category(
        self,
        category_phases: dict[str, int],
        max_batch_size: int = 10,
    ) -> dict[int, list[str]]:
        """Group items into phases based on category mapping.

        Args:
            category_phases: Dict mapping category name to phase number.
            max_batch_size: Maximum items per phase.

        Returns:
            Dict mapping phase number to list of item IDs.
        """
        phases: dict[int, list[str]] = defaultdict(list)

        for item_id, item in self.items.items():
            category = (item.get("category") or "").lower()
            phase = category_phases.get(category, 999)  # Unmapped -> last
            phases[phase].append(item_id)

        # Sort each phase by priority and split if needed
        result: dict[int, list[str]] = {}
        for phase_num in sorted(phases.keys()):
            items = phases[phase_num]
            items.sort(key=lambda x: (self.items[x].get("priority") or 999, x))

            # Renumber phases to be sequential
            sub_phase = 0
            while items:
                batch = items[:max_batch_size]
                # Use phase_num * 100 + sub_phase for sub-phases
                result_phase = phase_num if sub_phase == 0 else phase_num * 100 + sub_phase
                result[result_phase] = batch
                items = items[max_batch_size:]
                sub_phase += 1

        return result

    def get_phase_items(self, phases: dict[int, list[str]], phase: int) -> list[str]:
        """Get item IDs for a specific phase.

        Args:
            phases: Phase mapping from detect_phases().
            phase: Phase number to retrieve.

        Returns:
            List of item IDs in that phase, or empty list.
        """
        return phases.get(phase, [])

    def get_ready_items(self, completed: set[str]) -> list[str]:
        """Get items whose dependencies are all completed.

        Args:
            completed: Set of completed item IDs.

        Returns:
            List of item IDs ready for implementation.
        """
        ready = []
        for item_id in self.items:
            if item_id in completed:
                continue
            deps = self.reverse_graph.get(item_id, [])
            if all(dep in completed for dep in deps):
                ready.append(item_id)

        # Sort by priority
        ready.sort(key=lambda x: (self.items[x].get("priority") or 999, x))
        return ready

    def get_dependencies(self, item_id: str) -> list[str]:
        """Get direct dependencies of an item.

        Args:
            item_id: The item ID to check.

        Returns:
            List of item IDs this item depends on.
        """
        return self.reverse_graph.get(item_id, [])

    def get_dependents(self, item_id: str) -> list[str]:
        """Get items that depend on this item.

        Args:
            item_id: The item ID to check.

        Returns:
            List of item IDs that depend on this item.
        """
        return self.graph.get(item_id, [])

    def has_cycle(self) -> bool:
        """Check if the graph has any cycles.

        Returns:
            True if cycles exist, False otherwise.
        """
        visited = set()
        rec_stack = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in self.graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for node in self.items:
            if node not in visited:
                if dfs(node):
                    return True

        return False

    def find_cycles(self) -> list[list[str]]:
        """Find all cycles in the graph.

        Returns:
            List of cycles, each cycle is a list of item IDs.
        """
        cycles = []
        visited = set()
        rec_stack = []
        rec_set = set()

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.append(node)
            rec_set.add(node)

            for neighbor in self.graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_set:
                    # Found cycle - extract it
                    cycle_start = rec_stack.index(neighbor)
                    cycle = rec_stack[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            rec_stack.pop()
            rec_set.remove(node)

        for node in self.items:
            if node not in visited:
                dfs(node)

        return cycles

    def get_stats(self) -> dict:
        """Get statistics about the dependency graph.

        Returns:
            Dict with graph statistics.
        """
        total_items = len(self.items)
        items_with_deps = sum(1 for deps in self.reverse_graph.values() if deps)
        items_no_deps = total_items - items_with_deps
        total_edges = sum(len(deps) for deps in self.reverse_graph.values())
        missing_dep_count = sum(len(deps) for deps in self.missing_dependencies.values())

        return {
            "total_items": total_items,
            "items_with_dependencies": items_with_deps,
            "items_without_dependencies": items_no_deps,
            "total_dependency_edges": total_edges,
            "has_cycles": self.has_cycle(),
            "missing_dependencies_count": missing_dep_count,
            "items_with_missing_deps": list(self.missing_dependencies.keys()),
        }


def order_items_by_dependency(
    items: list[dict],
    completed_ids: Optional[set[str]] = None,
) -> list[dict]:
    """Order items by dependencies, filtering out completed ones.

    Convenience function for getting next items to implement.

    Args:
        items: List of work item dicts.
        completed_ids: Set of already-completed item IDs to exclude.

    Returns:
        Ordered list of items ready for implementation.
    """
    if completed_ids is None:
        completed_ids = set()

    # Filter to pending items
    pending = [item for item in items if item["id"] not in completed_ids]
    if not pending:
        return []

    graph = DependencyGraph(pending)
    ready_ids = graph.get_ready_items(completed_ids)

    # Return full item dicts in order
    id_to_item = {item["id"]: item for item in pending}
    return [id_to_item[item_id] for item_id in ready_ids if item_id in id_to_item]
