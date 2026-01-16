#!/usr/bin/env python3
"""
prd_manager.py - Generic JSONL-based PRD management for append-only operations.

This provides JSONL-based story/item management with append-only semantics,
dependency awareness, and phase-based filtering for implementation loops.

Usage:
    python scripts/prd_manager.py --prd FILE COMMAND [args...]

Environment:
    PRD_FILE - Default PRD file path (overridden by --prd flag)

Commands:
    append                  # Append stories from stdin (JSON array or JSONL)
    ids                     # List all existing IDs (for duplicate checking)
    count                   # Count stories
    dedupe                  # Remove duplicate IDs (keeps first)
    stats                   # Category/phase statistics

Implementation Loop Commands:
    next-pending                              # Get next story to implement (JSON)
    next-pending-ordered [--phase N] [--category CAT]  # Dependency-aware selection
    pending-count                             # Count remaining pending stories
    get-story ID                              # Get full story JSON by ID
    get-status ID                             # Get story status
    implemented-summary                       # List implemented stories for context
    implemented-summary-compressed            # Tiered summary for large PRDs
    mark-implemented ID [description]         # Set status=implemented
    mark-dup ID PARENT_ID                     # Set status=dup, dup_of=PARENT_ID
    mark-skipped ID [reason]                  # Set status=skipped

Generic Schema (JSONL, one story per line):
{
  "id": "FEAT-001",           # Required: unique identifier
  "priority": 1,              # Required: lower = more foundational
  "story": "User can...",     # Required: user story text
  "acceptance_criteria": [],  # Required: list of criteria
  "status": "pending",        # Status: pending, implemented, dup, skipped
  "category": "CORE",         # Optional: category for grouping
  "phase": 1,                 # Optional: phase number for ordering
  "dependencies": [],         # Optional: list of story IDs this depends on
  "dup_of": null,             # Set when status=dup
  "impl_notes": null,         # Implementation notes
  "implemented_at": null,     # ISO timestamp when implemented
  "notes": ""                 # General notes
}
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Default PRD file (can be overridden by --prd or PRD_FILE env)
DEFAULT_PRD = Path("design/prd.jsonl")

# Required fields for validation
REQUIRED_FIELDS = {"id", "priority", "story", "acceptance_criteria"}


def get_prd_path(args_prd: str | None = None) -> Path:
    """Get PRD file path from args, env, or default."""
    if args_prd:
        return Path(args_prd)
    env_prd = os.environ.get("PRD_FILE")
    if env_prd:
        return Path(env_prd)
    return DEFAULT_PRD


def load_all_stories(prd_path: Path) -> list[dict]:
    """Load all stories from JSONL file."""
    stories = []
    if prd_path.exists():
        with open(prd_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        stories.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return stories


def save_all_stories(prd_path: Path, stories: list[dict]):
    """Save all stories back to JSONL file."""
    prd_path.parent.mkdir(parents=True, exist_ok=True)
    with open(prd_path, "w") as f:
        for story in stories:
            f.write(json.dumps(story, separators=(",", ":")) + "\n")


def get_existing_ids(prd_path: Path) -> set:
    """Get all existing story IDs from JSONL file."""
    ids = set()
    if prd_path.exists():
        with open(prd_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        story = json.loads(line)
                        if "id" in story:
                            ids.add(story["id"])
                    except json.JSONDecodeError:
                        pass
    return ids


def validate_story(story: dict) -> list[str]:
    """Validate a story has required fields."""
    errors = []
    missing = REQUIRED_FIELDS - set(story.keys())
    if missing:
        errors.append(f"Missing fields: {missing}")
    if "priority" in story and not isinstance(story["priority"], (int, float)):
        errors.append("priority must be number")
    if "acceptance_criteria" in story and not isinstance(story["acceptance_criteria"], list):
        errors.append("acceptance_criteria must be list")
    return errors


def update_story(prd_path: Path, story_id: str, updates: dict) -> bool:
    """Update a story by ID with given field updates. Returns True if found."""
    stories = load_all_stories(prd_path)
    found = False

    for story in stories:
        if story.get("id") == story_id:
            story.update(updates)
            found = True
            break

    if found:
        save_all_stories(prd_path, stories)

    return found


# =============================================================================
# Commands
# =============================================================================


def cmd_append(prd_path: Path):
    """Append stories from stdin (JSON array or JSONL)."""
    input_text = sys.stdin.read().strip()
    if not input_text:
        print("ERROR: No input", file=sys.stderr)
        sys.exit(1)

    # Parse input - could be JSON array or JSONL
    stories = []
    try:
        parsed = json.loads(input_text)
        if isinstance(parsed, list):
            stories = parsed
        elif isinstance(parsed, dict):
            stories = [parsed]
    except json.JSONDecodeError:
        # Try JSONL format
        for line in input_text.split("\n"):
            line = line.strip()
            if line:
                try:
                    stories.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not stories:
        print("ERROR: No valid stories in input", file=sys.stderr)
        sys.exit(1)

    # Get existing IDs for deduplication
    existing_ids = get_existing_ids(prd_path)

    # Validate and append
    added = []
    skipped = []

    prd_path.parent.mkdir(parents=True, exist_ok=True)
    with open(prd_path, "a") as f:
        for story in stories:
            story_id = story.get("id", "???")

            # Check duplicate
            if story_id in existing_ids:
                skipped.append(f"{story_id} (duplicate)")
                continue

            # Validate
            errors = validate_story(story)
            if errors:
                skipped.append(f"{story_id} ({'; '.join(errors)})")
                continue

            # Add defaults
            if "status" not in story:
                story["status"] = "pending"
            if "notes" not in story:
                story["notes"] = ""

            # Append to JSONL
            f.write(json.dumps(story, separators=(",", ":")) + "\n")
            existing_ids.add(story_id)
            added.append(story_id)
            print(f"ADDED: {story_id} - {story['story'][:60]}")

    if added:
        print(f"\nAdded {len(added)} stories: {', '.join(added)}")
    if skipped:
        print(f"Skipped {len(skipped)}: {', '.join(skipped)}", file=sys.stderr)

    if not added:
        sys.exit(1)


def cmd_ids(prd_path: Path):
    """List all existing IDs."""
    ids = sorted(get_existing_ids(prd_path))
    print(",".join(ids))


def cmd_count(prd_path: Path):
    """Count stories in JSONL."""
    count = 0
    if prd_path.exists():
        with open(prd_path) as f:
            for line in f:
                if line.strip():
                    count += 1
    print(count)


def cmd_dedupe(prd_path: Path):
    """Remove duplicate IDs, keeping first occurrence."""
    if not prd_path.exists():
        print(f"ERROR: {prd_path} not found", file=sys.stderr)
        sys.exit(1)

    seen_ids = set()
    unique_stories = []
    duplicates = 0

    with open(prd_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    story = json.loads(line)
                    story_id = story.get("id")
                    if story_id and story_id not in seen_ids:
                        seen_ids.add(story_id)
                        unique_stories.append(line)
                    else:
                        duplicates += 1
                except json.JSONDecodeError:
                    pass

    with open(prd_path, "w") as f:
        for line in unique_stories:
            f.write(line + "\n")

    print(f"Removed {duplicates} duplicates, kept {len(unique_stories)} stories")


def cmd_stats(prd_path: Path):
    """Show statistics by category and phase."""
    stories = load_all_stories(prd_path)

    if not stories:
        print("No stories found")
        return

    # Count by status
    by_status: dict[str, int] = {}
    by_category: dict[str, dict[str, int]] = {}
    by_phase: dict[int, dict[str, int]] = {}

    for s in stories:
        status = s.get("status", "pending")
        by_status[status] = by_status.get(status, 0) + 1

        # Category stats
        cat = s.get("category", s.get("id", "UNK").split("-")[0])
        if cat not in by_category:
            by_category[cat] = {"total": 0, "pending": 0, "implemented": 0, "other": 0}
        by_category[cat]["total"] += 1
        if status == "pending":
            by_category[cat]["pending"] += 1
        elif status == "implemented":
            by_category[cat]["implemented"] += 1
        else:
            by_category[cat]["other"] += 1

        # Phase stats
        phase = s.get("phase")
        if phase is not None:
            if phase not in by_phase:
                by_phase[phase] = {"total": 0, "pending": 0, "implemented": 0}
            by_phase[phase]["total"] += 1
            if status == "pending":
                by_phase[phase]["pending"] += 1
            elif status == "implemented":
                by_phase[phase]["implemented"] += 1

    # Output
    print(f"## PRD Statistics ({len(stories)} total)")
    print()

    print("### By Status")
    for status in sorted(by_status.keys()):
        print(f"  {status}: {by_status[status]}")
    print()

    print("### By Category")
    for cat in sorted(by_category.keys()):
        stats = by_category[cat]
        pct = (stats["implemented"] / stats["total"] * 100) if stats["total"] > 0 else 0
        print(f"  {cat}: {stats['implemented']}/{stats['total']} ({pct:.0f}%), {stats['pending']} pending")
    print()

    if by_phase:
        print("### By Phase")
        for phase in sorted(by_phase.keys()):
            stats = by_phase[phase]
            pct = (stats["implemented"] / stats["total"] * 100) if stats["total"] > 0 else 0
            print(f"  Phase {phase}: {stats['implemented']}/{stats['total']} ({pct:.0f}%), {stats['pending']} pending")


def cmd_next_pending(prd_path: Path):
    """Get next story to implement (lowest priority, status=pending)."""
    stories = load_all_stories(prd_path)

    # Filter: status=pending (or missing status)
    pending = [
        s for s in stories
        if s.get("status", "pending") == "pending"
    ]

    if not pending:
        print("{}", flush=True)  # Empty JSON object
        return

    # Sort by priority (lowest first = foundational)
    pending.sort(key=lambda s: s.get("priority", 999))

    # Output as JSON
    print(json.dumps(pending[0]))


def cmd_pending_count(prd_path: Path):
    """Count remaining pending stories."""
    stories = load_all_stories(prd_path)

    pending = [
        s for s in stories
        if s.get("status", "pending") == "pending"
    ]

    print(len(pending))


def cmd_get_story(prd_path: Path, story_id: str):
    """Get full story JSON by ID."""
    stories = load_all_stories(prd_path)

    for story in stories:
        if story.get("id") == story_id:
            print(json.dumps(story, indent=2))
            return

    print(f"ERROR: Story {story_id} not found", file=sys.stderr)
    sys.exit(1)


def cmd_get_status(prd_path: Path, story_id: str):
    """Get the status of a story."""
    stories = load_all_stories(prd_path)

    for story in stories:
        if story.get("id") == story_id:
            status = story.get("status", "pending")
            print(status)
            return

    print("not_found")


def cmd_implemented_summary(prd_path: Path):
    """List implemented stories grouped by category for prompt context."""
    stories = load_all_stories(prd_path)

    # Filter to implemented stories
    implemented = [
        s for s in stories
        if s.get("status") == "implemented"
    ]

    if not implemented:
        print("No stories implemented yet.")
        return

    # Group by category
    by_category: dict[str, list[str]] = {}
    for s in implemented:
        cat = s.get("category", s["id"].split("-")[0] if "-" in s.get("id", "") else "UNK")
        if cat not in by_category:
            by_category[cat] = []
        # Truncate story text for summary
        story_text = s.get("story", "")[:80]
        by_category[cat].append(f"{s['id']}: {story_text}")

    # Output grouped summary
    for cat in sorted(by_category.keys()):
        print(f"\n## {cat} ({len(by_category[cat])} implemented)")
        for item in by_category[cat]:
            print(f"  - {item}")

    print(f"\nTotal implemented: {len(implemented)}")


def cmd_implemented_summary_compressed(prd_path: Path):
    """Tiered summary with key story preservation for DUP_OF detection at scale."""
    stories = load_all_stories(prd_path)

    # Filter to implemented stories
    implemented = [
        s for s in stories
        if s.get("status") == "implemented"
    ]

    total = len(implemented)

    if total == 0:
        print("No stories implemented yet.")
        return

    # Group by category, preserving order
    by_category: dict[str, list[dict]] = {}
    for s in implemented:
        cat = s.get("category", s["id"].split("-")[0] if "-" in s.get("id", "") else "UNK")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(s)

    # Sort each category by ID to get first stories
    for cat in by_category:
        by_category[cat].sort(key=lambda s: s.get("id", ""))

    print(f"## Implemented Summary ({total} stories)")
    print()

    # Key stories section (first 3 non-dup per category)
    print("### Key Stories by Category (for duplicate detection)")
    for cat in sorted(by_category.keys()):
        cat_stories = by_category[cat]
        # Get first 3 non-duplicate stories
        key_stories = [s for s in cat_stories if s.get("status") != "dup"][:3]
        key_summaries = [f"{s['id']}: {s.get('story', '')[:40]}" for s in key_stories]
        print(f"{cat}: {' | '.join(key_summaries)}")
    print()

    # Category counts
    print("### Category Counts")
    counts = " | ".join(f"{p}: {len(by_category[p])}" for p in sorted(by_category.keys()))
    print(counts)
    print()

    # Show details based on total count
    if total < 500:
        # Full detail mode
        print("### All Implemented Stories")
        for cat in sorted(by_category.keys()):
            print(f"\n#### {cat} ({len(by_category[cat])} stories)")
            for s in by_category[cat]:
                print(f"  - {s['id']}: {s.get('story', '')[:80]}")
    else:
        # Compressed mode - show last N by implemented_at
        recent_count = 100 if total < 1500 else 50

        # Sort all implemented by timestamp or file order
        all_impl = []
        for s in implemented:
            ts = s.get("implemented_at", "")
            all_impl.append((ts, s))
        all_impl.sort(key=lambda x: x[0], reverse=True)

        recent = [s for _, s in all_impl[:recent_count]]

        print(f"### Recent ({recent_count} of {total})")
        for s in recent:
            print(f"  - {s['id']}: {s.get('story', '')[:80]}")

    print(f"\nTotal implemented: {total}")


def cmd_mark_implemented(prd_path: Path, story_id: str, impl_notes: str = ""):
    """Mark story as implemented."""
    updates = {
        "status": "implemented",
        "implemented_at": datetime.now().isoformat(),
    }
    if impl_notes:
        updates["impl_notes"] = impl_notes

    if update_story(prd_path, story_id, updates):
        print(f"Marked {story_id} as implemented")
    else:
        print(f"ERROR: Story {story_id} not found", file=sys.stderr)
        sys.exit(1)


def cmd_mark_dup(prd_path: Path, story_id: str, parent_id: str):
    """Mark story as duplicate."""
    # Verify parent exists
    stories = load_all_stories(prd_path)
    parent_exists = any(s.get("id") == parent_id for s in stories)

    if not parent_exists:
        print(f"ERROR: Parent story {parent_id} not found", file=sys.stderr)
        sys.exit(1)

    updates = {
        "status": "dup",
        "dup_of": parent_id,
    }

    if update_story(prd_path, story_id, updates):
        print(f"Marked {story_id} as duplicate of {parent_id}")
    else:
        print(f"ERROR: Story {story_id} not found", file=sys.stderr)
        sys.exit(1)


def cmd_mark_skipped(prd_path: Path, story_id: str, reason: str = ""):
    """Mark story as skipped."""
    updates = {"status": "skipped"}
    if reason:
        updates["impl_notes"] = f"Skipped: {reason}"

    if update_story(prd_path, story_id, updates):
        print(f"Marked {story_id} as skipped")
    else:
        print(f"ERROR: Story {story_id} not found", file=sys.stderr)
        sys.exit(1)


# =============================================================================
# Dependency-Aware Selection
# =============================================================================


def build_dependency_graph(stories: list[dict]) -> dict[str, set[str]]:
    """Build a dependency graph: story_id -> set of story_ids it depends on.

    Uses explicit dependencies field if present, otherwise tries to infer
    from story text patterns.
    """
    graph: dict[str, set[str]] = {}

    # Build set of all story IDs for validation
    all_ids = set(s.get("id") for s in stories)

    # Patterns for inferring dependencies from text
    dep_patterns = [
        re.compile(r"(?:requires?|needs?)\s+(?:the\s+)?(\w+[-_]\d+)", re.I),
        re.compile(r"(?:depends on|after)\s+(?:the\s+)?(\w+[-_]\d+)", re.I),
        re.compile(r"(?:builds on|extends?)\s+(?:the\s+)?(\w+[-_]\d+)", re.I),
    ]

    for s in stories:
        story_id = s.get("id", "")
        graph[story_id] = set()

        # Use explicit dependencies if present
        explicit_deps = s.get("dependencies", [])
        if explicit_deps:
            for dep_id in explicit_deps:
                if dep_id in all_ids and dep_id != story_id:
                    graph[story_id].add(dep_id)
        else:
            # Try to infer from story text
            text_to_check = s.get("story", "")
            for ac in s.get("acceptance_criteria", []):
                if isinstance(ac, str):
                    text_to_check += " " + ac

            for pattern in dep_patterns:
                for match in pattern.finditer(text_to_check):
                    dep_id = match.group(1)
                    if dep_id in all_ids and dep_id != story_id:
                        graph[story_id].add(dep_id)

    return graph


def cmd_next_pending_ordered(prd_path: Path, phase: int | None = None, category: str | None = None):
    """Get next story with dependency-aware ordering.

    Args:
        phase: Phase number to filter by
        category: Category prefix to filter by
    """
    stories = load_all_stories(prd_path)

    # Filter to pending stories
    pending = [
        s for s in stories
        if s.get("status", "pending") == "pending"
    ]

    if not pending:
        print("{}", flush=True)
        return

    # Filter by phase
    if phase is not None:
        pending = [s for s in pending if s.get("phase") == phase]
        if not pending:
            print(f"Phase {phase} complete!", file=sys.stderr)
            print("{}", flush=True)
            return

    # Filter by category
    if category:
        pending = [
            s for s in pending
            if s.get("category", s.get("id", "").split("-")[0]) == category
        ]
        if not pending:
            print(f"Category {category} complete!", file=sys.stderr)
            print("{}", flush=True)
            return

    # Build dependency graph
    dep_graph = build_dependency_graph(stories)

    # Get implemented story IDs (dependencies that are satisfied)
    implemented_ids = set(
        s.get("id") for s in stories
        if s.get("status") in ("implemented", "dup")
    )

    # Find stories with all dependencies satisfied
    ready = []
    for s in pending:
        sid = s.get("id")
        deps = dep_graph.get(sid, set())
        unsatisfied = deps - implemented_ids

        if not unsatisfied:
            ready.append(s)

    if not ready:
        # All pending have unsatisfied deps - break cycle by taking lowest priority
        print("WARNING: All pending stories have unsatisfied dependencies, using priority order", file=sys.stderr)
        ready = pending

    # Sort by priority (lowest first)
    ready.sort(key=lambda s: s.get("priority", 999))

    # Return first ready story
    print(json.dumps(ready[0]))


# =============================================================================
# Main
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="JSONL-based PRD management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--prd", "-p",
        help="PRD file path (default: design/prd.jsonl or PRD_FILE env)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Basic commands
    subparsers.add_parser("append", help="Append stories from stdin")
    subparsers.add_parser("ids", help="List all story IDs")
    subparsers.add_parser("count", help="Count stories")
    subparsers.add_parser("dedupe", help="Remove duplicate IDs")
    subparsers.add_parser("stats", help="Show statistics")

    # Implementation loop commands
    subparsers.add_parser("next-pending", help="Get next pending story")
    subparsers.add_parser("pending-count", help="Count pending stories")

    p = subparsers.add_parser("get-story", help="Get story by ID")
    p.add_argument("story_id", help="Story ID")

    p = subparsers.add_parser("get-status", help="Get story status")
    p.add_argument("story_id", help="Story ID")

    subparsers.add_parser("implemented-summary", help="List implemented stories")
    subparsers.add_parser("implemented-summary-compressed", help="Compressed summary")

    p = subparsers.add_parser("mark-implemented", help="Mark story as implemented")
    p.add_argument("story_id", help="Story ID")
    p.add_argument("notes", nargs="?", default="", help="Implementation notes")

    p = subparsers.add_parser("mark-dup", help="Mark story as duplicate")
    p.add_argument("story_id", help="Story ID")
    p.add_argument("parent_id", help="Parent story ID")

    p = subparsers.add_parser("mark-skipped", help="Mark story as skipped")
    p.add_argument("story_id", help="Story ID")
    p.add_argument("reason", nargs="?", default="", help="Skip reason")

    p = subparsers.add_parser("next-pending-ordered", help="Get next story with dependency ordering")
    p.add_argument("--phase", type=int, help="Phase number to filter by")
    p.add_argument("--category", help="Category to filter by")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    prd_path = get_prd_path(args.prd)

    # Dispatch commands
    if args.command == "append":
        cmd_append(prd_path)
    elif args.command == "ids":
        cmd_ids(prd_path)
    elif args.command == "count":
        cmd_count(prd_path)
    elif args.command == "dedupe":
        cmd_dedupe(prd_path)
    elif args.command == "stats":
        cmd_stats(prd_path)
    elif args.command == "next-pending":
        cmd_next_pending(prd_path)
    elif args.command == "pending-count":
        cmd_pending_count(prd_path)
    elif args.command == "get-story":
        cmd_get_story(prd_path, args.story_id)
    elif args.command == "get-status":
        cmd_get_status(prd_path, args.story_id)
    elif args.command == "implemented-summary":
        cmd_implemented_summary(prd_path)
    elif args.command == "implemented-summary-compressed":
        cmd_implemented_summary_compressed(prd_path)
    elif args.command == "mark-implemented":
        cmd_mark_implemented(prd_path, args.story_id, args.notes)
    elif args.command == "mark-dup":
        cmd_mark_dup(prd_path, args.story_id, args.parent_id)
    elif args.command == "mark-skipped":
        cmd_mark_skipped(prd_path, args.story_id, args.reason)
    elif args.command == "next-pending-ordered":
        cmd_next_pending_ordered(prd_path, args.phase, args.category)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
