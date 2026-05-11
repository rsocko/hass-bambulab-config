# Print Queue Migration Checklist

## Overview

This checklist guides you through migrating from the legacy `queue.yaml` to the new unified print queue package (`print_queue`).

**Estimated time**: 15-30 minutes  
**Difficulty**: Low to Medium  
**Risk level**: Low (old config will coexist until manually removed)

---

## Prerequisites

- [ ] Home Assistant 2024.12 or later
- [ ] Bambuddy REST API running (printer queue endpoints available)
- [ ] Browser with modern JavaScript support (ES2020+)
- [ ] Read-only access to current `queue.yaml` configuration

---

## Backup

### Step 1: Backup Current Configuration

Before making any changes, create a backup:

```bash
# Backup current queue configuration
cp homeassistant/packages/3d_printing/queue.yaml homeassistant/packages/3d_printing/queue.yaml.backup
```

- [ ] Backup `queue.yaml` to `queue.yaml.backup`
- [ ] Backup entire `homeassistant/` directory to external storage
- [ ] Document current queue statistics (entry count, typical filters in use)

---

## Installation

### Step 2: Deploy New Print Queue Package

The print queue package is now part of the standard deployment:

- [ ] Verify `homeassistant/packages/3d_printing/print_queue/` directory exists
- [ ] Verify `print_queue_loader.yaml` is present
- [ ] Verify `homeassistant/www/3d_printing/print_queue/unified-queue-board-card.js` exists
- [ ] Verify resource registration in `_resources.yaml` includes the card URL with version parameter

### Step 3: Register Lovelace Views

The dashboard views are auto-registered from `dashboard_views/`:

- [ ] Dashboard should show "Print Queue" view appearing in the sidebar
- [ ] Dashboard should show "Queue Manager" view (when implemented)

---

## Configuration

### Step 4: Update Lovelace Dashboard

If you have a custom queue view in your main dashboard, update it to use the new card:

**Old (if applicable):**
```yaml
type: entities
entities:
  - sensor.queue_status
  - sensor.queue_next_job
```

**New:**
```yaml
type: custom:unified-queue-board-card
printer_id: p1  # Match your printer ID
```

- [ ] Update Lovelace dashboard to use `unified-queue-board-card`
- [ ] Configure `printer_id` (typically `p1` for default printer)
- [ ] Hard refresh browser (Ctrl+Shift+R) to load new card code
- [ ] Verify card loads without JavaScript errors (check browser console)

### Step 5: Verify API Endpoints

Ensure Bambuddy API is providing required endpoints:

```bash
# Test queue entries endpoint
curl http://localhost:8080/api/v1/queues/p1/entries

# Test suggestions endpoint
curl http://localhost:8080/api/v1/queues/p1/suggestions?status=suggested

# Test planner endpoints
curl http://localhost:8080/api/v1/queues/p1/plan/history
curl http://localhost:8080/api/v1/queues/p1/plan/preview?strategy=balanced
```

- [ ] Queue entries endpoint returns 200 + valid entries array
- [ ] Suggestions endpoint returns 200 + suggestions array
- [ ] Planner history endpoint returns 200 + history array
- [ ] Planner preview endpoint returns 200 + planned_order array

---

## Testing

### Step 6: Basic Functionality Tests

#### Queue Board Card

- [ ] Queue entries render without errors
- [ ] Entry list displays correct number of items
- [ ] State filter buttons toggle (todo, ready, started, done, blocked, idea)
- [ ] Source filter buttons toggle (catalog, working, file, idea)
- [ ] Sort dropdown changes queue order
- [ ] Clear Filters button resets to defaults
- [ ] Stat widget shows correct counts (overnight-fit, AMS-ready, started, total)

#### Add to Queue Modal

- [ ] "+ Add" button opens modal overlay
- [ ] Quick Add tab submits with `quick_add=true`
- [ ] Advanced tab loads source options (Catalog Models, Working Groups)
- [ ] Source kind dropdown changes available options
- [ ] File checkboxes appear when source is selected
- [ ] Plate checkboxes appear for each selected file
- [ ] Copy count field accepts positive integers
- [ ] Submit button sends POST to `/add` endpoint
- [ ] Success flash banner appears after add
- [ ] Modal closes automatically on success
- [ ] Queue refreshes with new entry

#### Entry Detail Drawer

- [ ] Detail button (on queue entry) opens drawer
- [ ] Drawer displays all queue entry fields
- [ ] File grid shows thumbnails (if available)
- [ ] Plate list shows selection status and completion counts
- [ ] Archive linkage section shows linked archive (if available)
- [ ] Print History link navigates correctly
- [ ] Close button closes drawer
- [ ] Backdrop click closes drawer

