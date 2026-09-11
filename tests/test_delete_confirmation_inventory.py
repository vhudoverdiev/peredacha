from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "templates"


class DeleteConfirmationInventoryTests(unittest.TestCase):
    def read_template(self, name):
        return (TEMPLATES / name).read_text(encoding="utf-8")

    def test_every_data_confirm_delete_control_is_covered_by_the_shared_modal(self):
        expected_locations = {
            "contractor_directory.html": 1,
            "apartment_detail.html": 1,
            "glass_measurements.html": 2,
            "material_request_detail.html": 1,
            "materials.html": 4,
            "task_detail.html": 1,
            "task_list.html": 1,
        }
        actual_locations = {}
        for template_path in TEMPLATES.glob("*.html"):
            count = self.read_template(template_path.name).count("data-confirm=")
            if count:
                actual_locations[template_path.name] = count

        self.assertEqual(actual_locations, expected_locations)

        script = (ROOT / "app" / "static" / "script.js").read_text(encoding="utf-8")
        handler_start = script.index("document.addEventListener('submit', event => {", script.index("const showCrmActionConfirm"))
        handler_end = script.index("\ndocument.addEventListener('DOMContentLoaded', () => {", handler_start)
        handler = script[handler_start:handler_end]
        self.assertIn("submitter?.dataset?.confirmResolved", handler)
        self.assertIn("submitter?.dataset?.confirm", handler)
        self.assertIn("form.dataset.confirm", handler)
        self.assertIn("event.preventDefault()", handler)
        self.assertIn("form.dataset.confirmed = '1'", handler)
        self.assertIn("form.requestSubmit(submitter)", handler)

    def test_shared_delete_modal_has_all_safe_cancel_and_confirm_paths(self):
        script = (ROOT / "app" / "static" / "script.js").read_text(encoding="utf-8")
        start = script.index("const showCrmActionConfirm")
        end = script.index("window.crmShowActionConfirm = showCrmActionConfirm", start)
        modal = script[start:end]

        self.assertIn("cancel.onclick = () => close(false)", modal)
        self.assertIn("ok.onclick = () => close(true)", modal)
        self.assertIn("if (event.target === modal) close(false)", modal)
        self.assertIn("if (event.key === 'Escape') close(false)", modal)
        self.assertIn("if (settled) return", modal)

    def test_glass_ajax_delete_waits_for_confirmation_before_fetch(self):
        script = (ROOT / "app" / "static" / "script.js").read_text(encoding="utf-8")
        start = script.index("const bindGlassDeleteForm")
        end = script.index("const submitGlassNeedMeasureForm", start)
        handler = script[start:end]

        confirmation = handler.index("await window.crmShowActionConfirm(confirmMessage)")
        request = handler.index("fetch(form.action")
        self.assertLess(confirmation, request)

    def test_assignment_delete_waits_for_confirmation_before_fetch_or_native_submit(self):
        template = self.read_template("assignments.html")
        self.assertIn("assignment-remove-user-form", template)
        self.assertIn("assignment-remove-user-btn", template)

        script = (ROOT / "app" / "static" / "script.js").read_text(encoding="utf-8")
        start = script.index("const removeIssuedAssignment")
        end = script.index("// Capture the deliberate tap", start)
        handler = script[start:end]
        confirmation = handler.index("await window.crmShowConfirm({")
        rejection = handler.index("if (!confirmed) return;")
        native_submit = handler.index("form.submit()")
        request = handler.index("fetch(form.action")
        self.assertLess(confirmation, rejection)
        self.assertLess(rejection, native_submit)
        self.assertLess(rejection, request)

    def test_object_and_user_delete_pages_are_real_confirmation_dialogs(self):
        cases = {
            "object_delete_confirm.html": ("deleteObjectTitle", "main.object_delete", "main.objects"),
            "user_delete_confirm.html": ("deleteUserTitle", "main.user_delete", "main.users"),
        }
        for template_name, (title_id, delete_endpoint, cancel_endpoint) in cases.items():
            with self.subTest(template=template_name):
                template = self.read_template(template_name)
                self.assertIn('role="dialog"', template)
                self.assertIn('aria-modal="true"', template)
                self.assertIn(f'aria-labelledby="{title_id}"', template)
                self.assertIn(f"url_for('{delete_endpoint}'", template)
                self.assertIn(f"url_for('{cancel_endpoint}'", template)
                self.assertRegex(template, r'<button class="btn btn-danger" type="submit">')

    def test_site_error_delete_modal_binds_the_selected_record_and_can_cancel(self):
        template = self.read_template("site_errors.html")
        self.assertIn('data-bs-target="#deleteErrorModal"', template)
        self.assertIn('data-delete-url="{{ url_for(\'main.site_error_delete\'', template)
        self.assertIn('id="deleteErrorForm"', template)
        self.assertIn('data-bs-dismiss="modal"', template)
        self.assertIn('form.action = button.getAttribute(\'data-delete-url\') || \'\'', template)
        self.assertIn("if (!form.action)", template)
        self.assertIn("event.preventDefault()", template)

    def test_each_sync_log_delete_trigger_targets_its_own_confirmation_modal(self):
        template = self.read_template("sync_logs.html")
        self.assertIn('data-bs-target="#deleteLogModal{{ log.id }}"', template)
        self.assertIn('id="deleteLogModal{{ log.id }}"', template)
        self.assertIn("url_for('main.delete_sync_log', log_id=log.id)", template)
        delete_modal = template[template.index('<div class="modal fade crm-modal" id="deleteLogModal'):]
        self.assertIn('data-bs-dismiss="modal"', delete_modal)
        self.assertRegex(
            delete_modal,
            re.compile(r'<button class="btn sync-modal-btn sync-modal-btn-delete" type="submit">'),
        )


if __name__ == "__main__":
    unittest.main()
