#!/usr/bin/env python3
"""
extract_json.py - Extract JSON array from Claude's output.

Usage:
    echo "some text [json array] more text" | python scripts/extract_json.py

Handles:
- Markdown code fences (```json ... ```)
- Preamble text before JSON
- Multi-line JSON arrays
- Validates JSON before outputting

Returns:
- Valid JSON array on stdout (exit 0)
- Error message on stderr (exit 1)
"""
import json
import re
import sys


def extract_json_array(text: str, require_objects: bool = False) -> str | None:
    """Extract a JSON array from text, handling various formats.

    Args:
        text: Raw text potentially containing JSON
        require_objects: If True, only return arrays of objects (dicts)
    """

    # First, try to find JSON in markdown code fences
    fence_pattern = r'```(?:json)?\s*(\[[\s\S]*?\])\s*```'
    fence_match = re.search(fence_pattern, text)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1))
            if isinstance(parsed, list) and len(parsed) > 0:
                if not require_objects or isinstance(parsed[0], dict):
                    return json.dumps(parsed)
        except json.JSONDecodeError:
            pass

    # Try to find a JSON array directly (handles multi-line)
    # Look for [ followed by content and ending with ]
    array_pattern = r'\[[\s\S]*\]'
    matches = re.findall(array_pattern, text)

    # Try each match, starting with the longest (most likely to be complete)
    for match in sorted(matches, key=len, reverse=True):
        try:
            parsed = json.loads(match)
            if isinstance(parsed, list) and len(parsed) > 0:
                if not require_objects or isinstance(parsed[0], dict):
                    return json.dumps(parsed)
        except json.JSONDecodeError:
            continue

    # Last resort: try to parse the entire text as JSON
    try:
        parsed = json.loads(text.strip())
        if isinstance(parsed, list):
            if not require_objects or (len(parsed) > 0 and isinstance(parsed[0], dict)):
                return json.dumps(parsed)
    except json.JSONDecodeError:
        pass

    return None


def extract_json_object(text: str) -> str | None:
    """Extract a JSON object from text, handling various formats."""

    # First, try to find JSON in markdown code fences
    fence_pattern = r'```(?:json)?\s*(\{[\s\S]*?\})\s*```'
    fence_match = re.search(fence_pattern, text)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1))
            if isinstance(parsed, dict):
                return json.dumps(parsed)
        except json.JSONDecodeError:
            pass

    # Try to find a JSON object directly (handles multi-line)
    object_pattern = r'\{[\s\S]*\}'
    matches = re.findall(object_pattern, text)

    # Try each match, starting with the longest (most likely to be complete)
    for match in sorted(matches, key=len, reverse=True):
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict):
                return json.dumps(parsed)
        except json.JSONDecodeError:
            continue

    # Last resort: try to parse the entire text as JSON
    try:
        parsed = json.loads(text.strip())
        if isinstance(parsed, dict):
            return json.dumps(parsed)
    except json.JSONDecodeError:
        pass

    return None


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Extract JSON from text")
    parser.add_argument(
        "--object", "-o",
        action="store_true",
        help="Extract a JSON object instead of an array"
    )
    parser.add_argument(
        "--require-objects",
        action="store_true",
        help="Only extract arrays of objects (dicts)"
    )
    args = parser.parse_args()

    text = sys.stdin.read()

    if not text.strip():
        print("ERROR: No input received", file=sys.stderr)
        sys.exit(1)

    if args.object:
        json_str = extract_json_object(text)
    else:
        json_str = extract_json_array(text, require_objects=args.require_objects)

    if json_str:
        print(json_str)
        sys.exit(0)
    else:
        # Show what we received for debugging
        preview = text[:500].replace('\n', '\\n')
        expected = "object" if args.object else "array"
        print(f"ERROR: Could not extract valid JSON {expected} from output", file=sys.stderr)
        print(f"Preview: {preview}...", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
