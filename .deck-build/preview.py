from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date,timedelta,time
from flask import redirect,session
from flask_login import login_user
from werkzeug.serving import make_server
from app import create_app,db
from app.models import User,Project,Apartment,Task,WorkPoint,TaskComment,ChangeLog
from app.time_utils import utc_now,to_moscow_datetime
from config import Config
from app.models import Contractor,InspectionSlot,InspectionBooking
scratch=TemporaryDirectory();root=Path(scratch.name)
class PreviewConfig(Config):
 TESTING=True
 SECRET_KEY='isolated-preview-only'
 SQLALCHEMY_DATABASE_URI='sqlite://'
 WTF_CSRF_ENABLED=False
 SESSION_COOKIE_SECURE=False
 REMEMBER_COOKIE_SECURE=False
 UPLOAD_FOLDER=str(root/'uploads')
 EXPORT_FOLDER=str(root/'exports')
 SYNC_ON_STARTUP=False
app=create_app(PreviewConfig)
with app.app_context():
 project=Project(name='ЖК Листва',has_apartments=True)
 worker=User(username='preview_worker',full_name='Александр Иванов',role='painter',all_projects_access=True,captcha_disabled=True)
 worker.set_password('PreviewWorker123!')
 admin=User(username='preview_admin',full_name='Владимир',role='admin',all_projects_access=True,captcha_disabled=True)
 admin.set_password('PreviewAdmin123!')
 point=WorkPoint(point_number='11',short_name='Стены и потолки',source_sheet_name='preview')
 db.session.add_all([project,worker,admin,point]);db.session.flush()
 for i,(number,description,priority) in enumerate([
  ('42','Устранить трещину на стене в кухне и подготовить поверхность под покраску.','critical'),
  ('18','Выровнять поверхность стены возле дверного проёма.','normal'),
  ('63','Устранить следы строительной смеси на потолке.','normal')]):
  apt=Apartment(project=project,apartment_number=number,construction_number=f'1-3-{number}',finishing_type='Белая')
  task=Task(project=project,apartment=apt,work_point=point,responsible=worker,description=description,
    source_uid=f'preview-{i}',status='not_started',priority=priority,planned_date=to_moscow_datetime(utc_now()).date())
  db.session.add_all([apt,task]);db.session.flush()
  if i==0:db.session.add(TaskComment(task=task,user=worker,body='Материал получил. Приступаю к работе в первую очередь.'))
 # Previous and office comments attached to the same remark.
 first = Task.query.filter_by(source_uid='preview-0').one()
 first.comments[0].created_at = utc_now() - timedelta(days=2)
 db.session.add(ChangeLog(task=first, field_name='responsible_id', action='field_update',
                          new_value=str(worker.id), created_at=utc_now()-timedelta(days=1)))
 db.session.add(TaskComment(task=first,user=admin,body='Сначала устраните трещину. После завершения приложите комментарий о результате.'))
 done = Task.query.filter_by(source_uid='preview-2').one()
 done.status='done';done.is_done=True;done.completed_date=utc_now()
 glazier=User(username='preview_glazier',full_name='Сергей Петров',role='glazier',all_projects_access=True,captcha_disabled=True)
 glazier.set_password('PreviewGlazier123!')
 glass_point=WorkPoint(point_number='17',short_name='Работы по монтажу ПВХ блоков',source_sheet_name='preview')
 apt=Apartment(project=project,apartment_number='27',construction_number='1-2-27',finishing_type='Белая')
 glass_task=Task(project=project,apartment=apt,work_point=glass_point,responsible=glazier,
   description='Повреждён стеклопакет правой створки балконной двери.',source_uid='preview-glass',
   status='not_started',priority='normal',planned_date=to_moscow_datetime(utc_now()).date())
 db.session.add_all([glazier,glass_point,apt,glass_task])
 db.session.commit()
 apt42=Apartment.query.filter_by(apartment_number='42').one()
 apt42.owner_name='Мария Соколова'
 project.address='ул. Липовая, 8'
 c=Contractor(project=project,name='ООО «Стройсервис»',work_points=[point],apartments=[apt42])
 day=date(2026,11,5)
 slots=[InspectionSlot(project=project,day=day,start_time=time(10,m)) for m in (0,30)]
 db.session.add_all([c,*slots]);db.session.flush()
 db.session.add(InspectionBooking(slot=slots[0],active_slot_id=slots[0].id,apartment=apt42,staff=admin,created_by_id=admin.id,contact='Мария Соколова'))
 db.session.commit()
 glazier_id=glazier.id
 worker_id=worker.id;admin_id=admin.id;project_id=project.id
@app.route('/_preview_login/<kind>')
def preview_login(kind):
 user=db.session.get(User,worker_id if kind=='worker' else (glazier_id if kind=='glazier' else admin_id))
 login_user(user,remember=True)
 session.permanent=True
 session['session_version']=user.session_version or 0
 session['current_project_id']=project_id
 return redirect('/my-tasks' if kind in {'worker','glazier'} else '/assignments?view=issued')
print('PREVIEW_READY',flush=True)
make_server('127.0.0.1',5197,app,threaded=True).serve_forever()
