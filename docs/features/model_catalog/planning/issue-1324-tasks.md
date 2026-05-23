# Issue #1324 — GitHub Sub-Issue Templates

**Parent Issue**: [#1324 — Should 'picking a folder' on Browser work exactly like Server](https://github.com/rsocko/hass-bambulab-config/issues/1324)

**Status**: Design approved, ready to create tracking issues

**Estimated Effort**: 3 weeks (Backend foundation + Frontend + Integration)

---

## Instructions

Click each link below to open GitHub and create a new issue with pre-populated title and body. The issues are organized in implementation order:

**Week 1**: Create issues I1–I4 (Backend foundation)
**Week 2**: Create issues I5–I6 (Frontend)  
**Week 3**: Create issues I7–I8 (Integration)

Suggested parent/child relationships noted below — you'll need to manually link them using GitHub's "Linked issues" feature after creation.

---

## I1: Backend — Queue Schema & Selection Consolidation

**Effort**: 2–3 days | **Blocks**: I5, I7  
**Parent**: #1324

[**➤ CREATE THIS ISSUE**](https://github.com/rsocko/hass-bambulab-config/issues/new?title=I1:%20Backend%20%E2%80%94%20Queue%20Schema%20%26%20Selection%20Consolidation&body=%23%23%20Parent%20Issue%0A%23%231324%20%E2%80%94%20Unified%20%22Pick%20a%20Folder%22%20UX%20with%20removal%20semantics%0A%0A%23%23%20Summary%0A%0AImplement%20the%20backend%20queue%20schema%20changes%20and%20selection%20consolidation%20logic%20to%20support%20%60excluded_items%60%20tracking%20and%20prevent%20overlapping%20folder%20selections.%0A%0A%23%23%20Implementation%20Scope%0A%0A%23%23%23%20A1.%20Queue%20Item%20Schema%20Update%0A%0AUpdate%20%60SourceEntry%60%20and%20%60IntakeItem%60%20dataclasses%20to%20include%20%60excluded_items%60%20array%3A%0A%0A%60%60%60python%0A%40dataclass%0Aclass%20SourceEntry%3A%0A%20%20type%3A%20Literal%5B%22file%22%2C%20%22folder%22%5D%0A%20%20path%3A%20str%0A%20%20recursive%3A%20bool%20%7C%20None%20%3D%20None%0A%20%20excluded_items%3A%20list%5Bstr%5D%20%3D%20field%28default_factory%3Dlist%29%0A%60%60%60%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Add%20%60excluded_items%60%20field%20to%20%60SourceEntry%60%0A-%20%5B%20%5D%20Update%20JSON%20serialization%2Fdeserialization%0A-%20%5B%20%5D%20Write%20schema%20validation%20tests%0A-%20%5B%20%5D%20Verify%20backward%20compatibility%20(old%20queue%20items%20without%20field%20load%20OK)%0A%0A%23%23%23%20A2.%20Selection%20Consolidation%20Logic%0A%0AImplement%20%60_consolidate_overlapping_selections()%60%20to%20prevent%20overlapping%20folder%20selections%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Create%20%60intake_service.py%60%20helper%20module%0A-%20%5B%20%5D%20Implement%20%60_consolidate_overlapping_selections()%60%20function%0A-%20%5B%20%5D%20Implement%20%60_compute_exclusion_impact()%60%20function%20(for%20Organize%20step%20later)%0A-%20%5B%20%5D%20Test%20overlap%20scenarios%3A%20parent%20%2B%20child%20absorbed%20correctly%0A-%20%5B%20%5D%20Test%20exclusions%20merged%20during%20consolidation%0A%0A%23%23%23%20A3.%20Intake%20Submission%20Endpoint%20Update%0A%0AUpdate%20%60POST%20%2Fapi%2Fintake%2Fsubmit%60%20to%20accept%20and%20validate%20%60excluded_items%60%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Accept%20%60excluded_items%60%20in%20payload%0A-%20%5B%20%5D%20Call%20consolidation%20logic%20before%20storing%0A-%20%5B%20%5D%20Validate%20exclusion%20paths%20exist%20in%20source%20entries%0A-%20%5B%20%5D%20Return%20error%20if%20invalid%20exclusions%0A%0A%23%23%20Design%20Reference%0A%0Asee%20%5Bintake-source-selection-removal-design.md%5D(/docs/features/model_catalog/design/intake-source-selection.md)%20%23Selection%20Consolidation%20Rules%0A%0A%23%23%20Acceptance%20Criteria%0A%0A-%20%5B%20%5D%20Queue%20item%20schema%20includes%20%60excluded_items%60%20array%0A-%20%5B%20%5D%20Overlapping%20selections%20consolidated%20to%20topmost%20parent%0A-%20%5B%20%5D%20Exclusions%20from%20all%20entries%20merged%20during%20consolidation%0A-%20%5B%20%5D%20All%20unit%20tests%20passing%0A-%20%5B%20%5D%20Backward%20compatible%20with%20old%20queue%20items%0A%0A%23%23%20Related%0A%0A--%20%5BImplementation%20Breakdown%5D(issue-1324-implementation-breakdown.md))

---

## I2: Backend — Grouping & Pre-Filtering

**Effort**: 2 days | **Blocks**: I5, I7 | **Depends on**: I1  
**Parent**: #1324

[**➤ CREATE THIS ISSUE**](https://github.com/rsocko/hass-bambulab-config/issues/new?title=I2:%20Backend%20%E2%80%94%20Grouping%20%26%20Pre-Filtering&body=%23%23%20Parent%20Issue%0A%23%231324%20%E2%80%94%20Unified%20%22Pick%20a%20Folder%22%20UX%20with%20removal%20semantics%0A%0A%23%23%20Summary%0A%0AImplement%20pre-filtering%20logic%20to%20remove%20excluded%20items%20from%20all%20downstream%20steps%20(Organize%2C%20Validate%2C%20Commit)%20and%20update%20grouping%20logic%20to%20work%20with%20pre-filtered%20file%20lists.%0A%0A%23%23%20Implementation%20Scope%0A%0A%23%23%23%20B1.%20Pre-Filtering%20Helper%0A%0AImplement%20%60_prefilter_excluded_items()%60%20function%3A%0A%0A%60%60%60python%0Adef%20_prefilter_excluded_items(expanded_files%3A%20list%5BFile%5D%2C%20excluded_items%3A%20list%5Bstr%5D)%20-%3E%20list%5BFile%5D%3A%0A%20%20%22%22%22Filter%20out%20excluded%20files%20from%20working%20list.%22%22%22%0A%20%20return%20%5Bf%20for%20f%20in%20expanded_files%20if%20f.path%20not%20in%20excluded_items%5D%0A%60%60%60%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Create%20function%20in%20%60intake_grouping.py%60%0A-%20%5B%20%5D%20Handle%20both%20absolute%20and%20relative%20paths%0A-%20%5B%20%5D%20Test%20with%20100%20files%2C%205%20exclusions%20%E2%86%92%2095%20returned%0A-%20%5B%20%5D%20Test%20empty%20exclusions%20%E2%86%92%20all%20files%20returned%0A%0A%23%23%23%20B2.%20Update%20Grouping%20Logic%0A%0AUpdate%20%60_group_files_by_strategy()%60%20to%20accept%20exclusions%20and%20pre-filter%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Add%20%60excluded_items%3A%20list%5Bstr%5D%60%20parameter%0A-%20%5B%20%5D%20Call%20%60_prefilter_excluded_items()%60%20first%0A-%20%5B%20%5D%20Proceed%20with%20normal%20grouping%20on%20filtered%20list%0A-%20%5B%20%5D%20Test%20by-folder%20strategy%20with%20exclusions%0A-%20%5B%20%5D%20Test%20by-root%2C%20flat%2C%20none%20strategies%20with%20exclusions%0A%0A%23%23%23%20B3.%20Cascade%20Partial%20Indicators%0A%0AImplement%20%60_compute_partial_indicators()%60%20for%20UI%20display%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Create%20function%20to%20compute%20partial%20status%20per%20folder%0A-%20%5B%20%5D%20Mark%20parent%20and%20ancestors%20as%20partial%20(cascade%20upward)%0A-%20%5B%20%5D%20Return%20dict%20of%20%60folder_path%20-%3E%20is_partial%60%0A-%20%5B%20%5D%20Test%20single%20exclusion%20cascades%20correctly%0A-%20%5B%20%5D%20Test%20multiple%20exclusions%20in%20same%20folder%0A%0A%23%23%20Acceptance%20Criteria%0A%0A-%20%5B%20%5D%20Pre-filtering%20removes%20excluded%20items%20from%20all%20downstream%20steps%0A-%20%5B%20%5D%20Grouping%20calculations%20use%20pre-filtered%20list%0A-%20%5B%20%5D%20Excluded%20files%20never%20appear%20in%20groups%0A-%20%5B%20%5D%20Partial%20indicators%20cascade%20upward%20through%20hierarchy%0A-%20%5B%20%5D%20All%20unit%20tests%20passing%0A%0A%23%23%20Related%0A%0A-%20Depends%20on%3A%20I1%0A-%20Blocks%3A%20I5%2C%20I7%0A-%20%5BImplementation%20Breakdown%5D(issue-1324-implementation-breakdown.md))

---

## I3: Backend — Validation Integration & Schema

**Effort**: 1–2 days | **Blocks**: I7 | **Depends on**: I1  
**Parent**: #1324

[**➤ CREATE THIS ISSUE**](https://github.com/rsocko/hass-bambulab-config/issues/new?title=I3:%20Backend%20%E2%80%94%20Validation%20Integration%20%26%20Schema&body=%23%23%20Parent%20Issue%0A%23%231324%20%E2%80%94%20Unified%20%22Pick%20a%20Folder%22%20UX%20with%20removal%20semantics%0A%0A%23%23%20Summary%0A%0AAdd%20new%20validation%20check%20%60excluded_items_summary%60%20to%20inform%20users%20of%20excluded%20items%20before%20commit.%20This%20check%20is%20always%20informational%20(never%20blocking).%0A%0A%23%23%20Implementation%20Scope%0A%0A%23%23%23%20C1.%20Validation%20Endpoint%20Update%0A%0AUpdate%20%60POST%20%2Fapi%2Fintake%2Fitems%2F%7Bitem_id%7D%2Fvalidate%60%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Extract%20%60excluded_items%60%20from%20queue%20item%0A-%20%5B%20%5D%20Add%20new%20check%3A%20%60excluded_items_summary%60%0A-%20%5B%20%5D%20Always%20include%20check%20(even%20if%20count%20%3D%200)%0A-%20%5B%20%5D%20Message%20format%3A%20%22N%20files%20and%20M%20folders%20excluded%20from%20selected%20sources%22%0A-%20%5B%20%5D%20Check%20must%20always%20pass%20(informational%20only)%0A-%20%5B%20%5D%20Test%20with%20no%20exclusions%0A-%20%5B%20%5D%20Test%20with%205%20exclusions%0A%0A%23%23%23%20C2.%20Validation%20Response%20Schema%0A%0AUpdate%20%60ValidationCheck%60%20dataclass%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Ensure%20schema%20can%20represent%20new%20check%0A-%20%5B%20%5D%20Test%20JSON%20serialization%0A%0A%23%23%20Example%20Response%0A%0A%60%60%60json%0A%7B%0A%20%20%22key%22:%20%22excluded_items_summary%22,%0A%20%20%22label%22:%20%22Exclusion%20summary%22,%0A%20%20%22passed%22:%20true,%0A%20%20%22detail%22:%20%223%20files%20excluded%20from%20selected%20sources.%20Proceeding%20with%2012%20remaining%20items.%22%0A%7D%0A%60%60%60%0A%0A%23%23%20Acceptance%20Criteria%0A%0A-%20%5B%20%5D%20Validation%20always%20includes%20%60excluded_items_summary%60%20check%0A-%20%5B%20%5D%20Check%20correctly%20counts%20excluded%20items%0A-%20%5B%20%5D%20Message%20readable%20and%20informative%0A-%20%5B%20%5D%20Check%20always%20passes%20(never%20blocking)%0A-%20%5B%20%5D%20All%20unit%20tests%20passing%0A%0A%23%23%20Related%0A%0A-%20Depends%20on%3A%20I1%0A-%20Blocks%3A%20I7%0A-%20Design%3A%20%5Bintake-validation-contract.md%5D(/docs/features/model_catalog/reference/intake-validation.md)%20%23New%20Validation%20Check)

---

## I4: Frontend — State Management & Persistence

**Effort**: 2 days | **Blocks**: I5, I6 | **Depends on**: I1  
**Parent**: #1324

[**➤ CREATE THIS ISSUE**](https://github.com/rsocko/hass-bambulab-config/issues/new?title=I4:%20Frontend%20%E2%80%94%20State%20Management%20%26%20Persistence&body=%23%23%20Parent%20Issue%0A%23%231324%20%E2%80%94%20Unified%20%22Pick%20a%20Folder%22%20UX%20with%20removal%20semantics%0A%0A%23%23%20Summary%0A%0AImplement%20wizard%20state%20management%20to%20track%20%60excluded_items%60%20and%20maintain%20state%20across%20Back%2FNext%20navigation.%20Implement%20left%2Fright%20pane%20synchronization%20utilities.%0A%0A%23%23%20Implementation%20Scope%0A%0A%23%23%23%20F1.%20Intake%20Wizard%20State%20Store%20Update%0A%0AAdd%20excluded%20items%20tracking%20to%20state%3A%0A%0A%60%60%60javascript%0Asource:%20%7B%0A%20%20mode:%20%22browser%22,%0A%20%20entries:%20%5B%7B%20type:%20%22folder%22,%20path:%20%22%2Fmodels%2F%22,%20recursive:%20true,%20excluded:%20%5B...%5D%20%7D%5D,%0A%20%20excluded_items:%20%5B%22%2Fmodels%2Fexperimental.3mf%22%5D%0A%7D%0A%60%60%60%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Add%20%60excluded_items%60%20field%20to%20state%20store%0A-%20%5B%20%5D%20Implement%20%60addExcludedItem(path)%60%20method%0A-%20%5B%20%5D%20Implement%20%60removeExcludedItem(path)%60%20method%0A-%20%5B%20%5D%20Implement%20%60getPreFilteredFiles()%60%20method%0A-%20%5B%20%5D%20Persist%20state%20across%20Back%2FNext%20navigation%0A-%20%5B%20%5D%20Test%20state%20survives%20page%20reload%20(if%20applicable)%0A%0A%23%23%23%20F2.%20Left%2FRight%20Pane%20Synchronization%20Utilities%0A%0ACreate%20sync%20utilities%20for%20coordinated%20navigation%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Implement%20%60_syncNavigation(leftPath)%60%0A-%20%5B%20%5D%20Implement%20%60_syncBreadcrumb(path)%60%0A-%20%5B%20%5D%20Implement%20%60_updatePartialIndicators(excluded)%60%0A-%20%5B%20%5D%20Test%20left%20→%20right%20sync%0A-%20%5B%20%5D%20Test%20right%20→%20left%20sync%0A-%20%5B%20%5D%20Test%20breadcrumb%20always%20identical%0A%0A%23%23%20Acceptance%20Criteria%0A%0A-%20%5B%20%5D%20State%20store%20tracks%20excluded%20items%0A-%20%5B%20%5D%20Exclusions%20persist%20across%20Back%2FNext%20navigation%0A-%20%5B%20%5D%20Left%2Fright%20panes%20stay%20synchronized%0A-%20%5B%20%5D%20Breadcrumb%20always%20shows%20same%20path%20on%20both%20sides%0A-%20%5B%20%5D%20All%20unit%20tests%20passing%0A%0A%23%23%20Related%0A%0A-%20Depends%20on%3A%20I1%0A-%20Blocks%3A%20I5%2C%20I6%0A-%20%5BImplementation%20Breakdown%5D(issue-1324-implementation-breakdown.md))

---

## I5: Frontend — Source Step Browser Mode

**Effort**: 3 days | **Blocks**: I7 | **Depends on**: I1, I4  
**Parent**: #1324

[**➤ CREATE THIS ISSUE**](https://github.com/rsocko/hass-bambulab-config/issues/new?title=I5:%20Frontend%20%E2%80%94%20Source%20Step%20Browser%20Mode&body=%23%23%20Parent%20Issue%0A%23%231324%20%E2%80%94%20Unified%20%22Pick%20a%20Folder%22%20UX%20with%20removal%20semantics%0A%0A%23%23%20Summary%0A%0AImplement%20Browser%20Upload%20Source%20step%20with%20file%2Ffolder%20tree%2C%20removal%20buttons%2C%20partial%20indicators%2C%20and%20synchronized%20left%2Fright%20pane%20display.%0A%0A%23%23%20Implementation%20Scope%0A%0A%23%23%23%20D1.%20Browser%20File%20Tree%20Component%0A%0ACreate%20%60%3Csource-browser-file-tree%3E%60%20component%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Render%20uploaded%20files%2Ffolders%20in%20tree%20structure%0A-%20%5B%20%5D%20Show%20remove%20button%20%5BX%5D%20for%20each%20item%0A-%20%5B%20%5D%20Display%20partial%20indicators%20with%20exclusion%20count%20badge%0A-%20%5B%20%5D%20Implement%20%60_renderTree()%60%20method%0A-%20%5B%20%5D%20Implement%20%60_onRemoveClick(path)%60%20handler%0A-%20%5B%20%5D%20Implement%20%60_updatePartialIndicators()%20method%0A-%20%5B%20%5D%20Test%20rendering%2050%20files%20%E2%80%94%20no%20lag%0A-%20%5B%20%5D%20Test%20removal%20%E2%80%94%20item%20disappears%2C%20exclusion%20tracked%0A%0A%23%23%23%20D2.%20Browser%20Upload%20Right%20Pane%0A%0ACreate%20right-pane%20display%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Show%20same%20file%2Ffolder%20structure%20as%20left%20(synchronized)%0A-%20%5B%20%5D%20Display%20partial%20indicators%20%E2%98%A0%EF%B8%8F%20with%20counts%0A-%20%5B%20%5D%20Do%20NOT%20show%20removed%20items%20(pre-filtered)%0A-%20%5B%20%5D%20Show%20batch%20summary%20%22X%20selected%2C%20Y%20excluded%22%0A-%20%5B%20%5D%20Test%20removal%20on%20left%20→%20right%20updates%0A%0A%23%23%20Acceptance%20Criteria%0A%0A-%20%5B%20%5D%20Tree%20displays%20uploaded%20files%2Ffolders%0A-%20%5B%20%5D%20Remove%20buttons%20functional%0A-%20%5B%20%5D%20Removed%20items%20disappear%20from%20both%20panes%0A-%20%5B%20%5D%20Partial%20indicators%20show%20correct%20counts%0A-%20%5B%20%5D%20Left%2Fright%20panes%20synchronized%0A-%20%5B%20%5D%20No%20performance%20issues%20with%2050%2B%20files%0A-%20%5B%20%5D%20All%20unit%20tests%20passing%0A%0A%23%23%20Design%20Reference%0A%0A%5BIntake%20Wizard%20UX%20Mockups%5D(/docs/features/model_catalog/design/intake-wizard-mockups.md)%20-%20Browser%20variant%0A%0A%23%23%20Related%0A%0A-%20Depends%20on%3A%20I1%2C%20I4%0A-%20Blocks%3A%20I7%0A-%20Peer%3A%20I6%0A-%20%5BImplementation%20Breakdown%5D(issue-1324-implementation-breakdown.md))

---

## I6: Frontend — Source Step Server Mode

**Effort**: 3–4 days | **Blocks**: I7 | **Depends on**: I1, I4  
**Parent**: #1324

[**➤ CREATE THIS ISSUE**](https://github.com/rsocko/hass-bambulab-config/issues/new?title=I6:%20Frontend%20%E2%80%94%20Source%20Step%20Server%20Mode&body=%23%23%20Parent%20Issue%0A%23%231324%20%E2%80%94%20Unified%20%22Pick%20a%20Folder%22%20UX%20with%20removal%20semantics%0A%0A%23%23%20Summary%0A%0AImplement%20Server%20Inbox%20Source%20step%20with%20folder%20navigation%2C%20selection%20consolidation%2C%20removal%20handling%2C%20partial%20indicators%2C%20and%20synchronized%20left%2Fright%20panes.%0A%0A%23%23%20Implementation%20Scope%0A%0A%23%23%23%20E1.%20Server%20Navigation%20%26%20Selection%20Consolidation%0A%0AUpdate%20server%20browser%20to%20consolidate%20overlapping%20selections%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20When%20user%20selects%20%60%2Fmodels%2F%60%2C%20render%20children%20as%20%22selected%22%20(grayed)%0A-%20%5B%20%5D%20If%20user%20tries%20to%20select%20child%20%60%2Fmodels%2Fvariants%2F%60%2C%20absorb%20into%20parent%0A-%20%5B%20%5D%20Show%20consolidation%20visually%3A%20%22included%20in%20parent%22%20indicator%0A-%20%5B%20%5D%20Implement%20%60_onFolderSelect(path)%60%20handler%0A-%20%5B%20%5D%20Implement%20%60_renderSelectedIndicator()%60%0A-%20%5B%20%5D%20Test%20overlap%20consolidation%0A%0A%23%23%23%20E2.%20Server%20Removal%20Handling%0A%0AImplement%20file%2Ffolder%20removal%20from%20selected%20parents%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Implement%20%60_onRemoveClick(path)%60%20handler%0A-%20%5B%20%5D%20Add%20item%20to%20exclusions%0A-%20%5B%20%5D%20Update%20tree%20display%20(item%20disappears)%0A-%20%5B%20%5D%20Update%20right%20pane%0A-%20%5B%20%5D%20Test%20removal%20from%20various%20depths%0A%0A%23%23%23%20E3.%20Server%20Right%20Pane%0A%0ACreate%20right-pane%20display%20for%20server%20mode%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Show%20only%20topmost%20selected%20entries%20(consolidated)%0A-%20%5B%20%5D%20Breadcrumb%20navigation%20shared%20with%20left%0A-%20%5B%20%5D%20When%20navigating%20into%20subfolder%20on%20left%2C%20right%20also%20navigates%0A-%20%5B%20%5D%20Show%20%22Part%20of%3A%20%2Fmodels%2Fgridfinity%2F%22%20when%20viewing%20subfolder%0A-%20%5B%20%5D%20Display%20partial%20indicators%20and%20exclusion%20counts%0A%0A%23%23%23%20E4.%20Partial%20Folder%20Indicators%20Component%0A%0ACreate%20%60%3Cpartial-folder-badge%3E%60%20component%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Accept%20folder%20path%20and%20excluded%20count%0A-%20%5B%20%5D%20Render%20%22%F0%9F%93%81%20folder%20%E2%9A%A0%EF%B8%8F%20N%20items%20excluded%22%0A-%20%5B%20%5D%20Display%20on%20both%20left%20and%20right%20panes%0A-%20%5B%20%5D%20Test%20badge%20accuracy%20with%20multiple%20folders%0A%0A%23%23%20Acceptance%20Criteria%0A%0A-%20%5B%20%5D%20Overlapping%20selections%20consolidated%20(parent%20absorbs%20children)%0A-%20%5B%20%5D%20Children%20shown%20as%20%22selected%22%2C%20grayed%20out%0A-%20%5B%20%5D%20Removal%20buttons%20functional%2C%20items%20disappear%0A-%20%5B%20%5D%20Left%2Fright%20panes%20synchronized%20during%20navigation%0A-%20%5B%20%5D%20Breadcrumb%20identical%20on%20both%20sides%0A-%20%5B%20%5D%20Partial%20indicators%20display%20correctly%0A-%20%5B%20%5D%20Right%20pane%20shows%20only%20topmost%20entries%0A-%20%5B%20%5D%20All%20unit%20tests%20passing%0A%0A%23%23%20Design%20Reference%0A%0A%5BIntake%20Wizard%20UX%20Mockups%5D(/docs/features/model_catalog/design/intake-wizard-mockups.md)%20-%20Server%20variant%0A%0A%23%23%20Related%0A%0A-%20Depends%20on%3A%20I1%2C%20I4%0A-%20Blocks%3A%20I7%0A-%20Peer%3A%20I5%0A-%20%5BImplementation%20Breakdown%5D(issue-1324-implementation-breakdown.md))

---

## I7: Frontend — Organize & Validate Step Integration

**Effort**: 2 days | **Blocks**: I8 | **Depends on**: I1, I2, I3, I5, I6  
**Parent**: #1324

[**➤ CREATE THIS ISSUE**](https://github.com/rsocko/hass-bambulab-config/issues/new?title=I7:%20Frontend%20%E2%80%94%20Organize%20%26%20Validate%20Step%20Integration&body=%23%23%20Parent%20Issue%0A%23%231324%20%E2%80%94%20Unified%20%22Pick%20a%20Folder%22%20UX%20with%20removal%20semantics%0A%0A%23%23%20Summary%0A%0AIntegrate%20excluded%20items%20into%20Organize%20and%20Validate%20steps.%20Implement%20recursive%20override%20warning%20and%20exclusion%20summary%20check.%0A%0A%23%23%20Implementation%20Scope%0A%0A%23%23%23%20G1.%20Organize%20Step%20Pre-Filtering%0A%0AUpdate%20Organize%20step%20to%20work%20with%20pre-filtered%20files%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Receive%20%60excluded_items%60%20from%20Source%20step%0A-%20%5B%20%5D%20Call%20%60_prefilter_excluded_items()%60%20before%20grouping%0A-%20%5B%20%5D%20Show%20grouping%20results%20based%20on%20pre-filtered%20list%0A-%20%5B%20%5D%20Never%20show%20removed%20files%20in%20Organize%0A-%20%5B%20%5D%20Test%20grouping%20with%20exclusions%0A%0A%23%23%23%20G2.%20Recursive%20Override%20Warning%0A%0AImplement%20recursive%20toggle%20with%20warning%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Add%20recursive%20toggle%3A%20%5BOn%20%E2%95%BE%5D%20%2F%20%5BOff%20%E2%95%BE%5D%0A-%20%5B%20%5D%20If%20user%20changes%20from%20current%3A%20show%20warning%0A-%20%5B%20%5D%20Message%3A%20%22%E2%9A%A0%EF%B8%8F%20Non-recursive%20will%20exclude%20N%20subfolders%22%0A-%20%5B%20%5D%20Update%20%60excluded_items%60%20array%20(additive)%0A-%20%5B%20%5D%20Test%20toggle%20true%20→%20false%0A-%20%5B%20%5D%20Test%20no%20warning%20if%20no%20change%0A%0A%23%23%23%20H1.%20Validate%20Step%20Exclusion%20Check%0A%0ADisplay%20exclusion%20summary%20in%20Validate%20checklist%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Display%20%60excluded_items_summary%60%20check%20in%20checklist%0A-%20%5B%20%5D%20Message%3A%20%22N%20files%20excluded%20from%20selected%20sources.%20Proceeding%20with%20M%20remaining%20items.%22%0A-%20%5B%20%5D%20Always%20show%20check%20(even%20if%200%20excluded)%0A-%20%5B%20%5D%20Check%20marked%20as%20passed%20(not%20blocking)%0A-%20%5B%20%5D%20Test%20with%200%20exclusions%0A-%20%5B%20%5D%20Test%20with%205%20exclusions%0A%0A%23%23%20Acceptance%20Criteria%0A%0A-%20%5B%20%5D%20Organize%20receives%20pre-filtered%20files%0A-%20%5B%20%5D%20Grouping%20uses%20only%20non-excluded%20items%0A-%20%5B%20%5D%20Removed%20files%20not%20shown%20in%20Organize%0A-%20%5B%20%5D%20Recursive%20override%20shows%20warning%20and%20adds%20exclusions%0A-%20%5B%20%5D%20Validate%20displays%20exclusion%20summary%20check%0A-%20%5B%20%5D%20Check%20always%20passes%20(informational)%0A-%20%5B%20%5D%20All%20unit%20tests%20passing%0A%0A%23%23%20Related%0A%0A-%20Depends%20on%3A%20I1%2C%20I2%2C%20I3%2C%20I5%2C%20I6%0A-%20Blocks%3A%20I8%0A-%20%5BImplementation%20Breakdown%5D(issue-1324-implementation-breakdown.md))

---

## I8: Frontend & Backend — Browser Upload Filtering + End-to-End Integration

**Effort**: 2 days | **Depends on**: All prior issues | **Parent**: #1324

[**➤ CREATE THIS ISSUE**](https://github.com/rsocko/hass-bambulab-config/issues/new?title=I8:%20Browser%20Upload%20Filtering%20%26%20End-to-End%20Integration&body=%23%23%20Parent%20Issue%0A%23%231324%20%E2%80%94%20Unified%20%22Pick%20a%20Folder%22%20UX%20with%20removal%20semantics%0A%0A%23%23%20Summary%0A%0AImplement%20client-side%20filtering%20for%20Browser%20upload%20(exclude%20removed%20items%20before%20upload)%20and%20run%20full%20end-to-end%20integration%20tests.%0A%0A%23%23%20Implementation%20Scope%0A%0A%23%23%23%20I1.%20Browser%20Upload%20File%20Filtering%0A%0AFilter%20excluded%20items%20client-side%20before%20upload%3A%0A%0A**Tasks:**%0A-%20%5B%20%5D%20Implement%20%60_prepareFilesForUpload(files%2C%20excluded)%60%0A-%20%5B%20%5D%20Filter%20files%20to%20exclude%20any%20in%20%60excluded_items%60%20array%0A-%20%5B%20%5D%20Only%20upload%20non-excluded%20files%20to%20sidecar%0A-%20%5B%20%5D%20Test%2050%20files%2C%205%20excluded%20→%20only%2045%20uploaded%0A-%20%5B%20%5D%20Test%20exclusions%20applied%20correctly%0A%0A%23%23%23%20Integration%20%26%20Testing%0A%0ARun%20full%20end-to-end%20scenarios%3A%0A%0A**Test%20Scenario%201:%20Server%20Selection%20%2B%20Removal**%0A-%20%5B%20%5D%20Source%3A%20user%20removes%20file%20→%20exclusion%20badge%0A-%20%5B%20%5D%20Organize%3A%20file%20not%20in%20grouping%0A-%20%5B%20%5D%20Validate%3A%20exclusion%20count%20shown%0A-%20%5B%20%5D%20Commit%3A%20file%20not%20imported%0A-%20%5B%20%5D%20Result%3A%20only%20non-excluded%20files%20in%20working%20group%0A%0A**Test%20Scenario%202:%20Browser%20Upload%20%2B%20Removal**%0A-%20%5B%20%5D%20Source%3A%20file%20removed%2C%20exclusion%20tracked%0A-%20%5B%20%5D%20Upload%3A%20only%20non-excluded%20files%20sent%0A-%20%5B%20%5D%20Organize%3A%20file%20not%20in%20grouping%0A-%20%5B%20%5D%20Validate%3A%20exclusion%20count%20shown%0A-%20%5B%20%5D%20Result%3A%20file%20never%20reaches%20sidecar%0A%0A**Test%20Scenario%203:%20Recursive%20Override**%0A-%20%5B%20%5D%20Source%3A%20%2Fmodels%2F%20selected%2C%20recursive%3Dtrue%2C%20nothing%20removed%0A-%20%5B%20%5D%20Organize%3A%20user%20changes%20to%20recursive%3Dfalse%0A-%20%5B%20%5D%20Warning%3A%20%22Non-recursive%20will%20exclude%208%20subfolders%22%0A-%20%5B%20%5D%20Validate%3A%20exclusion%20count%20updated%0A-%20%5B%20%5D%20Result%3A%20only%20top-level%20files%20imported%0A%0A%23%23%20Performance%20Tests%0A%0A-%20%5B%20%5D%20500-file%20folder%3A%20UI%20doesn%27t%20lag%20on%20expansion%0A-%20%5B%20%5D%201000%20exclusions%3A%20pre-filtering%20still%20fast%0A-%20%5B%20%5D%20Large%20tree%20navigation%3A%20left%2Fright%20sync%20smooth%0A%0A%23%23%20Acceptance%20Criteria%0A%0A-%20%5B%20%5D%20Browser%20upload%20filters%20excluded%20files%20client-side%0A-%20%5B%20%5D%20Only%20non-excluded%20files%20uploaded%0A-%20%5B%20%5D%20All%20end-to-end%20scenarios%20working%0A-%20%5B%20%5D%20All%20integration%20tests%20passing%0A-%20%5B%20%5D%20No%20performance%20regressions%0A-%20%5B%20%5D%20Manual%20QA%20complete%0A%0A%23%23%20Related%0A%0A-%20Depends%20on%3A%20All%20prior%20issues%20(I1–I7)%0A-%20%5BImplementation%20Breakdown%5D(issue-1324-implementation-breakdown.md))

---

## Issue Dependencies & Suggested Parent/Child Links

After creating all issues, link them as follows (GitHub "Linked issues" feature):

```
I1 (Schema & Consolidation)
  ├─ I2 (Grouping & Pre-filtering)
  ├─ I3 (Validation)
  └─ I4 (State Management)

I5 (Browser Source Step)
  └─ I7 (Organize & Validate Integration)
     └─ I8 (End-to-End Testing)

I6 (Server Source Step)
  └─ I7 (Organize & Validate Integration)
     └─ I8 (End-to-End Testing)
```

**Parent-child suggestion**:
- Set #1324 as parent of all 8 issues (epic)
- Consider grouping I1–I4 as "Backend Foundation" and I5–I8 as "Frontend & Integration"

---

## Implementation Timeline

| Week | Issues | Focus | Estimated Effort |
|------|--------|-------|-----------------|
| **Week 1** | I1–I4 | Backend foundation: schema, consolidation, validation | 1 FTE |
| **Week 2** | I5–I6 | Frontend Source step: Browser + Server modes | 1.5 FTE |
| **Week 3** | I7–I8 | Integration + testing + polish | 1 FTE |

**Total**: ~3.5 FTE-weeks or 4 weeks for one developer

---

## Next Steps

1. Click each issue link above to create them in GitHub
2. Manually link them with parent/child relationships
3. Assign to development team
4. Update labels: `#1324`, `intake-wizard`, `phase-2`, etc.
5. Reference this breakdown document in each issue description

