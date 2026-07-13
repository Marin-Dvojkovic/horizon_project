# Why runtime grows linearly with #FDs

Across all three experiments (service_tickets, hospital_2k, insurance_claims_2k),
with the rows held fixed, runtime rises **linearly** with the number of FDs — and
since each FD here adds ~one attribute, that shows up as linear in #attributes too.

## The reason is algorithmic, not an implementation quirk

Horizon does a fixed slice of work **per FD, per tuple**. The two heavy stages are
both a loop over tuples containing a loop over FDs:

- **repair** (`horizon.py:187`): for each tuple, do O(1) work for each FD.
- **graph build** (`fd_pattern_graph.py:172`): scan the data once per FD to count
  its patterns.

Both are therefore `O(n_rows · n_FDs)`. With `n_rows` fixed, adding one FD adds one
constant slice of work over all the rows — so total time is a straight line in the
number of FDs. Ordering the FDs is `O(#FDs)` and negligible.

This is exactly Horizon's design claim ("linear in the data and the rules"), just
observed along the rules axis instead of the rows axis. There's no way to repair
under N rules without at least looking at each rule for each row, and Horizon does
precisely that — no more (the repair table memoizes decisions so interacting FDs
stay O(1) instead of blowing up). The linear slope is that per-rule slice of work.

## What implementation only affects

The implementation sets the *constants* (how steep the line is, and a fixed startup
cost), and it decides *which* stage happens to dominate at a given data size — but
none of that bends the line. The linearity is the algorithm.
