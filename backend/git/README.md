# Git intelligence boundary

Phase 1 reads branch and commit identifiers using fixed, timed Git subprocess calls in `backend.analysis.indexer`. The subprocess environment strips inherited Git repository/configuration overrides. No hooks, repository scripts, external diffs, or working-tree commands are invoked.

Commit history, churn, hotspots, branch comparisons, and pull-request reviews are scheduled for Phase 6.
