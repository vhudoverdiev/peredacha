from __future__ import annotations

import argparse
import os
import signal
import sys
from datetime import date, time, timedelta
from pathlib import Path

from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app, db
import app.security as security
from app.models import (
    Apartment,
    InspectionBooking,
    InspectionSlot,
    Project,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_OFFICE_MANAGER,
    STATUS_DONE,
    STATUS_NOT_STARTED,
    STATUS_PROBLEM,
    Task,
    User,
    WorkCategory,
    WorkPoint,
)
from app.time_utils import to_moscow_datetime, utc_now
from config import Config


class E2EVisualConfig(Config):
    TESTING = False
    ALLOW_SQLITE_RUNTIME = True
    SECRET_KEY = "e2e-visual-secret-key"
    SQLALCHEMY_DATABASE_URI = os.environ["E2E_VISUAL_DATABASE_URL"]
    WTF_CSRF_ENABLED = os.environ.get("E2E_VISUAL_CSRF_ENABLED") == "1"
    SESSION_COOKIE_SECURE = False
    TRUSTED_PROXY_COUNT = 0
    FORCE_HSTS = False
    UPLOAD_FOLDER = os.environ["E2E_VISUAL_UPLOAD_FOLDER"]
    EXPORT_FOLDER = os.environ["E2E_VISUAL_EXPORT_FOLDER"]


