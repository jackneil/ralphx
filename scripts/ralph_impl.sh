#!/bin/bash
#
# ralph_impl.sh - Generic autonomous feature implementation agent
#
# Continuously implements user stories from a JSONL PRD file one at a time,
# tracking progress and handling duplicates/skipped features.
#
# Usage: ./scripts/ralph_impl.sh [OPTIONS]
#
# Options:
#   --prd FILE                 PRD file path (default: design/prd.jsonl)
#   --design FILE              Design document path (default: design/DESIGN.md)
#   --guardrails FILE          Guardrails file path (optional)
#   --phase NUM                Implementation phase filter
#   --category CAT             Specific category filter
#   -n, --iterations NUM       Max iterations (default: 50)
#   -r, --runtime SECS         Max total runtime in seconds (default: 28800 = 8h)
#   -t, --timeout SECS         Per-feature timeout (default: 1800 = 30min)
#   --model MODEL              Model to use (default: opus)
#                              Choices: sonnet, opus, haiku
#   --skip-tests               Skip running tests after implementation
#   -d, --dry-run              Show what would run without executing
#   -h, --help                 Show this help message
#
# Examples:
#   ./scripts/ralph_impl.sh --prd design/prd.jsonl --design design/DESIGN.md
#   ./scripts/ralph_impl.sh --phase 1 --category CORE
#   ./scripts/ralph_impl.sh --model opus -n 10
#   ./scripts/ralph_impl.sh --dry-run
#

set -e
set -o pipefail  # Preserve exit codes through pipes

# Get script directory for finding related files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Lock file for concurrent execution protection
LOCK_FILE="/tmp/ralph_impl.lock"

# Track background job PID for cleanup
CLAUDE_PID=""
INTERRUPTED=false

# Credential swapping for ralph account
CREDENTIALS_FILE="$HOME/.claude/.credentials.json"
RALPH_CREDENTIALS="$HOME/.claude/.credentials.ralph.json"
ORIGINAL_CREDENTIALS=""

# Save original credentials at script start for cleanup restoration
if [ -f "$CREDENTIALS_FILE" ]; then
    ORIGINAL_CREDENTIALS=$(cat "$CREDENTIALS_FILE")
fi

cleanup() {
    if [ "$INTERRUPTED" = true ]; then
        return
    fi
    INTERRUPTED=true

    echo ""
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Received interrupt signal - cleaning up..."

    # Kill Claude process if running
    if [ -n "$CLAUDE_PID" ] && kill -0 "$CLAUDE_PID" 2>/dev/null; then
        kill -TERM "$CLAUDE_PID" 2>/dev/null || true
        sleep 1
        kill -9 "$CLAUDE_PID" 2>/dev/null || true
    fi

    # Kill any child processes
    pkill -P $$ 2>/dev/null || true

    # Restore original credentials if they were swapped
    if [ -n "$ORIGINAL_CREDENTIALS" ]; then
        echo "$ORIGINAL_CREDENTIALS" > "$CREDENTIALS_FILE"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restored original credentials"
    fi

    # Release lock file
    rm -f "$LOCK_FILE"

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleanup complete"
    exit 130
}

trap cleanup SIGINT SIGTERM SIGHUP

acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        local pid=$(cat "$LOCK_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "ERROR: Another ralph_impl process is running (PID $pid)"
            echo "If this is stale, remove $LOCK_FILE manually"
            exit 1
        else
            echo "Removing stale lock file"
            rm -f "$LOCK_FILE"
        fi
    fi
    echo $$ > "$LOCK_FILE"
}

release_lock() {
    rm -f "$LOCK_FILE"
}

