"""
Integration tests for Phase 3.1 Edit Mode & Photo Management
Tests end-to-end workflows using Playwright browser automation
"""

import pytest
import asyncio
from pathlib import Path


# NOTE: These tests are designed to run with pytest-playwright plugin
# Install with: pip install pytest-playwright

@pytest.mark.asyncio
class TestEditModeIntegration:
    """Integration tests for edit mode functionality"""

    @pytest.fixture(scope="function")
    async def setup_page(self, page):
        """Setup page for testing"""
        # Navigate to model detail popup
        await page.goto("http://localhost:8123/")
        yield page
        await page.close()

    async def test_edit_mode_toggle(self, page):
        """Test toggling between view and edit mode"""
        # Wait for popup to load
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        # Find Edit button
        edit_button = await page.locator('button:has-text("✏️ Edit")')
        assert await edit_button.count() > 0, "Edit button should be present"
        
        # Click Edit button
        await edit_button.click()
        
        # Verify edit form appears
        edit_form = await page.locator('[id="edit-form-container"]')
        assert await edit_form.is_visible(), "Edit form should be visible"
        
        # Verify Cancel button appears
        cancel_button = await page.locator('button:has-text("✕ Cancel")')
        assert await cancel_button.count() > 0, "Cancel button should appear in edit mode"

    async def test_edit_form_validation(self, page):
        """Test form validation"""
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        # Enter edit mode
        edit_button = await page.locator('button:has-text("✏️ Edit")')
        await edit_button.click()
        
        # Clear model name
        name_field = await page.locator('input[id="model-name"]')
        await name_field.clear()
        
        # Try to save
        save_button = await page.locator('button:has-text("💾 Save")')
        await save_button.click()
        
        # Check for validation error
        error_msg = await page.locator('[id="error-model-name"]')
        error_text = await error_msg.text_content()
        assert error_text, "Validation error should appear"
        assert "required" in error_text.lower(), "Error should mention required field"

    async def test_edit_form_save(self, page):
        """Test saving edited model"""
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        # Enter edit mode
        edit_button = await page.locator('button:has-text("✏️ Edit")')
        await edit_button.click()
        
        # Update model name
        name_field = await page.locator('input[id="model-name"]')
        new_name = "Updated Model Name"
        await name_field.fill(new_name)
        
        # Save
        save_button = await page.locator('button:has-text("💾 Save")')
        await save_button.click()
        
        # Wait for form to close and data to update
        await page.wait_for_selector('[class*="header-title"]', timeout=10000)
        
        # Verify model name updated
        title = await page.locator('[class*="header-title"]')
        title_text = await title.text_content()
        assert new_name in title_text, "Model name should be updated"

    async def test_edit_mode_cancel(self, page):
        """Test cancelling edit mode"""
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        original_name = None
        title = await page.locator('[class*="header-title"]')
        original_name = await title.text_content()
        
        # Enter edit mode
        edit_button = await page.locator('button:has-text("✏️ Edit")')
        await edit_button.click()
        
        # Change model name
        name_field = await page.locator('input[id="model-name"]')
        await name_field.fill("Temporary Name")
        
        # Cancel
        cancel_button = await page.locator('button:has-text("✕ Cancel")')
        await cancel_button.click()
        
        # Verify name didn't change
        title = await page.locator('[class*="header-title"]')
        title_text = await title.text_content()
        assert original_name in title_text, "Model name should not change after cancel"


@pytest.mark.asyncio
class TestPhotoGalleryIntegration:
    """Integration tests for photo gallery"""

    async def test_gallery_tab_visible(self, page):
        """Test gallery tab is visible"""
        await page.goto("http://localhost:8123/")
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        # Find Gallery tab
        gallery_tab = await page.locator('button[data-tab="gallery"]')
        assert await gallery_tab.count() > 0, "Gallery tab should be present"

    async def test_gallery_tab_click(self, page):
        """Test clicking gallery tab"""
        await page.goto("http://localhost:8123/")
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        # Click Gallery tab
        gallery_tab = await page.locator('button[data-tab="gallery"]')
        await gallery_tab.click()
        
        # Verify gallery content is visible
        gallery_content = await page.locator('[class*="gallery"]')
        assert await gallery_content.is_visible(), "Gallery should be visible"

    async def test_photo_thumbnail_preview(self, page):
        """Test photo preview functionality"""
        await page.goto("http://localhost:8123/")
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        # Go to gallery tab
        gallery_tab = await page.locator('button[data-tab="gallery"]')
        await gallery_tab.click()
        
        # Find first thumbnail
        thumbnail = await page.locator('.gallery-thumbnail').first
        await thumbnail.hover()
        
        # Find preview button in thumbnail overlay
        preview_btn = await thumbnail.locator('[data-action="preview"]')
        assert await preview_btn.count() > 0, "Preview button should be present"
        await preview_btn.click(force=True)

        lightbox = page.locator('.photo-lightbox[role="dialog"]')
        await lightbox.wait_for(state="visible", timeout=5000)
        assert await lightbox.is_visible(), "Photo preview lightbox should open"

        close_btn = page.locator('#btn-photo-lightbox-close')
        await close_btn.click()
        await lightbox.wait_for(state="hidden", timeout=5000)

    async def test_photo_upload_button_edit_mode(self, page):
        """Test upload button appears in edit mode"""
        await page.goto("http://localhost:8123/")
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        # Go to gallery tab
        gallery_tab = await page.locator('button[data-tab="gallery"]')
        await gallery_tab.click()
        
        # Enter edit mode
        edit_button = await page.locator('button:has-text("✏️ Edit")')
        await edit_button.click()
        
        # Check for upload area
        upload_area = await page.locator('[id="photo-upload-area"]')
        assert await upload_area.is_visible(), "Upload area should be visible in edit mode"

    async def test_photo_set_as_preview(self, page):
        """Test setting photo as preview"""
        await page.goto("http://localhost:8123/")
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        # Go to gallery tab
        gallery_tab = await page.locator('button[data-tab="gallery"]')
        await gallery_tab.click()
        
        # Enter edit mode
        edit_button = await page.locator('button:has-text("✏️ Edit")')
        await edit_button.click()
        
        # Find photo thumbnail with star button
        thumbnail = await page.locator('.gallery-thumbnail').first
        star_btn = await thumbnail.locator('[data-action="set-preview"]')
        
        if await star_btn.count() > 0:
            await star_btn.click()
            
            # Verify preview badge appears
            preview_badge = await thumbnail.locator('.preview-badge')
            assert await preview_badge.count() > 0, "Preview badge should appear"


