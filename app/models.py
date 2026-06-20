from __future__ import annotations

from datetime import date, datetime
import re
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from app import db


ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_EXECUTOR = "executor"
ROLE_PAINTER = "painter"
ROLE_HANDYMAN = "handyman"
ROLE_GLAZIER = "glazier"
ROLE_VERIFIER = "verifier"
ROLE_VIEWER = "viewer"
WORKER_ROLES = {ROLE_EXECUTOR, ROLE_PAINTER, ROLE_HANDYMAN, ROLE_GLAZIER}
ROLE_LABELS = {
    ROLE_ADMIN: "Инженер",
    ROLE_MANAGER: "Инженер",
    ROLE_EXECUTOR: "Маляр",
    ROLE_PAINTER: "Маляр",
    ROLE_HANDYMAN: "Разнорабочий",
    ROLE_GLAZIER: "Витражник",
    ROLE_VERIFIER: "Сверщик",
    ROLE_VIEWER: "Просмотр",
}
USER_ROLE_CHOICES = [
    (ROLE_ADMIN, "Инженер"),
    (ROLE_PAINTER, "Маляр"),
    (ROLE_HANDYMAN, "Разнорабочий"),
    (ROLE_GLAZIER, "Витражник"),
    (ROLE_VERIFIER, "Сверщик"),
]
ROLES = [ROLE_ADMIN, ROLE_MANAGER, ROLE_EXECUTOR, ROLE_PAINTER, ROLE_HANDYMAN, ROLE_GLAZIER, ROLE_VERIFIER, ROLE_VIEWER]

STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"
STATUS_FINISHERS = "finishers"
STATUS_CONTRACTOR = "contractor"
STATUS_PROBLEM = "problem"
STATUS_REVIEW = "review"
STATUS_POSTPONED = "postponed"

TASK_STATUSES = {
    STATUS_DONE: {"label": "Выполнено", "class": "success"},
    STATUS_FINISHERS: {"label": "Чистовики", "class": "info"},
    STATUS_CONTRACTOR: {"label": "Подрядчик", "class": "warning"},
    STATUS_PROBLEM: {"label": "Проблема", "class": "danger"},
    STATUS_NOT_STARTED: {"label": "Не выполнено", "class": "secondary"},
}
DONE_STATUSES = {STATUS_DONE, STATUS_FINISHERS, STATUS_CONTRACTOR}

PRIORITIES = ["low", "normal", "high", "critical"]

category_workpoint = db.Table(
    "category_workpoint",
    db.Column("category_id", db.Integer, db.ForeignKey("work_categories.id"), primary_key=True),
    db.Column("work_point_id", db.Integer, db.ForeignKey("work_points.id"), primary_key=True),
)

material_writeoff_tasks = db.Table(
    "material_writeoff_tasks",
    db.Column("writeoff_id", db.Integer, db.ForeignKey("material_writeoffs.id"), primary_key=True),
    db.Column("task_id", db.Integer, db.ForeignKey("tasks.id"), primary_key=True),
)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    password_plain = db.Column(db.String(255), nullable=True)
    full_name = db.Column(db.String(160), nullable=True)
    role = db.Column(db.String(30), default=ROLE_VIEWER, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True, index=True)
    failed_login_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    last_login_ip = db.Column(db.String(80), nullable=True)
    session_version = db.Column(db.Integer, default=0, nullable=False)

    assigned_tasks = db.relationship("Task", back_populates="responsible", foreign_keys="Task.responsible_id")
    project = db.relationship("Project")
    site_error_reports = db.relationship("SiteErrorReport", back_populates="user")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)
        # Пароли больше не хранятся в открытом виде: это закрывает утечку через БД/логи/экран пользователей.
        self.password_plain = None
        self.failed_login_count = 0
        self.locked_until = None
        self.session_version = int(self.session_version or 0) + 1

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def can(self, *roles: str) -> bool:
        return self.role in roles or self.role == ROLE_ADMIN

    def __repr__(self):
        return f"<User {self.username}>"


