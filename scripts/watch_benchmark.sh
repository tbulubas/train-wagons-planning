#!/usr/bin/env bash
# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

# Live view of the system load and of the progress of scripts/benchmark.py.
#
# Usage: scripts/watch_benchmark.sh [interval] [total] [results]
#
# Refreshes every `interval` seconds (default 5): CPU and memory of the
# machine, every running Python process with its CPU share, memory and CPU
# time, and for every results file in `results` (default docs/benchmark) the
# number of finished instances out of `total` (default 70), the last result
# and the time since it was written. Stop with Ctrl+C.
#
# Runs in Git Bash on Windows (processes from tasklist) and on Linux (ps).

set -u
interval=${1:-5}
total=${2:-70}
results=${3:-docs/benchmark}
cores=$(nproc)

# busy and total CPU ticks of the whole machine
cpu_ticks() { awk '/^cpu / { print $2 + $3 + $4, $2 + $3 + $4 + $5 }' /proc/stat; }

# one line per Python process: pid, memory in kB, CPU seconds, command
python_processes() {
    if command -v tasklist > /dev/null 2>&1; then
        tasklist //V //FO CSV //NH //FI "IMAGENAME eq python.exe" 2> /dev/null | tr -d '\r' | awk '
            /^"python/ {
                sub(/^"/, ""); sub(/"$/, ""); n = split($0, f, /","/)
                mem = f[5]; gsub(/[^0-9]/, "", mem)
                split(f[8], t, ":"); seconds = t[1] * 3600 + t[2] * 60 + t[3]
                print f[2], mem, seconds, "python.exe"
            }'
    else
        ps -C python -C python3 -o pid=,rss=,time=,args= 2> /dev/null | awk '{
            n = split($3, t, /[-:]/); seconds = 0
            if (n == 4) seconds = t[1] * 86400 + t[2] * 3600 + t[3] * 60 + t[4]
            else seconds = t[1] * 3600 + t[2] * 60 + t[3]
            command = ""; for (i = 4; i <= NF; i++) command = command " " $i
            print $1, $2, seconds, substr(command, 2, 60)
        }'
    fi
}

declare -A previous
read -r busy0 all0 < <(cpu_ticks)
sleep 1

while true; do
    read -r busy all < <(cpu_ticks)
    load=$(( all > all0 ? 100 * (busy - busy0) / (all - all0) : 0 ))
    busy0=$busy all0=$all
    memory=$(awk '/^MemTotal/ { t = $2 } /^MemFree/ { f = $2 }
                  END { printf "%.1f / %.1f GB", (t - f) / 1048576, t / 1048576 }' /proc/meminfo)

    out=$(printf 'System  %s   CPU %3d %%   memory %s   (%d logical CPUs)' \
        "$(date +%H:%M:%S)" "$load" "$memory" "$cores")
    out+=$'\n\nPython processes\n'
    out+=$(printf '  %7s  %6s  %8s  %9s  %s' PID 'CPU %' 'RAM MB' 'CPU time' command)
    while read -r pid mem seconds command; do
        [ -n "$pid" ] || continue
        share=""
        if [ -n "${previous[$pid]:-}" ]; then
            share=$(( 100 * (seconds - previous[$pid]) / interval / cores ))
        fi
        previous[$pid]=$seconds
        out+=$'\n'$(printf '  %7s  %6s  %8d  %02d:%02d:%02d  %s' "$pid" "$share" $(( mem / 1024 )) \
            $(( seconds / 3600 )) $(( seconds % 3600 / 60 )) $(( seconds % 60 )) "$command")
    done < <(python_processes)

    out+=$'\n\n'"Benchmark results ($results)"$'\n'
    out+=$(printf '  %-14s %9s  %-36s %s' configuration done 'last result' written)
    found=0
    for file in "$results"/*.csv; do
        [ -f "$file" ] || continue
        found=1
        rows=$(( $(wc -l < "$file") - 1 ))
        IFS=, read -r series k target seed _ _ _ _ _ _ _ _ _ _ status value _ < <(tail -n 1 "$file" | tr -d '\r')
        age=$(( $(date +%s) - $(stat -c %Y "$file") ))
        out+=$'\n'$(printf '  %-14s %4d / %-3d  %-36s %d s ago' "$(basename "$file" .csv)" "$rows" "$total" \
            "$series K=$k lambda=$target s$seed: $status $value" "$age")
    done
    [ "$found" = 1 ] || out+=$'\n  no results yet'

    printf '\033[H\033[2J%s\n\nRefresh every %s s - Ctrl+C to stop. Graphs: Task Manager (Ctrl+Shift+Esc) or resmon.\n' \
        "$out" "$interval"
    sleep "$interval"
done
