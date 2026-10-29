"""Acceptance contracts for the durable worker status API."""
from datetime import timedelta
from uuid import uuid4
import unittest
from flask import g
from app import db
from app.models import Task, ChangeLog, WorkerOfflineOperation
from app.services.worker_offline import version
from tests import test_worker_task_updates as fixture


class WorkerOfflineOperationTests(unittest.TestCase):
    setUp = fixture.WorkerTaskUpdatesTests.setUp
    tearDown = fixture.WorkerTaskUpdatesTests.tearDown
    login = fixture.WorkerTaskUpdatesTests.login

    def operation(self, **changes):
        data=dict(operation_id=str(uuid4()),account_id=self.worker.id,task_id=self.task.id,
                  version=version(self.task),previous_status=self.task.status,new_status='in_progress',
                  created_at='2026-10-29T10:00:00Z')
        data.update(changes)
        return data

    def send(self, data):
        return self.client.post('/worker-offline/operation',json=data,
                                headers={'Accept':'application/json','X-Requested-With':'XMLHttpRequest'})

    def test_duplicate_receives_original_acknowledgement_without_second_history(self):
        data=self.operation()
        first=self.send(data);self.assertEqual(first.status_code,200,first.data)
        count=ChangeLog.query.filter_by(task_id=self.task.id,action='status_change').count()
        self.assertEqual(self.send(data).json,first.json)
        self.assertEqual(ChangeLog.query.filter_by(task_id=self.task.id,action='status_change').count(),count)
        self.assertEqual(WorkerOfflineOperation.query.count(),1)

    def test_ordered_changes_use_acknowledged_version(self):
        a=self.send(self.operation());self.assertEqual(a.status_code,200)
        b=self.send(self.operation(version=a.json['task']['version'],previous_status='in_progress',new_status='done'))
        self.assertEqual(b.status_code,200,b.data)
        self.assertTrue(db.session.get(Task,self.task.id).is_done)

    def test_conflicting_status_is_not_overwritten(self):
        data=self.operation()
        self.task.status='done';self.task.is_done=True;db.session.commit()
        result=self.send(data)
        self.assertEqual(result.status_code,409)
        self.assertEqual(result.json['code'],'conflict')
        self.assertEqual(result.json['task']['status'],'done')
        self.assertEqual(WorkerOfflineOperation.query.count(),0)

    def test_reassignment_and_wrong_account_are_rejected(self):
        data=self.operation(account_id=self.other.id)
        self.assertEqual(self.send(data).status_code,403)
        data=self.operation();self.task.responsible_id=self.other.id;db.session.commit()
        self.assertEqual(self.send(data).status_code,403)

    def test_removed_task_and_invalid_transition_are_rejected(self):
        data=self.operation(new_status='problem')
        self.assertEqual(self.send(data).status_code,422)
        data=self.operation();self.task.is_archived=True;db.session.commit()
        self.assertEqual(self.send(data).status_code,410)

    def test_operation_id_cannot_be_reused_with_different_payload(self):
        data=self.operation();self.assertEqual(self.send(data).status_code,200)
        data['new_status']='done'
        self.assertEqual(self.send(data).status_code,409)

    def test_snapshot_contains_future_tasks_without_pagination(self):
        self.task.planned_date=self.task.planned_date+timedelta(days=900);db.session.commit()
        response=self.client.get('/worker-offline/snapshot',headers={'Accept':'application/json'})
        self.assertEqual(response.status_code,200,response.data)
        self.assertIn(self.task.id,[t['id'] for t in response.json['tasks']])
        self.assertIn(f'data-task-id="{self.task.id}"',response.json['html'])
        self.assertEqual(response.json['offline_hours'],72)

    def test_expired_session_returns_json_and_does_not_change_tasks(self):
        data=self.operation()
        self.client.post('/logout');g.pop('_login_user',None)
        response=self.send(data)
        self.assertEqual(response.status_code,401,response.data)
        self.assertEqual(WorkerOfflineOperation.query.count(),0)

    def test_legacy_status_endpoint_still_works(self):
        response=self.client.post(f'/my-tasks/{self.task.id}/status',data={'status':'in_progress'},
                                  headers={'Accept':'application/json','X-Requested-With':'XMLHttpRequest'})
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.json['status'],'in_progress')

    def test_duplicate_after_later_change_returns_ack_without_overwriting(self):
        data=self.operation();first=self.send(data)
        self.task.status='done';self.task.is_done=True;db.session.commit()
        self.assertEqual(self.send(data).json,first.json)
        self.assertEqual(db.session.get(Task,self.task.id).status,'done')

    def test_csrf_required_and_fresh_token_works(self):
        self.app.config['WTF_CSRF_ENABLED']=True
        data=self.operation()
        self.assertEqual(self.send(data).status_code,400)
        snapshot=self.client.get('/worker-offline/snapshot',headers={'Accept':'application/json'}).json
        token=snapshot['csrf_token']
        data['version']=snapshot['tasks'][0]['version']
        result=self.client.post('/worker-offline/operation',json=data,headers={'X-CSRFToken':token,'Accept':'application/json'})
        self.assertEqual(result.status_code,200,result.data)
