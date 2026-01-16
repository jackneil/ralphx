#!/bin/bash
#
# ralph_plan.sh - Generic PRD/story generation agent
#
# Continuously generates user stories from a design document using Claude,
# appending to a JSONL PRD file.
#
# Usage: ./scripts/ralph_plan.sh [OPTIONS]
#
# Options:
#   --prd FILE                 PRD file path (default: design/prd.jsonl)
#   --design FILE              Design document path (default: design/DESIGN.md)
#   --category CAT             Force specific category
#   --mode MODE                Mode: turbo (no web) or deep (web research)
#   -n, --iterations NUM       Max iterations (default: 20)
#   -r, --runtime SECS         Max total runtime (default: 7200 = 2h)
#   -t, --timeout SECS         Per-iteration timeout (default: 600 = 10min)
#   --model MODEL              Model: sonnet, opus, haiku (default: sonnet)
#   --min-stories NUM          Min stories per iteration (default: 5)
#   --max-stories NUM          Max stories per iteration (default: 15)
#   -d, --dry-run              Show config without executing
#   -h, --help                 Show this help message
#
# Examples:
#   ./scripts/ralph_plan.sh --design design/DESIGN.md
#   ./scripts/ralph_plan.sh --mode turbo --category CORE
#   ./scripts/ralph_plan.sh --mode deep -n 5
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Track background job PID for cleanup
CLAUDE_PID=""
INTERRUPTED=false

# Credential swapping
CREDENTIALS_FILE="$HOME/.claude/.credentials.json"
RALPH_CREDENTIALS="$HOME/.claude/.credentials.ralph.json"
ORIGINAL_CREDENTIALS=""

if [ -f "$CREDENTIALS_FILE" ]; then
    ORIGINAL_CREDENTIALS=$(cat "$CREDENTIALS_FILE")
fi

cleanup() {
    if [ "$INTERRUPTED" = true ]; then
        return
    fi
    INTERRUPTED=true

    echo ""
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleaning up..."

    if [ -n "$CLAUDE_PID" ] && kill -0 "$CLAUDE_PID" 2>/dev/null; then
        kill -TERM "$CLAUDE_PID" 2>/dev/null || true
        sleep 1
        kill -9 "$CLAUDE_PID" 2>/dev/null || true
    fi

    pkill -P $$ 2>/dev/null || true

    if [ -n "$ORIGINAL_CREDENTIALS" ]; then
        echo "$ORIGINAL_CREDENTIALS" > "$CREDENTIALS_FILE"
    fi

    exit 130
}

trap cleanup SIGINT SIGTERM SIGHUP

run_claude_as_ralph() {
    local cmd="$1"

    if [ ! -f "$RALPH_CREDENTIALS" ]; then
        eval "$cmd" &
        CLAUDE_PID=$!
        wait $CLAUDE_PID 2>/dev/null
        return $?
    fi

    ORIGINAL_CREDENTIALS=$(cat "$CREDENTIALS_FILE")
    cp "$RALPH_CREDENTIALS" "$CREDENTIALS_FILE"

    eval "$cmd" &
    CLAUDE_PID=$!

    sleep 0.5
    echo "$ORIGINAL_CREDENTIALS" > "$CREDENTIALS_FILE"

    wait $CLAUDE_PID 2>/dev/null
    return $?
}

# Defaults
MAX_ITERATIONS=20
MAX_RUNTIME_SECONDS=7200
ITERATION_TIMEOUT=600
CLAUDE_MODEL="sonnet"
PRD_FILE="design/prd.jsonl"
DESIGN_FILE="design/DESIGN.md"
LOG_FILE="ralph_plan.log"
FORCE_MODE="turbo"
FORCE_CATEGORY=""
MIN_STORIES=5
MAX_STORIES=15
DRY_RUN=false

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
        --category)
            FORCE_CATEGORY="$2"
            shift 2
            ;;
        --mode)
            FORCE_MODE="$2"
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
            ITERATION_TIMEOUT="$2"
            shift 2
            ;;
        --model)
            CLAUDE_MODEL="$2"
            shift 2
            ;;
        --min-stories)
            MIN_STORIES="$2"
            shift 2
            ;;
        --max-stories)
            MAX_STORIES="$2"
            shift 2
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            head -30 "$0" | tail -25
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

