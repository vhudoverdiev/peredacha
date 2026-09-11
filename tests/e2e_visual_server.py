from __future__ import annotations

import argparse
import os
import signal
import sys
from datetime import date, timedelta
from pathlib import Path

from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app, db
import app.security as security
from app.models import (
    Apartment,
    Project,
    ROLE_ADMIN,
    ROLE_MANAGER,
    STATUS_DONE,
    STATUS_NOT_STARTED,
    STATUS_PROBLEM,
    Task,
    User,
    WorkCategory,
    WorkPoint,
)
from app.time_utils import utc_now
from config import Config


class E2EVisualConfig(Config):
    TESTING = False
    SECRET_KEY = "e2e-visual-secret-key"
    SQLALCHEMY_DATABASE_URI = os.environ["E2E_VISUAL_DATABASE_URL"]
    WTF_CSRF_ENABLED = False
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

    db.session.add_all([project, user, developer, work_point, all_category, qa_category])
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
