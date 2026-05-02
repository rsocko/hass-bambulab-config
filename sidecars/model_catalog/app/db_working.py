"""Working groups schema.

This module documents the working groups context. The actual query logic
resides in the routers since working group operations are more complex and
leverage local file discovery and working group hierarchies.

Tables:
- working_groups: Group definitions with discovery metadata
- working_items: Individual files within groups
- working_file_inventory: File discovery cache
- working_group_model_links: Links between groups and models
"""

# This module is organized by bounded context for schema clarity.
# Most query/mutation logic resides in routers/working.py
