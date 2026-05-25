"""Working files schema (post working-groups deprecation).

The legacy working_groups / working_items / working_file_inventory /
working_group_model_links tables were removed by PR E.1 of the
working-groups deprecation. The working-files context is now a thin
filesystem-only browser surfaced by routers/working.py; no schema lives here.

This module is retained as a marker for the bounded context.
"""