# Momentary swap: swap to ralph, start claude, swap back immediately
# The running claude process keeps auth in memory
run_claude_as_ralph() {
    local cmd="$1"

    if [ ! -f "$RALPH_CREDENTIALS" ]; then
        log "INFO: Using default account (no ralph credentials at $RALPH_CREDENTIALS)"
        eval "$cmd"
        return $?
    fi

    # Save original credentials
    ORIGINAL_CREDENTIALS=$(cat "$CREDENTIALS_FILE")

    # Swap to ralph credentials
    cp "$RALPH_CREDENTIALS" "$CREDENTIALS_FILE"

    # Run claude synchronously
    eval "$cmd"
    local exit_code=$?

    # Restore original credentials
    echo "$ORIGINAL_CREDENTIALS" > "$CREDENTIALS_FILE"

    return $exit_code
}

# Defaults
MAX_ITERATIONS=50
MAX_RUNTIME_SECONDS=28800       # 8 hours
FEATURE_TIMEOUT=1800            # 30 minutes per feature
CLAUDE_MODEL="opus"
SKIP_TESTS=false
DRY_RUN=false
PRD_FILE="design/prd.jsonl"
DESIGN_FILE="design/DESIGN.md"
GUARDRAILS_FILE=""
LOG_FILE="ralph_impl.log"
PROGRESS_FILE="ralph_progress.txt"
IMPL_PHASE=""
IMPL_CATEGORY=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --prd)
            PRD_FILE="$2"
            shift 2
            ;;
        --design)
            DESIGN_FILE="$2"
            shift 2
            ;;
        --guardrails)
            GUARDRAILS_FILE="$2"
            shift 2
            ;;
        --phase)
            IMPL_PHASE="$2"
            shift 2
            ;;
        --category)
            IMPL_CATEGORY="$2"
            shift 2
            ;;
        -n|--iterations)
            MAX_ITERATIONS="$2"
            shift 2
            ;;
        -r|--runtime)
            MAX_RUNTIME_SECONDS="$2"
            shift 2
            ;;
        -t|--timeout)
            FEATURE_TIMEOUT="$2"
            shift 2
            ;;
        --model)
            CLAUDE_MODEL="$2"
            shift 2
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            head -35 "$0" | tail -30
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage"
            exit 1
            ;;
    esac
done

# State
START_TIME=$(date +%s)
ITERATION=0
IMPLEMENTED_COUNT=0
DUP_COUNT=0
SKIPPED_COUNT=0
ERROR_COUNT=0

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

format_duration() {
    local secs=$1
    if [ $secs -ge 3600 ]; then
        echo "$((secs / 3600))h $((secs % 3600 / 60))m"
    elif [ $secs -ge 60 ]; then
        echo "$((secs / 60))m $((secs % 60))s"
    else
        echo "${secs}s"
    fi
}

check_timeout() {
    local elapsed=$(($(date +%s) - START_TIME))
    if [ $elapsed -ge $MAX_RUNTIME_SECONDS ]; then
        log "TIMEOUT: Max runtime exceeded (${elapsed}s / ${MAX_RUNTIME_SECONDS}s)"
        release_lock
        exit 0
    fi
}

check_uncommitted_changes() {
    if ! git diff --quiet 2>/dev/null; then
        log "WARNING: Uncommitted changes detected from previous session"
        log "Changed files:"
        git diff --name-only | head -10 | while read f; do log "  - $f"; done

        echo ""
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log "Aborting. Run 'git stash' or 'git checkout -- .' to clean up"
            exit 1
        fi
    fi
}

