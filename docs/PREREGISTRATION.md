# Pre-registration

The machine-readable version is `config/prereg.json`. Edit it, review it, then run `scopeguard freeze`. The lock stores a hash of the file and of the frozen suite; E3 to E5 refuse to run without a matching lock (or `--exploratory`), and every trace records whether it was confirmatory.

Values currently in the file are **proposals**, not decisions: `false_block_limit` is 0.05 and `min_block_rate_gain_pp` is 20. Change them if you have a reason, before freezing.

Rules that go with the lock:

1. Primary comparisons are the ones listed in `primary_comparisons`. Anything else is exploratory and labeled so.
2. Report per model as well as pooled.
3. Publish null and negative results in the same table as the positive ones.
4. A change to the suite after freezing changes its hash and voids the lock; re-freeze and say why.