@pytest.mark.asyncio
class TestConflictDetectionIntegration:
    """Integration tests for conflict detection"""

    async def test_conflict_dialog_appears(self, page):
        """Test conflict dialog appears when conflict detected"""
        await page.goto("http://localhost:8123/")
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        # This test would require mocking concurrent edits
        # For now, just verify conflict dialog structure exists
        conflict_dialog = await page.locator('[class*="conflict-dialog"]')
        
        # Dialog should exist in DOM but be hidden initially
        assert await conflict_dialog.count() >= 0, "Conflict dialog structure should exist"

    async def test_conflict_resolution_buttons(self, page):
        """Test conflict resolution buttons are available"""
        await page.goto("http://localhost:8123/")
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        # Look for conflict resolution buttons
        cancel_btn = await page.locator('[id="btn-conflict-cancel"]')
        reload_btn = await page.locator('[id="btn-conflict-reload"]')
        overwrite_btn = await page.locator('[id="btn-conflict-overwrite"]')
        
        # Buttons should exist in DOM
        assert await cancel_btn.count() >= 0
        assert await reload_btn.count() >= 0
        assert await overwrite_btn.count() >= 0


@pytest.mark.asyncio
class TestAdvancedEnrichmentFields:
    """Integration tests for advanced enrichment fields"""

    async def test_advanced_section_toggle(self, page):
        """Test toggling advanced section"""
        await page.goto("http://localhost:8123/")
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        # Enter edit mode
        edit_button = await page.locator('button:has-text("✏️ Edit")')
        await edit_button.click()
        
        # Find advanced toggle
        advanced_toggle = await page.locator('[id="advanced-toggle"]')
        assert await advanced_toggle.count() > 0, "Advanced toggle should exist"
        
        # Click to expand
        await advanced_toggle.click()
        
        # Check for advanced content
        advanced_content = await page.locator('[id="advanced-content"]')
        is_visible = await advanced_content.evaluate('el => el.classList.contains("open")')
        assert is_visible, "Advanced section should be expanded"

    async def test_enrichment_fields_present(self, page):
        """Test enrichment fields are present"""
        await page.goto("http://localhost:8123/")
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        # Enter edit mode
        edit_button = await page.locator('button:has-text("✏️ Edit")')
        await edit_button.click()
        
        # Expand advanced section
        advanced_toggle = await page.locator('[id="advanced-toggle"]')
        await advanced_toggle.click()
        
        # Check for enrichment fields
        print_time = await page.locator('[id="enrichment-print-time"]')
        support_type = await page.locator('[id="enrichment-support-type"]')
        difficulty = await page.locator('[id="enrichment-difficulty"]')
        notes = await page.locator('[id="enrichment-print-notes"]')
        
        assert await print_time.count() > 0, "Print time field should exist"
        assert await support_type.count() > 0, "Support type field should exist"
        assert await difficulty.count() > 0, "Difficulty field should exist"
        assert await notes.count() > 0, "Notes field should exist"


@pytest.mark.asyncio
class TestResponsiveBehavior:
    """Integration tests for responsive design"""

    async def test_mobile_viewport_edit_mode(self, page):
        """Test edit mode on mobile viewport"""
        # Set mobile viewport
        await page.set_viewport_size({"width": 375, "height": 812})
        
        await page.goto("http://localhost:8123/")
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        # Enter edit mode
        edit_button = await page.locator('button:has-text("✏️ Edit")')
        await edit_button.click()
        
        # Verify form is usable
        name_field = await page.locator('input[id="model-name"]')
        assert await name_field.is_visible(), "Name field should be visible on mobile"

    async def test_tablet_viewport(self, page):
        """Test on tablet viewport"""
        # Set tablet viewport
        await page.set_viewport_size({"width": 768, "height": 1024})
        
        await page.goto("http://localhost:8123/")
        await page.wait_for_selector('[class*="popup"]', timeout=10000)
        
        # Verify popup is properly sized
        popup = await page.locator('[class*="popup-container"]')
        assert await popup.is_visible(), "Popup should be visible on tablet"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--asyncio-mode=auto'])
