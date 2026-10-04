# STT resume identity guard

The canonical V6 training entry point now requires pre-split streaming inputs,
CUDA availability, and output outside its Git worktree. A fresh run refuses
an existing output directory. It records hashes of JSONL/SQLite manifests,
every referenced audio file, local model/initial-adapter assets, and the V6
entry point/shared trainer/identity helper, plus the exact supplied settings.
No transcript content is retained in this run-identity JSON.

Resume requires the original identity and a checkpoint immediately inside
that run, with Trainer state, optimizer, scheduler, RNG state, and adapter
weights. Changed data, weights, code, or options are rejected. Older runs
without this manifest are not silently migrated; preserve their original
checkout and execution recipe instead. Audio hashing increases startup time
but avoids a file-path-only identity falsely proving unchanged training data.

The regression test checks fresh overwrite refusal, incomplete checkpoint
rejection, matching resume, and changed audio/model/code/manifest/settings.
It uses disposable fixtures and is not a numerical resume-equivalence test.
Compilation checks pass; a one-step CUDA smoke is still required before
launching the next long run. No live training checkout was edited.
