#!/usr/bin/env python3
"""Filter scanner output to only 🟢 (Very strong/Strong) and 🟡 (Solid) picks.
Drops 🟠 (Slight lean / Coin-flip) blocks entirely."""
import sys

if len(sys.argv) < 2:
    import sys as _s; _s.exit(1)

with open(sys.argv[1]) as f:
    content = f.read()

lines = content.split("\n")
out = []
skip_block = False

for line in lines:
    # New orange pick → skip this block
    if line.startswith("🟠"):
        skip_block = True
        continue
    # New green/yellow pick or sport header → end skip
    if skip_block:
        if line.startswith(("🟢", "🟡", "*", "_Bet")) or line.strip() == "":
            skip_block = False
        else:
            continue
    out.append(line)

# Clean up excess blank lines
result = "\n".join(out).strip()
# Remove trailing blank lines between picks
while "\n\n\n" in result:
    result = result.replace("\n\n\n", "\n\n")

print(result)
