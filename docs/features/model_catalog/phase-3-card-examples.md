# Model Detail Popup Card Integration Examples
# Add these card configurations to your model catalog dashboard

# Example 1: Simple Template Button to Open Model Detail Popup
# Add to dashboard YAML:
- type: template
  template: >
    {% set model_ref = "gridfinity-bin" %}
    Model: {{ model_ref }}
  tap_action:
    action: call-service
    service: browser_mod.popup
    service_data:
      title: "Gridfinity Bin"
      size: wide
      content:
        type: custom:model-detail-popup-card
        model_ref: gridfinity-bin
        model_sidecar_url: http://localhost:8314

# Example 2: Markdown Card with Link to Open Model Details
- type: markdown
  content: |
    # Model Catalog
    
    ## Popular Models
    - [Gridfinity Bin](javascript:void(0)) 
    - [Print in Place Models](javascript:void(0))
    - [Functional Organizers](javascript:void(0))

# Example 3: Input Select with Pop-up Action
# Configure with model options, then tap to view
- type: custom:button-card
  entity: input_select.model_selector
  tap_action:
    action: call-service
    service: browser_mod.popup
    service_data:
      title: "{{ state_attr('input_select.model_selector', 'options')[states('input_select.model_selector')] }}"
      size: wide
      content:
        type: custom:model-detail-popup-card
        model_ref: "{{ states('input_select.model_selector') }}"
        model_entity: input_text.model_catalog_sidecar_base_url

# Example 4: Full Width Dashboard View with Model Browser + Detail Popup
# This integrates the Phase 2 browser with Phase 3 detail popup

title: Model Catalog
views:
  - title: Browse
    cards:
      - type: custom:model-catalog-browser-card
        title: "Model Catalog Browser"
        per_page: 12
        # When a model is selected, you can trigger the detail popup
        # This would be implemented in the browser card itself

# Example 5: Markdown with Inline Buttons for Quick Access
- type: markdown
  content: |
    # Quick Model Access
    
    Click a model to view details:
    
    [View Gridfinity Details](#) | [View Organizer](#) | [View Tool Holder](#)
  tap_action:
    action: call-service
    # Implementation would vary based on which button was clicked
