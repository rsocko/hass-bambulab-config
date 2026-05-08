# External Storage Behavior

> **Status**: Source-verified design reference.
> **Last updated**: 2026-04-22

## Purpose

Document what Manyfold does and does not reliably support when curated models are stored in a filesystem-scanned external library.

This doc exists because earlier planning language risked implying more automatic recovery and storage-mode flexibility than Manyfold actually provides.

## Baseline Truths

- Manyfold's documented integration surface is REST, not GraphQL
- filesystem-scanned libraries are fundamentally path- and folder-oriented
- scans and checks can detect new or missing content relative to known paths
- restoring content to the original path can allow missing problems to clear
- moved or renamed paths are not a general automatic relink workflow
- there is no baseline assumption of native in-place conversion between external scanned storage and Manyfold-managed/internal storage

## Mental Model

For scanned external libraries, Manyfold effectively treats a model as a discovered folder path and the files it finds under that path.

That means:

- folder stability matters
- adding files inside the same stable folder is friendly to rescans
- materially changing the path identity of a model is not the same as editing files inside that model

## Behavior Matrix

| Scenario | Expected Manyfold behavior | Recommended operator approach |
|---|---|---|
| Add a new file under the same model folder | Rescan can discover the new file | Safe normal flow |
| Restore a previously missing file/folder to the same path | Check/rescan can clear missing problems | Safe recovery flow |
| Rename a file but preserve the overall model folder/path assumptions | May be partially recoverable depending on exact path expectations, but do not assume automatic repair | Validate manually |
| Rename the model folder | Do not assume automatic relink | Treat as recreate/relink |
| Move the model elsewhere in the library tree | Do not assume automatic relink | Treat as recreate/relink |
| Reorganize many curated folders at once | High risk of stale/missing records | Avoid unless you are prepared for deliberate cleanup |
| Convert an external scanned model into Manyfold-managed/internal storage in place | Not a supported baseline assumption | Use explicit publish/recreate workflow |

## Recommended Use

Use external scanned curated storage only when all of the following are true:

- you want curated model files directly visible on disk
- you can keep the curated tree stable
- folder-per-model organization is natural enough for your use case
- you accept recreate/relink workflows when path identity changes

If those are not true, prefer letting Manyfold manage curated organization.

## Folder Guidance

For externally stored curated models, a one-folder-per-model mindset is the safest default.

That does not mean every folder shape must be identical, but it does mean:

- treat the folder as the stable model identity anchor
- keep related curated files together
- avoid frequent renames or moves after Manyfold has indexed the model

## Recovery Guidance

### Recovery Type 1: Same Path Restored

If the original file or folder is restored to the same path:

1. restore the content
2. run a check/rescan
3. verify the missing problem clears

This is the best-case recovery path.

### Recovery Type 2: Path Identity Changed

If the path changed materially:

1. do not assume Manyfold will repair the link automatically
2. decide whether to recreate the curated record or relink sidecar state to a newly discovered record
3. deliberately clean up stale missing/problem records as needed
4. carry forward metadata intentionally rather than implicitly

This is why the architecture avoids promising storage-mode conversion or path-healing behavior.

## Design Consequence

Because of these constraints:

- Working stays outside Manyfold by default
- cataloging should prefer Manyfold-managed organization when the operator does not want path-management overhead
- publish/recreate/relink terminology is more accurate than promote/demote terminology