#### Medium-Confidence Suggestions

- [ ] Suggestion cards appear above queue (if suggestions exist)
- [ ] Suggestion metadata displays (archive ID, confidence, reasons)
- [ ] Accept button marks entry done + records audit trail
- [ ] Reject button marks suggestion rejected
- [ ] Flash banner confirms action
- [ ] Rejected suggestions don't re-appear on refresh

#### Queue Planner

- [ ] Planner button (📊) opens drawer
- [ ] Strategy radio buttons (Aggressive, Balanced, Lazy)
- [ ] Preview updates when strategy changes
- [ ] Preview list shows planned order with reasons
- [ ] Operation history displays past planner runs
- [ ] Apply button executes plan + closes drawer
- [ ] Undo button reverts last operation (if history exists)
- [ ] Flash banner confirms operation

### Step 7: Data Persistence Tests

- [ ] Filter state persists across page refresh (localStorage)
- [ ] Filter state separate per printer_id
- [ ] Add modal source selection persists during modal lifetime
- [ ] Detail drawer scrolls independently of main queue

---

## Validation

### Step 8: Verify No Data Loss

- [ ] All queue entries from old config appear in new UI
- [ ] Entry rankings match old configuration
- [ ] Entry copies requested match old values
- [ ] Archive linkages preserved (last_archive_id field)

### Step 9: Check Logs for Errors

```bash
# Check Home Assistant logs for 404s, template errors, etc.
tail -f homeassistant.log | grep -i "queue\|planner\|suggestion"
```

- [ ] No 404 errors for card or resource URLs
- [ ] No JavaScript syntax errors in browser console
- [ ] No API errors when loading queue data
- [ ] No template rendering errors

### Step 10: Performance Validation

- [ ] Queue loads within 2 seconds on initial page load
- [ ] Auto-refresh every 30 seconds completes without lag
- [ ] Filter/sort operations respond immediately
- [ ] Modal opens without noticeable delay
- [ ] Drawer opens smoothly (slide-in animation)

---

## Rollback

### If Issues Occur

If you encounter problems, rollback is straightforward:

1. **Revert Lovelace configuration** back to previous card type or entity card
2. **Remove print_queue package** from loader (if integrated into feature loader)
3. **Hard refresh browser** to clear old card cache
4. **Verify old queue view** displays correctly

```bash
# Restore from backup
cp homeassistant/packages/3d_printing/queue.yaml.backup homeassistant/packages/3d_printing/queue.yaml
```

- [ ] Rollback completed if needed
- [ ] Old queue view restored and verified
- [ ] No lingering errors in logs

---

## Cleanup

### Step 11: Remove Legacy Configuration (Optional)

Once fully migrated and validated, you may remove the old queue.yaml:

**⚠️ Only do this after extended testing period (at least 1 week)**

```bash
# Remove old queue.yaml only after successful migration
rm homeassistant/packages/3d_printing/queue.yaml
```

- [ ] Migration stable for 1+ week
- [ ] All users trained on new UI
- [ ] Remove old `queue.yaml` file
- [ ] Commit changes to git

---

## Support & Troubleshooting

### Common Issues

#### Card doesn't render

- [ ] Clear browser cache (Ctrl+Shift+Delete)
- [ ] Hard refresh page (Ctrl+Shift+R)
- [ ] Check `_resources.yaml` has correct version parameter
- [ ] Check browser console for JavaScript errors

#### API endpoints return 404

- [ ] Verify Bambuddy service is running
- [ ] Verify printer_id matches configuration
- [ ] Check API logs for endpoint registration
- [ ] Verify queue REST endpoints are enabled

#### Filters don't persist

- [ ] Check browser localStorage is enabled
- [ ] Check browser console for localStorage errors
- [ ] Clear browser cache and try again
- [ ] Verify printer_id is configured correctly

#### Performance issues

- [ ] Check queue entry count (high count may slow rendering)
- [ ] Check network latency to Bambuddy API
- [ ] Reduce auto-refresh interval if needed
- [ ] Check browser DevTools Performance tab

### Getting Help

- [ ] Review issue #1429 and linked issues for known problems
- [ ] Check GitHub discussions for community solutions
- [ ] File new issue with reproduction steps and browser console logs

---

## Sign-Off

- [ ] All checks completed
- [ ] No critical issues remain
- [ ] Rollback procedure verified and documented
- [ ] Ready for production use

**Migration Date**: _______________  
**Migrated By**: _______________  
**Approved By**: _______________

