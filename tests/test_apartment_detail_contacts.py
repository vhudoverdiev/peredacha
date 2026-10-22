import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app" / "templates" / "apartment_detail.html").read_text(encoding="utf-8")
APARTMENTS_TEMPLATE = (ROOT / "app" / "templates" / "apartments.html").read_text(encoding="utf-8")
MODELS = (ROOT / "app" / "models.py").read_text(encoding="utf-8")
ROUTES = (ROOT / "app" / "routes.py").read_text(encoding="utf-8")
APP_INIT = (ROOT / "app" / "__init__.py").read_text(encoding="utf-8")
STYLE = (ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")
SCRIPT = (ROOT / "app" / "static" / "script.js").read_text(encoding="utf-8")


class ApartmentDetailContactsTests(unittest.TestCase):
    def test_detail_shows_owner_and_phone_for_desktop_and_mobile(self):
        self.assertIn("ФИО", TEMPLATE)
        self.assertIn("Номер телефона", TEMPLATE)
        self.assertIn("row.owner_names|join(', ') if row.owner_names else '—'", TEMPLATE)
        self.assertIn("{% for phone in row.phones %}", TEMPLATE)
        self.assertIn("{% if not loop.last %}<br>{% endif %}", TEMPLATE)
        self.assertIn('name="phone" rows="{{ [row.phones|length, 2]|max }}"', TEMPLATE)
        self.assertNotIn('name="phone" type="text"', TEMPLATE)

    def test_detail_renders_contract_number_and_multiline_owner_editor(self):
        self.assertIn('"contract_number": _apartment_contract_number(apartment)', ROUTES)
        self.assertIn("def _apartment_contract_number(apartment: Apartment) -> str:", ROUTES)
        self.assertIn("row.contract_number", TEMPLATE)
        self.assertIn("<span>По договору</span>", TEMPLATE)
        self.assertIn('name="contract_number"', TEMPLATE)
        self.assertIn('form="apartment-details-form-{{ apartment.id }}"', TEMPLATE)
        self.assertIn("const fieldSelector = '[name=\"owner_name\"], [name=\"phone\"], [name=\"contract_number\"], [name=\"construction_number\"], [name=\"finishing_type\"], [name=\"mode\"]';", TEMPLATE)
        self.assertIn("field.form === form || (formId && field.getAttribute('form') === formId)", TEMPLATE)
        self.assertIn('class="form-control form-control-sm apartment-owner-names-control"', TEMPLATE)
        self.assertIn("row.owner_names|join('\\n') if row.owner_names else ''", TEMPLATE)
        self.assertIn(".apartment-owner-names-control", STYLE)

    def test_detail_fields_autosave_without_manual_save_button(self):
        self.assertIn('data-apartment-details-autosave="1"', TEMPLATE)
        self.assertIn("'X-Requested-With': 'XMLHttpRequest'", TEMPLATE)
        self.assertIn("field.value === 'unsold'", TEMPLATE)
        self.assertNotIn("Сохранить данные", TEMPLATE)
        self.assertIn("data-apartment-detail-sidebar", TEMPLATE)
        self.assertIn("data-apartment-history-card", TEMPLATE)
        self.assertIn("refreshRenderedSections(refreshSidebar)", TEMPLATE)
        self.assertIn("currentHistory.replaceWith(nextHistory)", TEMPLATE)
        self.assertIn("currentSidebar.replaceWith(nextSidebar)", TEMPLATE)
        self.assertIn("initApartmentDetailsAutosave()", TEMPLATE)
        self.assertNotIn("AbortController", TEMPLATE)

    def test_office_role_cannot_edit_apartment_comments_or_see_internal_status(self):
        self.assertIn("current_user.role not in ['viewer', 'office', 'office_manager']", TEMPLATE)
        self.assertIn("current_user.role not in ['viewer', 'office', 'office_manager']", APARTMENTS_TEMPLATE)
        self.assertIn("current_user.role not in ['office', 'office_manager']", TEMPLATE)
        self.assertIn("current_user.role not in ['office', 'office_manager']", APARTMENTS_TEMPLATE)
        self.assertIn("update_apartment_comment", TEMPLATE)
        self.assertIn("update_apartment_inspection_note", TEMPLATE)
        self.assertIn("update_apartment_po_status", TEMPLATE)
        self.assertIn("update_apartment_po_status", APARTMENTS_TEMPLATE)

    def test_apartment_comments_have_separate_labels(self):
        for label in ("Комментарий (Офис)", "Комментарий (Инженеры)", "Комментарий (Офис-Менеджер)"):
            self.assertIn(label, TEMPLATE)
            self.assertIn(label, APARTMENTS_TEMPLATE)
        self.assertNotIn("row.mode == 'АПП' and current_user.role", TEMPLATE)
        self.assertNotIn("row.mode == 'не принята' and current_user.role", TEMPLATE)

    def test_apartment_comment_display_controls_are_not_part_of_editor_header(self):
        comment_display = TEMPLATE.split('data-apartment-comment-display', 1)[1].split("</div>", 1)[0]
        note_display = TEMPLATE.split('data-apartment-inspection-note-display', 1)[1].split("</div>", 1)[0]
        comment_form_head = TEMPLATE.split('for="apartment-comment-', 1)[1].split("</div>", 1)[0]
        note_form_head = TEMPLATE.split('for="inspection-note-', 1)[1].split("</div>", 1)[0]

        self.assertIn('data-clear-note-form="apartment-comment-form-{{ apartment.id }}"', comment_display)
        self.assertIn("{% if not has_manual_comment %} hidden{% endif %}", comment_display)
        self.assertIn('data-clear-note-form="inspection-note-form-{{ apartment.id }}"', note_display)
        self.assertIn("{% if not has_inspection_comment %} hidden{% endif %}", note_display)
        self.assertNotIn("data-clear-note-button", comment_form_head)
        self.assertNotIn("data-clear-note-button", note_form_head)
        self.assertIn('id="apartment-comment-form-{{ apartment.id }}"', TEMPLATE)
        self.assertIn('id="inspection-note-form-{{ apartment.id }}"', TEMPLATE)
        self.assertIn("manual_comment_text not in ['-', '—']", TEMPLATE)
        self.assertIn("inspection_comment_text not in ['-', '—']", TEMPLATE)

    def test_apartment_comment_display_is_plain_and_has_no_autosave_caption(self):
        note_rule = STYLE.split("html body.app-body .apartment-detail-page .apartment-data-note > p {", 1)[1].split("}", 1)[0]

        self.assertIn("font-weight: 400 !important;", note_rule)
        self.assertNotIn("Сохраняется автоматически", STYLE)
        self.assertIn("syncApartmentNoteClearButton", SCRIPT)
        self.assertIn("button.getAttribute('data-clear-note-form')", SCRIPT)
        self.assertIn("normalizedValue === '-' || normalizedValue === '—'", SCRIPT)

    def test_correction_comment_is_internal_crm_field(self):
        self.assertIn("correction_comment = db.Column(db.Text", MODELS)
        self.assertIn("ALTER TABLE apartments ADD COLUMN correction_comment TEXT", APP_INIT)
        self.assertIn("apartment.correction_comment", ROUTES)
        update_start = ROUTES.index("def update_apartment_inspection_note")
        update_end = ROUTES.index("@bp.route(\"/apartments/<int:apartment_id>/comment\"", update_start)
        update_route = ROUTES[update_start:update_end]
        self.assertIn("item.correction_comment = note or None", update_route)
        self.assertNotIn("item.inspection_note = note or None", update_route)

    def test_unsold_apartment_detail_hides_inspection_row(self):
        self.assertIn("row.mode != 'не продана'", TEMPLATE)
        self.assertNotIn("Для непроданной квартиры осмотр фиксируется автоматически", TEMPLATE)

    def test_inspection_reset_hover_matches_save_button_green(self):
        start = STYLE.index(".apartment-inspection-reset-btn:hover")
        end = STYLE.index(".apartment-detail-page .apartment-task-item:hover", start)
        rule = STYLE[start:end]

        self.assertIn(
            "background: linear-gradient(180deg, var(--peredacha-action-green) 0%, var(--peredacha-action-green-hover) 100%) !important;",
            rule,
        )
        self.assertIn("border-color: var(--peredacha-action-green-hover) !important;", rule)
        self.assertNotIn("var(--peredacha-action-green-dark)", rule)

    def test_inspection_date_picker_stacks_above_reset_action(self):
        controls_selector = (
            "html body.app-body .apartment-detail-page "
            ".apartment-compact-control-row:has([data-apartment-inspection-display]) "
            ".apartment-inline-controls {"
        )
        controls_start = STYLE.index(controls_selector)
        controls_rule = STYLE[controls_start:STYLE.index("}", controls_start)]
        input_selector = (
            "html body.app-body .apartment-detail-page "
            ".apartment-compact-control-row:has([data-apartment-inspection-display]) "
            ".apartment-inspection-date-form .form-control {"
        )
        input_start = STYLE.index(input_selector)
        input_rule = STYLE[input_start:STYLE.index("}", input_start)]

        self.assertIn("flex-direction: column !important;", controls_rule)
        self.assertIn("justify-self: end !important;", controls_rule)
        self.assertIn("width: 8.45rem !important;", controls_rule)
        self.assertIn("font-size: .72rem !important;", input_rule)
        self.assertIn("min-height: 2rem !important;", input_rule)

    def test_mobile_inspection_controls_fill_card_width_without_right_column_offset(self):
        marker = "/* Keep apartment inspection controls inside the mobile detail card. */"
        self.assertIn(marker, STYLE)
        start = STYLE.index(marker)
        end = STYLE.index("/* v667:", start)
        mobile_rules = STYLE[start:end]

        self.assertIn("grid-template-columns: minmax(0, 1fr) !important;", mobile_rules)
        self.assertIn("justify-items: stretch !important;", mobile_rules)
        self.assertIn("grid-template-columns: minmax(0, 1fr) auto !important;", mobile_rules)
        self.assertIn(".apartment-inspection-reset-btn {", mobile_rules)
        self.assertIn("min-height: 2.75rem !important;", mobile_rules)

    def test_inspection_dates_stack_and_controls_align_in_value_column(self):
        controls_selector = (
            "html body.app-body .apartment-detail-page "
            ".apartment-compact-control-row:has([data-apartment-inspection-display]) .apartment-inline-controls {"
        )
        controls_start = STYLE.rindex(controls_selector)
        controls_rule = STYLE[controls_start:STYLE.index("}", controls_start)]
        date_stack_start = STYLE.rindex("html body.app-body .apartment-detail-page .apartment-inspection-date-stack {")
        date_stack_rule = STYLE[date_stack_start:STYLE.index("}", date_stack_start)]

        self.assertIn("[data-apartment-inspection-display] > span:not(.status-pill):not(.apartment-inspection-date-stack)", STYLE)
        self.assertIn("margin: 0 !important;", controls_rule)
        self.assertIn("width: 100% !important;", controls_rule)
        self.assertIn("flex-direction: column !important;", date_stack_rule)
        self.assertIn("display: grid !important;", date_stack_rule)
        self.assertIn("grid-template-columns: minmax(0, max-content) !important;", date_stack_rule)
        self.assertIn("row-gap: .5rem !important;", date_stack_rule)
        mobile_controls_start = STYLE.rindex(
            "html:is(.mobile-viewport, .adaptive-mobile-viewport, .touch-app-device) "
            "body.app-body:has(.apartment-detail-page) "
            ".apartment-compact-control-row:has([data-apartment-inspection-display]) .apartment-inline-controls {"
        )
        self.assertIn("width: 100% !important;", STYLE[mobile_controls_start:STYLE.index("}", mobile_controls_start)])

    def test_mobile_delete_action_sits_next_to_problem_with_matching_dimensions(self):
        self.assertIn('class="apartment-task-actions actions-cell{% if task.status != \'problem\' %} has-delete-action{% endif %}"', TEMPLATE)
        self.assertIn('class="apartment-task-delete-mobile-form"', TEMPLATE)
        self.assertIn("{% if task.status != 'problem' %}", TEMPLATE)

        action_grid = STYLE[STYLE.index(".apartment-task-actions {"):STYLE.index(".apartment-task-actions {") + 2200]
        self.assertIn(".apartment-task-actions.has-delete-action .apartment-task-action-form-problem", action_grid)
        self.assertIn("grid-column: 1 !important;", action_grid)
        self.assertIn(".apartment-task-actions.has-delete-action .apartment-task-delete-mobile-form", action_grid)
        self.assertIn("grid-column: 2 !important;", action_grid)
        self.assertIn(".apartment-task-delete-mobile-btn", action_grid)
        self.assertIn("min-height: 2.66rem !important;", action_grid)

    def test_desktop_apartment_date_rows_do_not_collapse_when_window_narrows(self):
        override_start = STYLE.index("/* v671: keep apartment date/action rows in the same desktop layout")
        override = STYLE[override_start:]

        self.assertIn("@media (min-width: 768px)", override)
        self.assertIn("grid-template-columns: minmax(7.2rem, 8.2rem) minmax(7.1rem, 1fr) minmax(9.7rem, auto) !important;", override)
        self.assertIn("grid-column: auto !important;", override)
        self.assertIn("max-width: 9.7rem !important;", override)
        self.assertIn("grid-template-columns: minmax(5.05rem, 1.22fr) minmax(4.1rem, .95fr) !important;", override)
        self.assertIn("font-size: .62rem !important;", override)

    def test_app_dates_refresh_display_after_async_save(self):
        self.assertIn("data-apartment-app-signed-display", TEMPLATE)
        self.assertIn("data-apartment-app-deadline-display", TEMPLATE)
        self.assertIn("document.querySelectorAll('[data-apartment-app-signed-display]')", SCRIPT)
        self.assertIn("document.querySelectorAll('[data-apartment-app-deadline-display]')", SCRIPT)
        self.assertIn("appDeadlineInput.value = data.app_deadline_date || '';", SCRIPT)
        self.assertIn("const formatRuDateValue = (dateValue) =>", SCRIPT)
        self.assertIn("const syncAppDateDisplays = () =>", SCRIPT)
        self.assertIn("formatRuDateValue(deadlineInput.value) || 'Нет срока'", SCRIPT)

    def test_avr_date_autosave_keeps_current_status_and_refreshes_display(self):
        self.assertIn("form.classList.contains('apartment-avr-form')", SCRIPT)
        self.assertIn('button[name="avr_status"].btn-primary', SCRIPT)
        self.assertIn("formData.set('avr_status', activeAvrButton.value || '')", SCRIPT)
        self.assertIn("document.querySelectorAll('[data-apartment-avr-display]')", SCRIPT)
        self.assertIn("signedDateInput.value = data.avr_signed_date || '';", SCRIPT)

    def test_addendum_status_buttons_keep_text_on_one_line(self):
        selector = (
            'html body.app-body .apartment-detail-page '
            '.apartment-addendum-form button[name="addendum_status"]'
        )
        start = STYLE.index(selector)
        rule = STYLE[start:STYLE.index("}", start)]

        self.assertIn("width: 100% !important;", rule)
        self.assertIn("font-size: .68rem !important;", rule)
        self.assertIn("white-space: nowrap !important;", rule)
        self.assertIn("overflow: hidden !important;", rule)

    def test_hidden_note_clear_button_is_not_forced_visible(self):
        self.assertIn("apartment-note-clear-btn", TEMPLATE)
        self.assertIn("{% if not has_manual_comment %} hidden{% endif %}", TEMPLATE)
        self.assertIn("{% if not has_inspection_comment %} hidden{% endif %}", TEMPLATE)
        self.assertIn("html body.app-body .apartment-note-clear-btn[hidden]", STYLE)
        start = STYLE.index("html body.app-body .apartment-note-clear-btn[hidden]")
        rule = STYLE[start:STYLE.index("}", start)]
        self.assertIn("display: none !important;", rule)

    def test_addendum_row_matches_avr_date_control_pattern(self):
        self.assertIn('name="addendum_signed_date"', TEMPLATE)
        self.assertIn('class="apartment-addendum-status-actions"', TEMPLATE)
        self.assertNotIn("apartment-addendum-date-badge", TEMPLATE)
        self.assertIn("activeAddendumButton", SCRIPT)
        self.assertIn("formData.set('addendum_status', activeAddendumButton.value || '')", SCRIPT)
        self.assertIn("document.querySelectorAll('[data-apartment-addendum-display]')", SCRIPT)
        self.assertIn("signedDateInput.value = data.addendum_signed_date || '';", SCRIPT)


if __name__ == "__main__":
    unittest.main()