START_TIME=$(date +%s)
ITERATION=0
TOTAL_ADDED=0

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
        log "TIMEOUT: Max runtime exceeded"
        exit 0
    fi
}

# Get existing IDs for a category
get_existing_stories() {
    local category="$1"
    python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" ids 2>/dev/null | tr ',' '\n' | grep "^${category}-" | while read id; do
        local story=$(python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" get-story "$id" 2>/dev/null | jq -r '.story // ""' 2>/dev/null | head -c 100)
        echo "- $id: $story"
    done
}

# Get next ID for a category
get_next_id() {
    local category="$1"
    local max_num=$(python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" ids 2>/dev/null | tr ',' '\n' | grep "^${category}-" | sed "s/${category}-//" | sort -n | tail -1)
    if [ -z "$max_num" ]; then
        echo "${category}-001"
    else
        printf "%s-%03d" "$category" $((max_num + 1))
    fi
}

build_prompt() {
    local category="$1"
    local mode="$2"

    local design_doc=""
    if [ -f "$DESIGN_FILE" ]; then
        design_doc=$(cat "$DESIGN_FILE")
    fi

    local existing_stories=$(get_existing_stories "$category")
    local next_id=$(get_next_id "$category")

    # Build mode-specific instruction
    local mode_instruction=""
    local mode_restrictions=""

    if [ "$mode" = "turbo" ]; then
        mode_instruction="Read the ENTIRE design document below and extract ALL user stories for the $category category."
        mode_restrictions="- Do NOT use web search - all info is in the design document"
    else
        mode_instruction="Do web research to find NEW user stories for the $category category that fill gaps not covered by the design document."
        mode_restrictions="- Do NOT write stories for features already fully specified in the design doc
- Do NOT write to any files"
    fi

    cat << PROMPT_EOF
# Generate $category Stories

## YOUR TASK
$mode_instruction

## RULES

**YOU MUST:**
- Generate $MIN_STORIES-$MAX_STORIES NEW user stories for the $category category
- Use IDs starting at: $next_id
- Output ONLY a raw JSON array at the end - no markdown, no explanation, no code fences

**YOU MUST NOT:**
- Create stories for other categories
- Duplicate existing stories listed below
$mode_restrictions
- Output anything except the JSON array

## EXISTING $category STORIES (do not duplicate these)

$existing_stories

## PROJECT DESIGN DOCUMENT

$design_doc

## OUTPUT FORMAT

Output a raw JSON array (NO markdown fences, NO explanation):

[{"id":"$category-XXX","priority":50,"story":"As a [role], I can [action] so that [benefit]","acceptance_criteria":["Criterion 1","Criterion 2"],"status":"pending","category":"$category","notes":"Source: design doc"}]

## PRIORITY GUIDE
- 1-20: Core infrastructure
- 21-40: Essential workflow
- 41-60: Important features
- 61-80: Advanced features
- 81-100: Nice-to-have

OUTPUT THE JSON ARRAY NOW:
PROMPT_EOF
}

show_config() {
    echo ""
    echo "=========================================="
    echo "  RALPH PLAN - Story Generation Agent"
    echo "=========================================="
    echo "Configuration:"
    echo "  Model:          $CLAUDE_MODEL"
    echo "  Mode:           $FORCE_MODE"
    if [ -n "$FORCE_CATEGORY" ]; then
        echo "  Category:       $FORCE_CATEGORY"
    else
        echo "  Category:       (auto-select)"
    fi
    echo "  Timeout:        $(format_duration $ITERATION_TIMEOUT) per iteration"
    echo "  Max iterations: $MAX_ITERATIONS"
    echo "  Max runtime:    $(format_duration $MAX_RUNTIME_SECONDS)"
    echo "  Stories/iter:   $MIN_STORIES-$MAX_STORIES"
    echo ""
    echo "Files:"
    echo "  PRD:        $PRD_FILE"
    echo "  Design Doc: $DESIGN_FILE"
    echo "  Log:        $LOG_FILE"
    echo ""
}

main() {
    show_config | tee -a "$LOG_FILE"

    # Verify files
    if [ ! -f "$DESIGN_FILE" ]; then
        log "ERROR: Design document not found: $DESIGN_FILE"
        exit 1
    fi

    # Create PRD file if it doesn't exist
    if [ ! -f "$PRD_FILE" ]; then
        mkdir -p "$(dirname "$PRD_FILE")"
        touch "$PRD_FILE"
        log "Created PRD file: $PRD_FILE"
    fi

    local initial_count=$(python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" count 2>/dev/null || echo "0")
    log "Starting - $initial_count stories in PRD"

    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would generate stories for category: ${FORCE_CATEGORY:-auto}"
        log "[DRY RUN] Mode: $FORCE_MODE"
        exit 0
    fi

    # Main loop
    while [ $ITERATION -lt $MAX_ITERATIONS ]; do
        ITERATION=$((ITERATION + 1))
        local elapsed=$(($(date +%s) - START_TIME))

        log ""
        log "=== Iteration $ITERATION/$MAX_ITERATIONS ($(format_duration $elapsed) elapsed) ==="

        check_timeout

        # Select category
        local category="$FORCE_CATEGORY"
        if [ -z "$category" ]; then
            # Default to CORE if no category specified
            category="CORE"
        fi

        log "Generating $FORCE_MODE stories for category: $category"

        # Build prompt
        local prompt=$(build_prompt "$category" "$FORCE_MODE")
        local prompt_file=$(mktemp)
        local output_file=$(mktemp)

        echo "$prompt" > "$prompt_file"

        # Set tool restrictions based on mode
        local tool_flags=""
        if [ "$FORCE_MODE" = "turbo" ]; then
            tool_flags="--allowedTools ''"
        else
            tool_flags="--allowedTools 'WebSearch,WebFetch'"
        fi

        log "Running Claude ($CLAUDE_MODEL, timeout $(format_duration $ITERATION_TIMEOUT))..."

        local iter_start=$(date +%s)
        local claude_exit=0
        run_claude_as_ralph "timeout $ITERATION_TIMEOUT claude -p --model '$CLAUDE_MODEL' --verbose $tool_flags < '$prompt_file' > '$output_file' 2>&1" || claude_exit=$?

        if [ "$INTERRUPTED" = true ]; then
            rm -f "$prompt_file" "$output_file"
            break
        fi

        local output=$(cat "$output_file")
        rm -f "$prompt_file" "$output_file"

        local iter_elapsed=$(($(date +%s) - iter_start))
        log "Claude completed in $(format_duration $iter_elapsed)"

        # Extract JSON from output
        local json_output=$(echo "$output" | python3 "$SCRIPT_DIR/extract_json.py" 2>/dev/null)

        if [ -z "$json_output" ] || [ "$json_output" = "null" ]; then
            log "ERROR: Could not extract JSON from output"
            log "Output preview: $(echo "$output" | tail -10)"
            continue
        fi

        # Count stories before append
        local count_before=$(python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" count 2>/dev/null || echo "0")

        # Append to PRD
        echo "$json_output" | python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" append 2>&1 | tee -a "$LOG_FILE"

        local count_after=$(python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" count 2>/dev/null || echo "0")
        local added=$((count_after - count_before))
        TOTAL_ADDED=$((TOTAL_ADDED + added))

        log "Added $added stories (total: $count_after)"

        # Brief pause between iterations
        sleep 2
    done

    # Final summary
    log ""
    log "=========================================="
    log "  PLANNING SESSION COMPLETE"
    log "=========================================="
    local total_elapsed=$(($(date +%s) - START_TIME))
    local final_count=$(python3 "$SCRIPT_DIR/prd_manager.py" --prd "$PRD_FILE" count 2>/dev/null || echo "0")
    log "Iterations: $ITERATION"
    log "Runtime:    $(format_duration $total_elapsed)"
    log "Added:      $TOTAL_ADDED stories"
    log "Total PRD:  $final_count stories"

    exit 0
}

main "$@"
