# Print Queue Deployment Validation Checklist

Quick reference checklist for print_queue package deployment and validation.

## Pre-Deployment

- [ ] Resource version bumped to `v=7` in `_resources.yaml`
- [ ] Card JS file compiles without syntax errors
- [ ] Lovelace views created in `dashboard_views/`
- [ ] Loader YAML references all necessary sections
- [ ] E2E tests pass: `pytest tests/print_queue/ -v`

## Post-Deployment

### Browser

- [ ] Browser cache cleared (Ctrl+Shift+Delete)
- [ ] Hard refresh performed (Ctrl+Shift+R)
- [ ] No JavaScript errors in console (F12 → Console tab)
- [ ] No network 404 errors for card URL

### Queue Board Card

- [ ] Card renders without errors
- [ ] Queue entries load and display
- [ ] Stats widget shows counts (overnight-fit, AMS-ready, started, total)
- [ ] Entries appear in correct default state order

### Filters & Sorting

- [ ] State filters toggle correctly
- [ ] Source filters toggle correctly
- [ ] Sort dropdown changes queue order
- [ ] Clear All button resets filters
- [ ] Filter state persists on page refresh

### Add Modal

- [ ] "+ Add" button opens modal
- [ ] Quick Add tab works and submits
- [ ] Advanced tab loads sources
- [ ] Submit creates queue entry
- [ ] Success message appears
- [ ] Queue refreshes with new entry

### Detail Drawer

- [ ] Detail button opens drawer
- [ ] Entry details display correctly
- [ ] File grid shows files and plates
- [ ] Archive link available (if linked)
- [ ] Close button works
- [ ] Backdrop click closes drawer

### Suggestions

- [ ] Medium-confidence suggestions appear (if any)
- [ ] Accept button marks entry done
- [ ] Reject button marks suggestion rejected
- [ ] Success message appears for both actions
- [ ] Rejected suggestions don't re-appear

### Planner

- [ ] Planner button (📊) opens drawer
- [ ] Strategy selection works (Aggressive/Balanced/Lazy)
- [ ] Preview updates on strategy change
- [ ] Operation history displays
- [ ] Apply button executes plan
- [ ] Undo button reverts operation
- [ ] Queue refreshes after apply/undo

### API Verification

```bash
# Verify endpoints respond
curl -s http://localhost:8080/api/v1/queues/p1/entries | jq '.entries | length'
curl -s http://localhost:8080/api/v1/queues/p1/suggestions?status=suggested | jq '.suggestions | length'
curl -s http://localhost:8080/api/v1/queues/p1/plan/history | jq '.history | length'
curl -s http://localhost:8080/api/v1/queues/p1/plan/preview?strategy=balanced | jq '.planned_order | length'
```

- [ ] All endpoints return 200 status
- [ ] All responses have expected structure

## Rollback Procedure

If issues occur:

1. Revert Lovelace dashboard to previous card configuration
2. Clear browser cache and hard refresh
3. Check logs for errors: `grep -i "queue\|planner" homeassistant.log`
4. Restore from backup if needed

- [ ] Rollback tested successfully

## Sign-Off

**Deployed by**: _______________  
**Date**: _______________  
**Status**: ☐ Production Ready | ☐ Issues Found (see notes)  
**Notes**: _______________

