from app import db
from app.models import AppSetting, WorkCategory, WorkPoint

DEFAULT_CATEGORIES = [
    ("Все", "#212529", 0),
    ("Маляры", "#79bf25", 10),
    ("Разнорабочие", "#79bf25", 20),
    ("Витражники", "#79bf25", 30),
    ("Доп.Соглашение", "#6c757d", 80),
]

DEFAULT_POINT_MAPPING = {
    "Маляры": ["10", "11", "12"],
    "Разнорабочие": ["13", "14", "15"],
    "Витражники": ["18"],
    # Материалы по доп. соглашению лежат в пункте 24. Даты 25+ не импортируем как задачи.
    "Доп.Соглашение": ["24"],
}

MAIN_POINT_NUMBERS = {str(number) for number in range(10, 23)}
DOP_AGREEMENT_POINT_NUMBERS = {"24"}
VISIBLE_POINT_NUMBERS = MAIN_POINT_NUMBERS | DOP_AGREEMENT_POINT_NUMBERS
HIDDEN_POINT_NUMBERS = {str(number) for number in range(1, 101)} - VISIBLE_POINT_NUMBERS

REMOVED_CATEGORIES = {
    "Электрики", "Сантехники", "Двери", "Окна ПВХ", "Другое",
}


def _mapping_custom_key(category_id: int) -> str:
    return f"category_mapping_customized:{int(category_id)}"


def _mapping_is_customized(category_id: int) -> bool:
    setting = AppSetting.query.filter_by(key=_mapping_custom_key(category_id)).first()
    return str(setting.value or "").strip() == "1" if setting else False


def _mark_mapping_customized(category_id: int, customized: bool = True) -> None:
    key = _mapping_custom_key(category_id)
    setting = AppSetting.query.filter_by(key=key).first()
    value = "1" if customized else "0"
    if setting is None:
        setting = AppSetting(key=key, value=value)
        db.session.add(setting)
    else:
        setting.value = value


def ensure_default_categories():
    default_names = {name for name, _, _ in DEFAULT_CATEGORIES}
    for name, color, sort_order in DEFAULT_CATEGORIES:
        category = WorkCategory.query.filter_by(name=name).first()
        if category is None:
            category = WorkCategory(name=name, color=color, sort_order=sort_order, is_active=True)
            db.session.add(category)
        else:
            category.color = color
            category.sort_order = sort_order
            category.is_active = True

    for category in WorkCategory.query.all():
        if category.name in default_names:
            continue
        if category.name in REMOVED_CATEGORIES or category.name not in default_names:
            category.is_active = False

    db.session.flush()
    for category in WorkCategory.query.all():
        category.work_points = [point for point in category.work_points if point.point_number not in HIDDEN_POINT_NUMBERS]
    apply_default_point_mapping(commit=False)


def apply_default_point_mapping(commit: bool = True):
    for category_name, point_numbers in DEFAULT_POINT_MAPPING.items():
        category = WorkCategory.query.filter_by(name=category_name).first()
        if not category:
            continue
        if _mapping_is_customized(category.id):
            continue
        visible_numbers = [point_number for point_number in point_numbers if point_number not in HIDDEN_POINT_NUMBERS]
        points = WorkPoint.query.filter(WorkPoint.point_number.in_(visible_numbers)).all()
        for point in points:
            if point not in category.work_points:
                category.work_points.append(point)
    if commit:
        db.session.commit()


def update_category_points(category_id: int, point_ids: list[int], *, commit: bool = True):
    category = db.session.get(WorkCategory, category_id)
    if not category:
        raise ValueError("Category not found")
    points = WorkPoint.query.filter(WorkPoint.id.in_(point_ids)).all() if point_ids else []
    category.work_points = points
    _mark_mapping_customized(category.id, True)
    if commit:
        db.session.commit()
    return category