def seed_database() -> None:
    db.drop_all()
    db.create_all()

    project = Project(
        name="E2E Visual Baseline",
        address="Visual Test Street",
        has_apartments=True,
        has_commercial=True,
    )
    user = User(
        username="e2e-admin",
        full_name="E2E Admin",
        role=ROLE_MANAGER,
        project=project,
        all_projects_access=False,
        captcha_disabled=True,
    )
    user.set_password("E2E-visual-password-2026!")
    developer = User(
        username="e2e-developer",
        full_name="E2E Developer",
        role=ROLE_ADMIN,
        project=None,
        all_projects_access=True,
        captcha_disabled=True,
    )
    developer.set_password("E2E-developer-password-2026!")
    office_manager = User(
        username="e2e-office-manager",
        full_name="Офис Менеджер",
        role=ROLE_OFFICE_MANAGER,
        project=project,
        all_projects_access=False,
        captcha_disabled=True,
    )
    office_manager.set_password("E2E-office-password-2026!")

    work_point = WorkPoint(
        point_number="10",
        original_column_name="E2E visual work point",
        short_name="E2E visual",
        source_sheet_name="e2e_visual",
        source_column_index=10,
        is_active=True,
    )
    all_category = WorkCategory(
        name="\u0412\u0441\u0435",
        color="#75bd18",
        sort_order=0,
        is_active=True,
    )
    qa_category = WorkCategory(
        name="E2E Visual",
        color="#75bd18",
        sort_order=10,
        is_active=True,
    )
    all_category.work_points.append(work_point)
    qa_category.work_points.append(work_point)

    db.session.add_all([project, user, developer, office_manager, work_point, all_category, qa_category])
    db.session.flush()

    apartments = []
    for number in range(1, 27):
        apartments.append(
            Apartment(
                project=project,
                apartment_number=str(number),
                construction_number=f"C-{number}",
                owner_name=f"Owner {number}",
                phone=f"+7 900 000-{number:04d}",
                finishing_type="White Box" if number % 2 else "Shell",
                inspection_date=date.today() - timedelta(days=number),
                first_inspection_present=True,
            )
        )
    db.session.add_all(apartments)
    db.session.flush()

    if os.environ.get("E2E_CALL_LIST_FIXTURES") == "1":
        for index in (0, 1, 9, 19):
            apartments[index].po_status = "thrown"
            apartments[index].po_status_manual = True

    statuses = [STATUS_NOT_STARTED, STATUS_DONE, STATUS_PROBLEM]
    for index, apartment in enumerate(apartments[:8], start=1):
        status = statuses[index % len(statuses)]
        db.session.add(
            Task(
                source_uid=f"e2e-visual-task-{index}",
                project=project,
                apartment=apartment,
                work_point=work_point,
                title=f"E2E task {index}",
                description=f"E2E visual remark {index}",
                source_cell_value=f"E2E visual remark {index}",
                status=status,
                is_done=status == STATUS_DONE,
                completed_date=utc_now() if status == STATUS_DONE else None,
                source_sheet_name="e2e_visual",
                source_row_index=index + 1,
                source_column_index=10,
                source_cell_address=f"J{index + 1}",
            )
        )

    if os.environ.get("E2E_EXTENDED_FIXTURES") == "1":
        # Opt-in regressions need long lists and source-specific point copies.
        # Normal visual baselines keep their original fixtures.
        user.all_projects_access = True
        user.full_name = "Иванов Иван Иванович"
        developer.full_name = "Петров Пётр Петрович"
        db.session.add_all(Project(name=f"Scroll QA object {index}") for index in range(20))
        apartments[0].floor = "2"
        apartments[0].first_inspection_date = date(2026, 2, 1)
        apartments[0].inspection_date = date(2026, 6, 1)
        for number in ("15", "22", "24"):
            for sheet in ("Таблица", "Кладовые"):
                point = WorkPoint(point_number=number, short_name=f"QA point {number}", source_sheet_name=sheet)
                db.session.add(Task(source_uid=f"mapping-{number}-{sheet}", project=project,
                                    apartment=apartments[0], work_point=point, description="Mapping QA remark"))
    if os.environ.get("E2E_WORKER_FIXTURES") == "1":
        second_project = Project(name="Второй объект — длинное название для проверки переноса")
        second_apartment = Apartment(project=second_project, apartment_number="173")
        db.session.add_all([second_project, second_apartment]); db.session.flush()
        forbidden_project = Project(name="Недоступный объект для осмотров")
        forbidden_apartment = Apartment(project=forbidden_project, apartment_number="999")
        db.session.add(forbidden_apartment)
        db.session.flush()
        inspection_today = to_moscow_datetime(utc_now()).date()
        for room, day, begins in ((apartments[0], inspection_today, time(9, 15)),
                                  (second_apartment, inspection_today, time(10)),
                                  (forbidden_apartment, inspection_today, time(11)),
                                  (apartments[1], inspection_today + timedelta(days=1), time(12))):
            slot = InspectionSlot(project=room.project, day=day, start_time=begins, duration_minutes=30)
            db.session.add(slot)
            db.session.flush()
            db.session.add(InspectionBooking(slot=slot, active_slot_id=slot.id, apartment=room,
                                            created_by=developer, contact="Личные данные собственника",
                                            contact_phone="+79991112233", status="booked"))
        for role in ("painter", "handyman", "glazier"):
            worker = User(username="qa-" + role, role=role, full_name="Петров Пётр Петрович",
                          project=project, captcha_disabled=True)
            worker.set_password("Worker-qa-password-2026!")
            worker.set_project_access([project.id, second_project.id])
            db.session.add(worker)
            db.session.add(Task(source_uid=f"worker-{role}-second", project=second_project,
                                apartment=second_apartment, work_point=work_point, responsible=worker,
                                planned_date=date.today(), description="Замечание на втором объекте"))
            for index in range(5):
                db.session.add(Task(source_uid=f"worker-{role}-{index}", project=project,
                                    apartment=apartments[0], work_point=work_point, responsible=worker,
                                    planned_date=date.today(), description=f"Работа {index + 1}: устранить замечание и проверить результат."))

    db.session.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    Path(E2EVisualConfig.UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
    Path(E2EVisualConfig.EXPORT_FOLDER).mkdir(parents=True, exist_ok=True)

    app = create_app(E2EVisualConfig)
    security.record_site_visit = lambda _response: None
    with app.app_context():
        seed_database()

    server = make_server(args.host, args.port, app, threaded=True)

    def shutdown(*_args):
        server.shutdown()

    signal.signal(signal.SIGTERM, shutdown)
    print(f"E2E_VISUAL_SERVER_READY http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
