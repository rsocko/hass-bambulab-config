# Bambuddy Photo Archive Integration (SUPERSEDED)

> **This file is a redirect stub.** The active design and implementation no longer live in the monolithic `bambuddy_integration` package.
>
> Use these canonical documents instead:
>
> - [print_history/photo-capture-design.md](../print_history/photo-capture-design.md)
> - [print_history/archive-enrichment.md](../print_history/archive-enrichment.md)
> - [print_history/README.md](../print_history/README.md)
> - [../../repo/bambuddy-reorganization-plan.md](../../repo/bambuddy-reorganization-plan.md)

Current state summary:

- the active photo-capture implementation lives in `homeassistant/packages/3d_printing/print_history/`
- the legacy `bambuddy_integration` package is superseded and will be removed during cleanup
- the active `print_history` package now owns local snapshot capture and the first-phase shell upload bridge
- any future richer upload worker design belongs in `print_history` docs, not here