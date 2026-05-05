/**
 * Intake Wizard Components Entry Point
 * 
 * Loads all intake wizard components for model catalog intake workflow
 * Phases D-I: Source → Organize → Validate → Upload
 * 
 * Cache-bust versioning: Increment v=NN when any component changes
 */

// Phase F: State Management
import '/local/3d_printing/model_catalog/intake-wizard/store.js?v=1';

// Phase D-E: Source Step Components
import '/local/3d_printing/model_catalog/intake-wizard/source-summary.js?v=1';
import '/local/3d_printing/model_catalog/intake-wizard/source-browser.js?v=1';
import '/local/3d_printing/model_catalog/intake-wizard/source-server.js?v=1';
import '/local/3d_printing/model_catalog/intake-wizard/source-server-summary.js?v=1';

// Phase E: Shared Components
import '/local/3d_printing/model_catalog/intake-wizard/partial-folder-badge.js?v=1';
import '/local/3d_printing/model_catalog/intake-wizard/return-to-source-banner.js?v=1';
import '/local/3d_printing/model_catalog/intake-wizard/recursive-toggle.js?v=1';
import '/local/3d_printing/model_catalog/intake-wizard/recursive-override-warning.js?v=1';
import '/local/3d_printing/model_catalog/intake-wizard/pane-sync.js?v=1';

// Phase G: Organize Step
import '/local/3d_printing/model_catalog/intake-wizard/organize-step.js?v=1';

// Phase H: Validate Step
import '/local/3d_printing/model_catalog/intake-wizard/validate-step.js?v=1';

// Phase I: Upload Handler
import '/local/3d_printing/model_catalog/intake-wizard/upload-handler.js?v=1';

console.log('✓ Intake Wizard components loaded');
