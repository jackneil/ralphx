#!/usr/bin/env python3
"""
parse_stream.py - Parse Claude stream-json output with comprehensive logging.

Usage:
    claude -p --output-format stream-json "prompt" | python scripts/parse_stream.py

Outputs:
- stdout: Text content only (for JSON extraction or status parsing)
- stderr: Comprehensive logging of all Claude activity

Log format (stderr, >>> prefix avoids JSON extraction conflicts):
    >>> INIT model=sonnet, mode=default
    >>> TOOL WebSearch: "query here"
    >>> RESULT WebSearch: 10 links (18.5s)
      - Title
        https://url...
    >>> DONE 3 turns, 48.8s total
"""
import sys
import os
import json

# Force unbuffered output for piped execution (critical for WSL)
os.environ['PYTHONUNBUFFERED'] = '1'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(line_buffering=True)

# Track tool calls to correlate with results
tool_calls = {}  # tool_use_id -> {"name": str, "input": dict}


def log(msg: str) -> None:
    """Log to stderr. Uses >>> prefix to avoid interfering with JSON extraction."""
    print(f">>> {msg}", file=sys.stderr, flush=True)


def format_tool_input(tool_name: str, tool_input: dict) -> str:
    """Format tool input for logging."""
    if tool_name == "WebSearch":
        query = tool_input.get("query", "")
        return f'"{query}"'
    elif tool_name == "WebFetch":
        url = tool_input.get("url", "")
        return url[:100] + ("..." if len(url) > 100 else "")
    elif tool_name == "Read":
        path = tool_input.get("file_path", "")
        return path
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return cmd[:80] + ("..." if len(cmd) > 80 else "")
    elif tool_name == "Edit":
        path = tool_input.get("file_path", "")
        return path
    elif tool_name == "Write":
        path = tool_input.get("file_path", "")
        return path
    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        return f'"{pattern}"'
    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        return pattern
    else:
        # Generic: show first key=value
        if tool_input:
            key = list(tool_input.keys())[0]
            val = str(tool_input[key])[:50]
            return f"{key}={val}"
        return ""


def handle_tool_result(event: dict, tool_id: str, tool_info: dict) -> None:
    """Handle tool result event and log details."""
    tool_name = tool_info.get("name", "unknown")
    result_info = event.get("tool_use_result", {})
    duration = result_info.get("durationSeconds", 0)

    if tool_name == "WebSearch":
        # Extract search results
        results_list = result_info.get("results", [])
        if results_list and isinstance(results_list, list):
            first_result = results_list[0] if results_list else {}
            links = first_result.get("content", []) if isinstance(first_result, dict) else []
            count = len(links) if isinstance(links, list) else 0
            log(f"RESULT WebSearch: {count} links ({duration:.1f}s)")
            # Show top 3 links
            if isinstance(links, list):
                for link in links[:3]:
                    if isinstance(link, dict):
                        title = link.get("title", "")[:60]
                        url = link.get("url", "")
                        log(f"  - {title}")
                        log(f"    {url}")
        else:
            log(f"RESULT WebSearch: ({duration:.1f}s)")

    elif tool_name == "WebFetch":
        # Show fetch result summary
        content = event.get("message", {}).get("content", [])
        if content and isinstance(content, list):
            result_content = content[0].get("content", "") if content else ""
            size = len(result_content) if isinstance(result_content, str) else 0
            log(f"RESULT WebFetch: {size} chars ({duration:.1f}s)")
        else:
            log(f"RESULT WebFetch: ({duration:.1f}s)")

    else:
        log(f"RESULT {tool_name}: ({duration:.1f}s)")


def main() -> None:
    """Main processing loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            event_type = event.get("type", "")

            # Handle system init
            if event_type == "system" and event.get("subtype") == "init":
                model = event.get("model", "unknown")
                # Shorten model name
                if "sonnet" in model.lower():
                    model = "sonnet"
                elif "opus" in model.lower():
                    model = "opus"
                elif "haiku" in model.lower():
                    model = "haiku"
                mode = event.get("permissionMode", "unknown")
                log(f"INIT model={model}, mode={mode}")

            # Handle assistant message with content blocks
            elif event_type == "assistant" and "message" in event:
                msg = event["message"]
                if isinstance(msg, dict) and "content" in msg:
                    for block in msg.get("content", []):
                        if block.get("type") == "text":
                            # Output text to stdout (for JSON extraction)
                            print(block.get("text", ""), end="", flush=True)

                        elif block.get("type") == "tool_use":
                            tool_name = block.get("name", "unknown")
                            tool_id = block.get("id", "")
                            tool_input = block.get("input", {})

                            # Store for correlation with result
                            tool_calls[tool_id] = {"name": tool_name, "input": tool_input}

                            # Log tool call with input
                            input_str = format_tool_input(tool_name, tool_input)
                            if input_str:
                                log(f"TOOL {tool_name}: {input_str}")
                            else:
                                log(f"TOOL {tool_name}")

            # Handle tool results (type: "user" with tool_result content)
            elif event_type == "user":
                msg = event.get("message", {})
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            tool_id = block.get("tool_use_id", "")
                            tool_info = tool_calls.get(tool_id, {"name": "unknown"})
                            handle_tool_result(event, tool_id, tool_info)

            # Handle streaming content block deltas (token-by-token)
            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    print(delta.get("text", ""), end="", flush=True)

            # Handle final result message
            elif event_type == "result":
                duration_ms = event.get("duration_ms", 0)
                num_turns = event.get("num_turns", 0)
                is_error = event.get("is_error", False)

                if is_error:
                    log(f"ERROR {num_turns} turns, {duration_ms/1000:.1f}s")
                else:
                    log(f"DONE {num_turns} turns, {duration_ms/1000:.1f}s total")

                # Also check for text in result
                result = event.get("result", "")
                if isinstance(result, dict):
                    content = result.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "")
                                if text:
                                    print(text, end="", flush=True)

                # Force exit after result - Claude is done, don't wait for stdin EOF
                print(flush=True)
                sys.exit(0)

            # Handle text events directly
            elif event_type == "text":
                text = event.get("text", "")
                if text:
                    print(text, end="", flush=True)

        except json.JSONDecodeError:
            # Not JSON, might be plain text - print it
            if line:
                print(line, flush=True)
        except Exception as e:
            # Log errors but keep processing
            log(f"PARSE_ERROR {e}")

    # Final newline
    print(flush=True)


if __name__ == "__main__":
    main()
