from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app" / "templates" / "apartments.html").read_text(encoding="utf-8")


def test_po_floating_widget_is_limited_to_engineer_and_developer():
    condition = "{% if current_user.role in ['admin', 'manager'] %}"
    widget = 'class="po-notification-widget"'

    condition_index = TEMPLATE.index(condition)
    widget_index = TEMPLATE.index(widget)
    endif_index = TEMPLATE.index("{% endif %}", widget_index)

    assert condition_index < widget_index < endif_index