# Build the implementation prompt
build_impl_prompt() {
    local story_json="$1"

    # Extract fields from JSON
    local story_id=$(echo "$story_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))")
    local priority=$(echo "$story_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('priority',0))")
    local story_text=$(echo "$story_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('story',''))")
    local notes=$(echo "$story_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('notes',''))")
    local category=$(echo "$story_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('category',''))")

    # Format acceptance criteria as numbered list
    local acceptance_criteria=$(echo "$story_json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
criteria = d.get('acceptance_criteria', [])
for i, c in enumerate(criteria, 1):
    print(f'{i}. {c}')
")

    # Get implemented summary
    local implemented_summary=$(python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" implemented-summary 2>/dev/null || echo "No stories implemented yet.")

    # Get design document
    local design_doc=""
    if [ -f "$DESIGN_FILE" ]; then
        design_doc=$(cat "$DESIGN_FILE")
    else
        design_doc="Design document not found."
    fi

    # Get guardrails (optional)
    local guardrails=""
    if [ -n "$GUARDRAILS_FILE" ] && [ -f "$GUARDRAILS_FILE" ]; then
        guardrails="## GUARDRAILS

Review the following guardrails for implementation standards:

$(cat "$GUARDRAILS_FILE")

---"
    fi

    # Read template and inject
    local template=$(cat "$SCRIPT_DIR/PROMPT_IMPL.md")

    IMPL_PROMPT="${template//\{STORY_ID\}/$story_id}"
    IMPL_PROMPT="${IMPL_PROMPT//\{PRIORITY\}/$priority}"
    IMPL_PROMPT="${IMPL_PROMPT//\{CATEGORY\}/$category}"
    IMPL_PROMPT="${IMPL_PROMPT//\{STORY_TEXT\}/$story_text}"
    IMPL_PROMPT="${IMPL_PROMPT//\{NOTES\}/$notes}"
    IMPL_PROMPT="${IMPL_PROMPT//\{ACCEPTANCE_CRITERIA\}/$acceptance_criteria}"
    IMPL_PROMPT="${IMPL_PROMPT//\{IMPLEMENTED_SUMMARY\}/$implemented_summary}"
    IMPL_PROMPT="${IMPL_PROMPT//\{DESIGN_DOC\}/$design_doc}"
    IMPL_PROMPT="${IMPL_PROMPT//\{GUARDRAILS\}/$guardrails}"

    echo "$story_id"
}

# Parse Claude output for status
parse_output_status() {
    local output="$1"

    # Strip markdown bold markers and terminal sequences
    local clean_output=$(echo "$output" | sed 's/\*\*//g' | sed $'s/\x1b\\[I//g' | sed $'s/\x1b\\[O//g')

    # Check for context overflow FIRST
    if echo "$clean_output" | grep -qi "Prompt is too long\|context length exceeded"; then
        echo "overflow"
        echo "Context overflow - story too complex for single-shot implementation"
        return
    fi

    # Look for delimiter-based status (preferred - more reliable)
    local delimited=$(echo "$clean_output" | sed -n '/###RALPH_IMPL_RESULT_7f3a9b2e###/,/###END_RALPH_RESULT###/p')
    if [ -n "$delimited" ]; then
        if echo "$delimited" | grep -qE "IMPLEMENTED:"; then
            echo "implemented"
            echo "$delimited" | grep -E "IMPLEMENTED:" | head -1 | sed 's/.*IMPLEMENTED: *//'
            return
        elif echo "$delimited" | grep -qE "DUP_OF:"; then
            echo "dup"
            echo "$delimited" | grep -E "DUP_OF:" | head -1 | sed 's/.*DUP_OF: *//'
            return
        elif echo "$delimited" | grep -qE "SKIPPED:"; then
            echo "skipped"
            echo "$delimited" | grep -E "SKIPPED:" | head -1 | sed 's/.*SKIPPED: *//'
            return
        elif echo "$delimited" | grep -qE "ERROR:"; then
            echo "error"
            echo "$delimited" | grep -E "ERROR:" | head -1 | sed 's/.*ERROR: *//'
            return
        fi
    fi

    # Fallback: Look for status lines without delimiters
    if echo "$clean_output" | grep -qE "^IMPLEMENTED:"; then
        echo "implemented"
        echo "$clean_output" | grep -E "^IMPLEMENTED:" | head -1 | sed 's/^IMPLEMENTED: *//'
    elif echo "$clean_output" | grep -qE "^DUP_OF:"; then
        local parent=$(echo "$clean_output" | grep -E "^DUP_OF:" | head -1 | sed 's/^DUP_OF: *//')
        echo "dup"
        echo "$parent"
    elif echo "$clean_output" | grep -qE "^SKIPPED:"; then
        echo "skipped"
        echo "$clean_output" | grep -E "^SKIPPED:" | head -1 | sed 's/^SKIPPED: *//'
    else
        echo "unknown"
        echo ""
    fi
}

# Build a recovery prompt when context overflow occurs
build_recovery_prompt() {
    local story_id="$1"
    local story_text="$2"
    local acceptance_criteria="$3"
    local notes="$4"

    # Get files changed since last commit
    local changed_files=$(git diff --name-only HEAD 2>/dev/null)
    local changed_diffs=""

    if [ -n "$changed_files" ]; then
        changed_diffs=$(git diff HEAD 2>/dev/null | head -500)
    fi

    # Get design document
    local design_doc=""
    if [ -f "$DESIGN_FILE" ]; then
        design_doc=$(cat "$DESIGN_FILE")
    fi

    # Get implemented summary
    local implemented_summary=$(python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" implemented-summary 2>/dev/null || echo "No stories implemented yet.")

    cat << RECOVERY_EOF
# Continue Implementation: $story_id

## CONTEXT
You were implementing this story but ran out of context during implementation.
Continue from where you left off.

## FILES ALREADY MODIFIED
The following files have been changed. Review them to understand your progress:

$changed_files

### Diffs (truncated if large):
\`\`\`diff
$changed_diffs
\`\`\`

## ORIGINAL TASK
**Story:** $story_text

## ACCEPTANCE CRITERIA
$acceptance_criteria

## NOTES
$notes

## ALREADY IMPLEMENTED FEATURES
$implemented_summary

## PROJECT DESIGN DOCUMENT
$design_doc

## INSTRUCTION
1. Review the files already modified above
2. Continue implementing any remaining functionality
3. Run tests to verify nothing is broken
4. Output your status using the standard format:

###RALPH_IMPL_RESULT_7f3a9b2e###
IMPLEMENTED: Brief description of what was completed
###END_RALPH_RESULT###

Or if there's an issue:
###RALPH_IMPL_RESULT_7f3a9b2e###
SKIPPED: reason
###END_RALPH_RESULT###
RECOVERY_EOF
}

# Build the next-pending command with phase/category filters
get_next_story_cmd() {
    local cmd="python3 $SCRIPT_DIR/prd_manager.py --prd $PRD_FILE next-pending-ordered"

    if [ -n "$IMPL_PHASE" ]; then
        cmd="$cmd --phase $IMPL_PHASE"
    fi

    if [ -n "$IMPL_CATEGORY" ]; then
        cmd="$cmd --category $IMPL_CATEGORY"
    fi

    echo "$cmd"
}

show_config() {
    echo ""
    echo "=========================================="
    echo "  RALPH IMPL - Feature Implementation Agent"
    echo "=========================================="
    echo "Configuration:"
    echo "  Model:          $CLAUDE_MODEL"
    if [ -f "$RALPH_CREDENTIALS" ]; then
        echo "  Account:        ralph (separate credentials)"
    else
        echo "  Account:        default"
    fi
    if [ -n "$IMPL_PHASE" ]; then
        if [ -n "$IMPL_CATEGORY" ]; then
            echo "  Phase:          $IMPL_PHASE (category: $IMPL_CATEGORY)"
        else
            echo "  Phase:          $IMPL_PHASE (all categories)"
        fi
    else
        echo "  Phase:          all (priority order)"
    fi
    echo "  Timeout:        $(format_duration $FEATURE_TIMEOUT) per feature"
    echo "  Max iterations: $MAX_ITERATIONS"
    echo "  Max runtime:    $(format_duration $MAX_RUNTIME_SECONDS)"
    echo "  Skip tests:     $SKIP_TESTS"
    echo ""
    echo "Files:"
    echo "  PRD:        $PRD_FILE"
    echo "  Design Doc: $DESIGN_FILE"
    if [ -n "$GUARDRAILS_FILE" ]; then
        echo "  Guardrails: $GUARDRAILS_FILE"
    fi
    echo "  Log:        $LOG_FILE"
    echo "  Progress:   $PROGRESS_FILE"
    echo ""
}

log_progress() {
    local story_id="$1"
    local priority="$2"
    local story_text="$3"
    local status="$4"
    local duration="$5"
    local details="$6"

    {
        echo ""
        echo "--- $story_id (priority: $priority) ---"
        echo "Story: $story_text"
        echo "Status: $status"
        echo "Duration: $duration"
        echo "Details: $details"
        echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
    } >> "$PROGRESS_FILE"
}

cleanup_rogue_files() {
    # Clean up temp files Claude may create
    find . -maxdepth 2 -type f \( \
        -name "temp_*.py" -o \
        -name "temp_*.sh" -o \
        -name "*.tmp" \
    \) -delete 2>/dev/null || true
}

main() {
    # Acquire lock to prevent concurrent execution
    acquire_lock

    show_config | tee -a "$LOG_FILE"

    # Verify required files
    if [ ! -f "$SCRIPT_DIR/prd_manager.py" ]; then
        log "ERROR: prd_manager.py not found in $SCRIPT_DIR"
        release_lock
        exit 1
    fi
    if [ ! -f "$SCRIPT_DIR/PROMPT_IMPL.md" ]; then
        log "ERROR: PROMPT_IMPL.md not found in $SCRIPT_DIR"
        release_lock
        exit 1
    fi
    if [ ! -f "$PRD_FILE" ]; then
        log "ERROR: PRD file not found: $PRD_FILE"
        release_lock
        exit 1
    fi
    if [ ! -f "$DESIGN_FILE" ]; then
        log "ERROR: Design document not found: $DESIGN_FILE"
        release_lock
        exit 1
    fi

    # Check for uncommitted changes from crashed session
    check_uncommitted_changes

    # Get initial counts
    local pending_count=$(python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" pending-count)
    log "Starting - $pending_count stories pending"

    # Start progress file session
    {
        echo ""
        echo "=== Implementation Session: $(date '+%Y-%m-%d %H:%M:%S') ==="
        echo "Stories pending: $pending_count"
    } >> "$PROGRESS_FILE"

    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Getting next pending story..."
        local next_cmd=$(get_next_story_cmd)
        log "[DRY RUN] Command: $next_cmd"
        local next_story=$($next_cmd 2>&1)
        if [ "$next_story" = "{}" ]; then
            if [ -n "$IMPL_PHASE" ]; then
                log "[DRY RUN] Phase $IMPL_PHASE ${IMPL_CATEGORY:+category $IMPL_CATEGORY }complete!"
            else
                log "[DRY RUN] No pending stories!"
            fi
        else
            local story_id=$(echo "$next_story" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))")
            local priority=$(echo "$next_story" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('priority',0))")
            local story_text=$(echo "$next_story" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('story',''))")
            log "[DRY RUN] Next story: $story_id (priority $priority)"
            log "[DRY RUN] Story: $story_text"
        fi
        release_lock
        exit 0
    fi

    # Main loop
    while [ $ITERATION -lt $MAX_ITERATIONS ]; do
        ITERATION=$((ITERATION + 1))
        local elapsed=$(($(date +%s) - START_TIME))

        log ""
        log "=== Iteration $ITERATION/$MAX_ITERATIONS ($(format_duration $elapsed) elapsed) ==="

        check_timeout

        # Get next pending story using dependency-aware ordering
        local next_cmd=$(get_next_story_cmd)
        local next_story=$($next_cmd 2>&1)

        if [ "$next_story" = "{}" ]; then
            if [ -n "$IMPL_PHASE" ]; then
                log "Phase $IMPL_PHASE ${IMPL_CATEGORY:+category $IMPL_CATEGORY }complete!"
            else
                log "No more pending stories - all done!"
            fi
            break
        fi

        # Extract story details
        local story_id=$(echo "$next_story" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))")
        local priority=$(echo "$next_story" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('priority',0))")
        local story_text=$(echo "$next_story" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('story','')[:100])")

        log "Implementing: $story_id (priority $priority)"
        log "Story: $story_text..."

        # Build implementation prompt
        build_impl_prompt "$next_story" > /dev/null
        local current_story_id="$story_id"

        # Run Claude
        local iter_start=$(date +%s)
        local temp_output=$(mktemp)
        local prompt_file=$(mktemp)

        printf '%s' "$IMPL_PROMPT" > "$prompt_file"

        # Log prompt size
        local prompt_chars=$(wc -c < "$prompt_file")
        local prompt_lines=$(wc -l < "$prompt_file")
        local prompt_tokens_est=$((prompt_chars / 4))
        log "Prompt size: ${prompt_chars} chars, ${prompt_lines} lines, ~${prompt_tokens_est} tokens (estimated)"

        log "Running Claude ($CLAUDE_MODEL, timeout $(format_duration $FEATURE_TIMEOUT))..."

        # Run Claude with stream-json for live output
        local claude_exit=0
        run_claude_as_ralph "timeout $FEATURE_TIMEOUT claude -p --model '$CLAUDE_MODEL' --verbose --output-format stream-json < '$prompt_file' 2>&1 | tee '$temp_output' | python3 '$SCRIPT_DIR/parse_stream.py' 2>&1" &
        CLAUDE_PID=$!
        wait $CLAUDE_PID || claude_exit=$?
        CLAUDE_PID=""

        if [ "$INTERRUPTED" = true ]; then
            rm -f "$prompt_file" "$temp_output"
            break
        fi

        # Extract text from JSONL output
        local RAW_OUTPUT=$(cat "$temp_output" 2>/dev/null || echo "")
        local OUTPUT=""

        if echo "$RAW_OUTPUT" | grep -qi "Prompt is too long\|context length exceeded"; then
            OUTPUT="$RAW_OUTPUT"
        else
            OUTPUT=$(echo "$RAW_OUTPUT" | jq -r '(select(.type == "assistant") | .message.content[]? | select(.type == "text") | .text), (select(.type == "result") | .result)' 2>/dev/null | tr -d '\0' || echo "$RAW_OUTPUT")
        fi

        # Parse output for status
        local status_result=$(parse_output_status "$OUTPUT")
        local status=$(echo "$status_result" | head -1)
        local details=$(echo "$status_result" | tail -1)

        # Handle context overflow
        if [[ "$status" == "overflow" ]]; then
            log "Context overflow - building recovery prompt..."

            local ac=$(echo "$next_story" | jq -r '.acceptance_criteria // empty')
            local notes=$(echo "$next_story" | jq -r '.notes // empty')

            local recovery_prompt=$(build_recovery_prompt "$current_story_id" "$story_text" "$ac" "$notes")
            echo "$recovery_prompt" > "$prompt_file"

            log "Retrying with opus (fresh context)..."
            claude_exit=0
            run_claude_as_ralph "timeout $FEATURE_TIMEOUT claude -p --model 'opus' --verbose --output-format stream-json < '$prompt_file' 2>&1 | tee '$temp_output' | python3 '$SCRIPT_DIR/parse_stream.py' 2>&1" &
            CLAUDE_PID=$!
            wait $CLAUDE_PID || claude_exit=$?
            CLAUDE_PID=""

            RAW_OUTPUT=$(cat "$temp_output" 2>/dev/null || echo "")
            if echo "$RAW_OUTPUT" | grep -qi "Prompt is too long\|context length exceeded"; then
                OUTPUT="$RAW_OUTPUT"
            else
                OUTPUT=$(echo "$RAW_OUTPUT" | jq -r '(select(.type == "assistant") | .message.content[]? | select(.type == "text") | .text), (select(.type == "result") | .result)' 2>/dev/null | tr -d '\0' || echo "$RAW_OUTPUT")
            fi
            status_result=$(parse_output_status "$OUTPUT")
            status=$(echo "$status_result" | head -1)
            details=$(echo "$status_result" | tail -1)

            if [[ "$status" == "overflow" ]]; then
                status="skipped"
                details="Context overflow even with recovery prompt"
            fi
        fi

        rm -f "$prompt_file" "$temp_output"

        local iter_elapsed=$(($(date +%s) - iter_start))
        local duration_str=$(format_duration $iter_elapsed)

        # Validate DUP_OF
        if [[ "$status" == "dup" && "$details" == "$current_story_id" ]]; then
            log "WARNING: Story cannot be DUP_OF itself, marking as skipped"
            status="skipped"
            details="Story referenced itself as duplicate"
        fi

        if [[ "$status" == "dup" ]]; then
            local target_status=$(python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" get-status "$details" 2>/dev/null)
            if [[ "$target_status" != "implemented" ]]; then
                log "WARNING: DUP_OF target '$details' is not implemented, marking as skipped"
                status="skipped"
                details="Invalid DUP_OF reference - target not implemented"
            fi
        fi

        case "$status" in
            implemented)
                log "IMPLEMENTED: $details"
                python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" mark-implemented "$current_story_id" "$details" 2>&1 | tee -a "$LOG_FILE"
                IMPLEMENTED_COUNT=$((IMPLEMENTED_COUNT + 1))

                # Git commit
                if git diff --quiet 2>/dev/null; then
                    log "No file changes to commit"
                else
                    git add -A 2>/dev/null
                    git commit -m "Implement $current_story_id

$story_text

Co-Authored-By: Claude <noreply@anthropic.com>" 2>&1 | tee -a "$LOG_FILE" || true
                    log "Files changed:"
                    git diff --stat HEAD~1 2>/dev/null | tee -a "$LOG_FILE"
                fi

                log_progress "$current_story_id" "$priority" "$story_text" "IMPLEMENTED" "$duration_str" "$details"
                ;;
            dup)
                log "DUPLICATE OF: $details"
                python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" mark-dup "$current_story_id" "$details" 2>&1 | tee -a "$LOG_FILE"
                DUP_COUNT=$((DUP_COUNT + 1))
                log_progress "$current_story_id" "$priority" "$story_text" "DUP_OF" "$duration_str" "$details"
                ;;
            skipped)
                log "SKIPPED: $details"
                python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" mark-skipped "$current_story_id" "$details" 2>&1 | tee -a "$LOG_FILE"
                SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
                log_progress "$current_story_id" "$priority" "$story_text" "SKIPPED" "$duration_str" "$details"
                ;;
            error)
                log "ERROR: $details"
                ERROR_COUNT=$((ERROR_COUNT + 1))
                log_progress "$current_story_id" "$priority" "$story_text" "ERROR" "$duration_str" "$details"
                ;;
            *)
                log "WARNING: Could not parse output status"
                log "Output preview: $(echo "$OUTPUT" | tail -20)"
                ERROR_COUNT=$((ERROR_COUNT + 1))
                log_progress "$current_story_id" "$priority" "$story_text" "ERROR" "$duration_str" "Could not parse status"
                ;;
        esac

        log "Completed in $duration_str"

        # Cleanup rogue files
        cleanup_rogue_files

        # Brief pause between iterations
        sleep 3
    done

    # Final summary
    log ""
    log "=========================================="
    log "  IMPLEMENTATION SESSION COMPLETE"
    log "=========================================="
    local total_elapsed=$(($(date +%s) - START_TIME))
    local final_pending=$(python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" pending-count)
    log "Iterations:  $ITERATION"
    log "Runtime:     $(format_duration $total_elapsed)"
    log "Implemented: $IMPLEMENTED_COUNT"
    log "Duplicates:  $DUP_COUNT"
    log "Skipped:     $SKIPPED_COUNT"
    log "Errors:      $ERROR_COUNT"
    log "Remaining:   $final_pending pending"

    # Append to progress file
    {
        echo ""
        echo "=== Session Summary ==="
        echo "Implemented: $IMPLEMENTED_COUNT"
        echo "Duplicates: $DUP_COUNT"
        echo "Skipped: $SKIPPED_COUNT"
        echo "Errors: $ERROR_COUNT"
        echo "Remaining: $final_pending"
    } >> "$PROGRESS_FILE"

    release_lock
    exit 0
}

main "$@"