class Project(TimestampMixin, db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False, index=True)
    queue = db.Column(db.String(120), nullable=True)
    building = db.Column(db.String(120), nullable=True)
    section = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    google_sheet_id = db.Column(db.String(255), nullable=True)
    has_apartments = db.Column(db.Boolean, default=True, nullable=False)
    has_commercial = db.Column(db.Boolean, default=True, nullable=False)
    has_storerooms = db.Column(db.Boolean, default=False, nullable=False)

    apartments = db.relationship("Apartment", back_populates="project", cascade="all, delete-orphan")
    tasks = db.relationship("Task", back_populates="project", cascade="all, delete-orphan")
    material_requests = db.relationship("MaterialRequest", back_populates="project", cascade="all, delete-orphan")
    material_writeoffs = db.relationship("MaterialWriteOff", back_populates="project", cascade="all, delete-orphan")
    glass_measurements = db.relationship("GlassMeasurement", back_populates="project", cascade="all, delete-orphan")
    site_error_reports = db.relationship("SiteErrorReport", back_populates="project", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Project {self.name}>"


class Apartment(TimestampMixin, db.Model):
    __tablename__ = "apartments"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    apartment_number = db.Column(db.String(80), nullable=True, index=True)
    construction_number = db.Column(db.String(80), nullable=True, index=True)
    owner_name = db.Column(db.String(180), nullable=True, index=True)
    is_unsold = db.Column(db.Boolean, default=False, nullable=False, index=True)
    phone = db.Column(db.String(100), nullable=True, index=True)
    finishing_type = db.Column(db.String(160), nullable=True, index=True)
    premise_type = db.Column(db.String(30), default="apartment", nullable=False, index=True)
    building = db.Column(db.String(50), nullable=True, index=True)
    entrance = db.Column(db.String(50), nullable=True)
    floor = db.Column(db.String(50), nullable=True)
    inspection_date = db.Column(db.Date, nullable=True)
    first_inspection_date = db.Column(db.Date, nullable=True)
    first_inspection_present = db.Column(db.Boolean, default=False, nullable=False, index=True)
    reinspection_date = db.Column(db.Date, nullable=True)
    deadline_date = db.Column(db.Date, nullable=True)
    remark_deadline_date = db.Column(db.Date, nullable=True)
    inspection_note = db.Column(db.Text, nullable=True)
    is_app_mode = db.Column(db.Boolean, default=False, nullable=False, index=True)
    po_status = db.Column(db.String(30), default="not_ready", nullable=False, index=True)
    po_status_manual = db.Column(db.Boolean, default=False, nullable=False, index=True)
    avr_archived_at = db.Column(db.DateTime, nullable=True)
    avr_status = db.Column(db.String(30), default="needed", nullable=False, index=True)
    avr_signed_date = db.Column(db.Date, nullable=True)
    app_deadline_date = db.Column(db.Date, nullable=True)
    app_deadline_raw = db.Column(db.String(255), nullable=True)
    app_deadline_status = db.Column(db.String(30), default="normal", nullable=False, index=True)
    comment = db.Column(db.Text, nullable=True)
    source_row_id = db.Column(db.String(180), nullable=True, index=True)

    project = db.relationship("Project", back_populates="apartments")
    tasks = db.relationship("Task", back_populates="apartment", cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint("project_id", "construction_number", "apartment_number", name="uq_apartment_identity"),
    )

    def label(self) -> str:
        number = self.apartment_number or self.construction_number or f"ID {self.id}"
        if self.premise_type == "commercial":
            return self._commercial_label(number)
        return f"кв {number}"

    def full_label(self) -> str:
        number = self.apartment_number or self.construction_number or f"ID {self.id}"
        if self.premise_type == "commercial":
            commercial_number, commercial_building, fallback = self._commercial_parts(number)
            if commercial_number and commercial_building:
                return f"Коммерция {commercial_number}/Корпус {commercial_building}"
            if commercial_number:
                return f"Коммерция {commercial_number}"
            return f"Коммерция {fallback}".strip()
        return f"кв {number}"

    def detail_label(self) -> str:
        number = self.apartment_number or self.construction_number or f"ID {self.id}"
        if self.premise_type == "commercial":
            return self.full_label()
        return f"Квартира {number}"

    def _commercial_parts(self, number: str | None) -> tuple[str, str, str]:
        text = str(number or "").strip()
        text = re.sub(r"^коммерци[яи]\s*", "", text, flags=re.IGNORECASE).strip()
        building = str(self.building or "").strip()
        building = re.sub(r"^(?:к|корпус)\s*", "", building, flags=re.IGNORECASE).strip()

        pair_match = re.match(r"^к?\s*(\d+)\s*/\s*(?:к|корпус)?\s*(\d+)\s*$", text, flags=re.IGNORECASE)
        if pair_match:
            commercial_number, parsed_building = pair_match.groups()
            return commercial_number, building or parsed_building, text

        simple_match = re.match(r"^к?\s*(\d+)\s*$", text, flags=re.IGNORECASE)
        if simple_match:
            return simple_match.group(1), building, text

        return "", building, text

    def _commercial_label(self, number: str) -> str:
        commercial_number, commercial_building, fallback = self._commercial_parts(number)
        if commercial_number and commercial_building:
            return f"К{commercial_number}/К{commercial_building}"
        if commercial_number:
            return f"К{commercial_number}"
        return f"К {fallback}".strip()

    @staticmethod
    def _is_no_deadline_text(value: str | None) -> bool:
        text = " ".join(str(value or "").strip().lower().replace("ё", "е").split())
        return not text or "без замечаний" in text

    def app_deadline_label(self) -> str:
        """Единое отображение срока устранения по колонке Excel «Срок устранения замечаний  по АПП»."""
        if self.app_deadline_date:
            return self.app_deadline_date.strftime("%d.%m.%Y")
        raw = str(self.app_deadline_raw or "").strip()
        if raw and not self._is_no_deadline_text(raw):
            return raw
        return "Нет срока"

    def app_deadline_badge(self, today: date | None = None) -> dict | None:
        """Статус показываем только для реальной даты. «Без замечаний»/пусто = нет срока без тревожной плашки."""
        if not self.app_deadline_date:
            return None
        today = today or date.today()
        days_left = (self.app_deadline_date - today).days
        if days_left < 0:
            return {"label": "Срок истёк", "class": "expired", "days_left": days_left}
        if days_left <= 15:
            return {"label": "Истекает", "class": "expiring", "days_left": days_left}
        return None


class WorkPoint(TimestampMixin, db.Model):
    __tablename__ = "work_points"

    id = db.Column(db.Integer, primary_key=True)
    point_number = db.Column(db.String(30), nullable=False, index=True)
    original_column_name = db.Column(db.String(255), nullable=True)
    short_name = db.Column(db.String(160), nullable=True)
    description = db.Column(db.Text, nullable=True)
    source_sheet_name = db.Column(db.String(160), nullable=True, index=True)
    source_column_index = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    categories = db.relationship("WorkCategory", secondary=category_workpoint, back_populates="work_points")
    tasks = db.relationship("Task", back_populates="work_point")

    __table_args__ = (
        db.UniqueConstraint("point_number", "source_sheet_name", name="uq_workpoint_number_sheet"),
    )

    @property
    def display_name(self):
        return self.short_name or self.original_column_name or f"Пункт {self.point_number}"


class WorkCategory(TimestampMixin, db.Model):
    __tablename__ = "work_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    color = db.Column(db.String(30), default="#6c757d", nullable=True)
    sort_order = db.Column(db.Integer, default=100, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    work_points = db.relationship("WorkPoint", secondary=category_workpoint, back_populates="categories")

    def __repr__(self):
        return f"<WorkCategory {self.name}>"


class Task(TimestampMixin, db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    source_uid = db.Column(db.String(64), unique=True, nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    apartment_id = db.Column(db.Integer, db.ForeignKey("apartments.id"), nullable=False, index=True)
    work_point_id = db.Column(db.Integer, db.ForeignKey("work_points.id"), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    source_cell_value = db.Column(db.Text, nullable=True)
    responsible_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    status = db.Column(db.String(30), default=STATUS_NOT_STARTED, nullable=False, index=True)
    priority = db.Column(db.String(30), default="normal", nullable=False, index=True)
    planned_date = db.Column(db.Date, nullable=True, index=True)
    completed_date = db.Column(db.DateTime, nullable=True, index=True)
    comment = db.Column(db.Text, nullable=True)
    source_sheet_name = db.Column(db.String(160), nullable=True, index=True)
    source_row_index = db.Column(db.Integer, nullable=True)
    source_column_index = db.Column(db.Integer, nullable=True)
    source_cell_address = db.Column(db.String(50), nullable=True)
    source_hash = db.Column(db.String(64), nullable=True)
    is_done = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_missing_in_latest_sync = db.Column(db.Boolean, default=False, nullable=False, index=True)
    manually_edited = db.Column(db.Boolean, default=False, nullable=False, index=True)
    last_seen_at = db.Column(db.DateTime, nullable=True, index=True)

    project = db.relationship("Project", back_populates="tasks")
    apartment = db.relationship("Apartment", back_populates="tasks")
    work_point = db.relationship("WorkPoint", back_populates="tasks")
    responsible = db.relationship("User", back_populates="assigned_tasks", foreign_keys=[responsible_id])
    changes = db.relationship("ChangeLog", back_populates="task", cascade="all, delete-orphan", order_by="desc(ChangeLog.created_at)")
    comments = db.relationship("TaskComment", back_populates="task", cascade="all, delete-orphan", order_by="desc(TaskComment.created_at)")
    glass_measurement = db.relationship("GlassMeasurement", back_populates="task", uselist=False, cascade="all, delete-orphan")

    def status_label(self) -> str:
        return TASK_STATUSES.get(self.status, {}).get("label", self.status)

    def status_class(self) -> str:
        return TASK_STATUSES.get(self.status, {}).get("class", "secondary")


class MaterialRequest(TimestampMixin, db.Model):
    __tablename__ = "material_requests"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    request_date = db.Column(db.Date, default=date.today, nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    title = db.Column(db.String(255), nullable=True, index=True)
    comment = db.Column(db.Text, nullable=True)

    project = db.relationship("Project", back_populates="material_requests")
    author = db.relationship("User")
    items = db.relationship("MaterialRequestItem", back_populates="request", cascade="all, delete-orphan")


class MaterialRequestItem(TimestampMixin, db.Model):
    __tablename__ = "material_request_items"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("material_requests.id"), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False, default=0)
    unit = db.Column(db.String(50), nullable=False, index=True)

    request = db.relationship("MaterialRequest", back_populates="items")


class MaterialWriteOff(TimestampMixin, db.Model):
    __tablename__ = "material_writeoffs"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    writeoff_date = db.Column(db.Date, default=date.today, nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    comment = db.Column(db.Text, nullable=True)

    project = db.relationship("Project", back_populates="material_writeoffs")
    author = db.relationship("User")
    tasks = db.relationship("Task", secondary=material_writeoff_tasks, backref=db.backref("material_writeoffs", lazy="dynamic"))
    items = db.relationship("MaterialWriteOffItem", back_populates="writeoff", cascade="all, delete-orphan")


class MaterialWriteOffItem(TimestampMixin, db.Model):
    __tablename__ = "material_writeoff_items"

    id = db.Column(db.Integer, primary_key=True)
    writeoff_id = db.Column(db.Integer, db.ForeignKey("material_writeoffs.id"), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False, default=0)
    unit = db.Column(db.String(50), nullable=False, index=True)

    writeoff = db.relationship("MaterialWriteOff", back_populates="items")


class GlassMeasurement(TimestampMixin, db.Model):
    __tablename__ = "glass_measurements"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False, unique=True, index=True)
    apartment_id = db.Column(db.Integer, db.ForeignKey("apartments.id"), nullable=True, index=True)
    size = db.Column(db.String(160), nullable=True)  # старое поле, оставлено для совместимости
    width = db.Column(db.Float, nullable=True)
    height = db.Column(db.Float, nullable=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    glass_type = db.Column(db.String(160), nullable=True)
    status = db.Column(db.String(30), default="none", nullable=False, index=True)
    comment = db.Column(db.Text, nullable=True)
    measured_at = db.Column(db.Date, nullable=True, index=True)
    ordered_at = db.Column(db.Date, nullable=True, index=True)
    replaced_at = db.Column(db.Date, nullable=True, index=True)
    material_request_item_id = db.Column(db.Integer, db.ForeignKey("material_request_items.id"), nullable=True, index=True)

    project = db.relationship("Project", back_populates="glass_measurements")
    task = db.relationship("Task", back_populates="glass_measurement")
    apartment = db.relationship("Apartment")
    material_request_item = db.relationship("MaterialRequestItem")
    items = db.relationship("GlassMeasurementItem", back_populates="measurement", cascade="all, delete-orphan", order_by="GlassMeasurementItem.id")

    @property
    def glass_status(self) -> str:
        return self.status or "none"

    def status_label(self) -> str:
        labels = {
            "none": "Без замера",
            "not_ordered": "Сделать замер",
            "measure_needed": "Сделать замер",
            "measured": "Замер внесён",
            "ordered": "Заказано",
            "replaced": "Поменяно",
        }
        return labels.get(self.status or "none", self.status or "Без замера")

    def size_label(self) -> str:
        parts = []
        if self.width:
            parts.append(str(int(self.width) if float(self.width).is_integer() else self.width))
        if self.height:
            parts.append(str(int(self.height) if float(self.height).is_integer() else self.height))
        if len(parts) == 2:
            return "×".join(parts)
        return self.size or ""


class GlassMeasurementItem(TimestampMixin, db.Model):
    __tablename__ = "glass_measurement_items"

    id = db.Column(db.Integer, primary_key=True)
    measurement_id = db.Column(db.Integer, db.ForeignKey("glass_measurements.id"), nullable=False, index=True)
    item_type = db.Column(db.String(80), nullable=False, default="Стеклопакет", index=True)
    width = db.Column(db.Float, nullable=False)
    height = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    size = db.Column(db.String(160), nullable=True)

    measurement = db.relationship("GlassMeasurement", back_populates="items")

    def size_label(self) -> str:
        if self.size:
            return self.size
        width = str(int(self.width) if float(self.width).is_integer() else self.width)
        height = str(int(self.height) if float(self.height).is_integer() else self.height)
        return f"{width}×{height}"

    def title_label(self) -> str:
        return f"{self.item_type or 'Стеклопакет'} {self.size_label()}".strip()


class SyncConflict(TimestampMixin, db.Model):
    __tablename__ = "sync_conflicts"

    id = db.Column(db.Integer, primary_key=True)
    # task_id оставлен nullable для новых баз: несостыковки теперь могут быть не только
    # по замечанию, но и по данным помещения (АПП, сроки, дата осмотра и т.д.).
    # В старых SQLite-базах колонка может оставаться NOT NULL, поэтому при импорте
    # для квартирных конфликтов мы привязываем ближайшую задачу как fallback.
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=True, index=True)
    apartment_id = db.Column(db.Integer, db.ForeignKey("apartments.id"), nullable=True, index=True)
    target_type = db.Column(db.String(30), nullable=False, default="task", index=True)  # task/apartment
    field_name = db.Column(db.String(120), nullable=True)
    field_label = db.Column(db.String(160), nullable=True)

    source_type = db.Column(db.String(30), nullable=False, default="excel")
    source_name = db.Column(db.String(255), nullable=True)

    sheet_name = db.Column(db.String(160), nullable=True, index=True)
    row_index = db.Column(db.Integer, nullable=True, index=True)
    column_index = db.Column(db.Integer, nullable=True, index=True)
    cell_address = db.Column(db.String(50), nullable=True)

    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    old_hash = db.Column(db.String(64), nullable=True)
    new_hash = db.Column(db.String(64), nullable=True)

    status = db.Column(db.String(20), nullable=False, default="pending", index=True)  # pending/keep_old/apply_new
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    task = db.relationship("Task")
    apartment = db.relationship("Apartment")
    resolved_by = db.relationship("User")


class TaskComment(TimestampMixin, db.Model):
    __tablename__ = "task_comments"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)

    task = db.relationship("Task", back_populates="comments")
    user = db.relationship("User")


class ChangeLog(db.Model):
    __tablename__ = "change_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False, index=True)
    action = db.Column(db.String(120), nullable=False)
    field_name = db.Column(db.String(120), nullable=True)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    task = db.relationship("Task", back_populates="changes")
    user = db.relationship("User")


class SyncLog(db.Model):
    __tablename__ = "sync_logs"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True, index=True)
    source_type = db.Column(db.String(50), nullable=False, index=True)
    source_name = db.Column(db.String(255), nullable=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), default="running", nullable=False, index=True)
    created_count = db.Column(db.Integer, default=0, nullable=False)
    updated_count = db.Column(db.Integer, default=0, nullable=False)
    missing_count = db.Column(db.Integer, default=0, nullable=False)
    error_message = db.Column(db.Text, nullable=True)
    rolled_back_at = db.Column(db.DateTime, nullable=True)
    rollback_note = db.Column(db.Text, nullable=True)
    rollback_data = db.Column(db.Text, nullable=True)

    project = db.relationship("Project")

    @property
    def is_rolled_back(self) -> bool:
        return self.rolled_back_at is not None


class SiteErrorReport(TimestampMixin, db.Model):
    __tablename__ = "site_error_reports"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    kind = db.Column(db.String(30), default="user", nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    page_url = db.Column(db.String(500), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    traceback_text = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default="new", nullable=False, index=True)

    project = db.relationship("Project", back_populates="site_error_reports")
    user = db.relationship("User", back_populates="site_error_reports")


class DeletionActionLog(TimestampMixin, db.Model):
    __tablename__ = "deletion_action_logs"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    action_key = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(80), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=True, index=True)
    entity_title = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    snapshot_json = db.Column(db.Text, nullable=True)
    is_undone = db.Column(db.Boolean, default=False, nullable=False, index=True)
    undone_at = db.Column(db.DateTime, nullable=True)
    undone_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    project = db.relationship("Project")
    user = db.relationship("User", foreign_keys=[user_id])
    undone_by = db.relationship("User", foreign_keys=[undone_by_user_id])


class SecurityEvent(TimestampMixin, db.Model):
    __tablename__ = "security_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    kind = db.Column(db.String(80), nullable=False, index=True)
    severity = db.Column(db.String(30), default="info", nullable=False, index=True)
    ip_address = db.Column(db.String(80), nullable=True, index=True)
    path = db.Column(db.String(500), nullable=True)
    method = db.Column(db.String(20), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    message = db.Column(db.Text, nullable=True)

    user = db.relationship("User")


class AppSetting(TimestampMixin, db.Model):
    __tablename__ = "app_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
