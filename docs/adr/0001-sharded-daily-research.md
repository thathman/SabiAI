# Sharded daily research before cross-sport decisions

**Status: accepted and implemented**

Sabi Boy's daily research will be structured as a bounded fan-out of sport → country → competition/division research slices, followed by one consolidated decision pass. Each slice and its evidence are cacheable and independently retryable, so a large multi-sport day does not become one timeout-prone prompt and a slip review can reuse fresh same-day work instead of rescanning everything. The decision pass must enforce coverage and exposure limits without forcing weak picks, while allowing a genuinely supported cross-sport value edge to win.

The existing cache-first, free-first source policy remains the source order; model calls are for slice assessment and synthesis, not for inventing fixtures, leagues, prices or coverage.
