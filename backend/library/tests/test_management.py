from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from library import models as m
from library.services import operations
from library.services.common import rules
from library.tasks import maintenance, purge_expired


class ManagementTests(TestCase):
    def setUp(self):
        self.admin = m.User.objects.create_user(username='manager', phone='13911111111', role='admin', is_superuser=True)
        self.reader = m.User.objects.create_user(username='reader', phone='13922222222')
        self.operator = m.User.objects.create_user(username='operator', phone='13933333333', role='operator')
        self.branch = m.Branch.objects.create(name='管理测试馆', address='示例地址')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def post(self, route, data, key='test'):
        return self.client.post('/api/v1/'+route, data, format='json', HTTP_IDEMPOTENCY_KEY=key)

    def test_manage_credit_deposit_and_roles_with_audit(self):
        result = self.post(f'readers/{self.reader.pk}/manage/', {'credit_delta': -20, 'deposit_delta': '30.00', 'reason': '登记押金并扣减损坏信用'})
        self.assertEqual(result.status_code, 200, result.data)
        self.reader.refresh_from_db()
        self.assertEqual(self.reader.credit, 80)
        self.assertEqual(self.reader.deposit, 30)
        self.assertTrue(m.CreditEntry.objects.filter(reader=self.reader).exists())
        result = self.post(f'readers/{self.reader.pk}/manage/', {'deposit_delta': '-100', 'reason': '退款'}, 'refund')
        self.assertEqual(result.status_code, 400)
        self.reader.refresh_from_db()
        self.assertEqual(self.reader.deposit, 30)
        self.client.force_authenticate(self.operator)
        self.assertEqual(self.post(f'readers/{self.reader.pk}/manage/', {'role': 'admin', 'reason': '越权'}).status_code, 403)

    def test_rule_configuration_validation(self):
        rule = rules()
        result = self.client.patch(f'/api/v1/rules/{rule.pk}/', {'loan_days': 0, 'fine_per_day': '-1'}, format='json')
        self.assertEqual(result.status_code, 400)
        result = self.client.patch(f'/api/v1/rules/{rule.pk}/', {'holidays': ['invalid']}, format='json')
        self.assertEqual(result.status_code, 400)
        result = self.client.patch(f'/api/v1/rules/{rule.pk}/', {'loan_days': 14, 'holidays': ['2026-10-01']}, format='json')
        self.assertEqual(result.status_code, 200)

    def test_fire_unlock_and_offline_alert_are_idempotent(self):
        import uuid
        gate = m.Device.objects.create(branch=self.branch, kind='gate', name='门禁')
        smoke = m.Device.objects.create(branch=self.branch, kind='smoke', name='烟感')
        event_id = uuid.uuid4()
        operations.ingest(None, smoke.pk, event_id, 'smoke', {})
        operations.ingest(None, smoke.pk, event_id, 'smoke', {})
        self.assertEqual(m.DeviceCommand.objects.filter(device=gate, command='unlock').count(), 1)
        m.Device.objects.filter(pk=smoke.pk).update(last_seen=timezone.now()-timedelta(hours=1))
        maintenance()
        maintenance()
        self.assertEqual(m.Alert.objects.filter(device=smoke, kind='offline').count(), 1)

    def test_catalogue_import_upsert_without_creating_stock(self):
        data = {'records': [{'isbn': '9781111111111', 'title': '集成书目', 'author': '作者', 'category_code': 'I', 'category_name': '文学', 'call_number': 'I/1', 'price': '18.00'}]}
        result = self.post('integrations/catalogue-import/', data)
        self.assertEqual(result.status_code, 200, result.data)
        data['records'][0]['title'] = '更新书目'
        self.assertEqual(self.post('integrations/catalogue-import/', data, 'update').status_code, 200)
        self.assertEqual(m.Book.objects.count(), 1)
        self.assertEqual(m.Book.objects.get().title, '更新书目')
        self.assertEqual(m.Copy.objects.count(), 0)

    def test_video_retention_required_and_operation_audited(self):
        data = {'branch': self.branch.pk, 'kind': 'video', 'title': '监控索引', 'occurred_on': '2026-09-20'}
        self.assertEqual(self.post('operations/', data).status_code, 400)
        data['expires_at'] = (timezone.now()+timedelta(days=30)).isoformat()
        result = self.post('operations/', data)
        self.assertEqual(result.status_code, 201, result.data)
        self.client.get(f'/api/v1/operations/{result.data["id"]}/')
        self.assertTrue(m.AuditLog.objects.filter(action='operation.read').exists())

    def test_privacy_removes_old_completed_loans_keeps_unpaid(self):
        category = m.Category.objects.create(code='A', name='分类')
        book = m.Book.objects.create(isbn='test', title='书', author='作者', category=category, call_number='A', price=1)
        copy = m.Copy.objects.create(book=book, branch=self.branch)
        date = timezone.now()-timedelta(days=200)
        clean = m.Loan.objects.create(reader=self.reader, copy=copy, borrowed_at=date-timedelta(days=5), due_at=date, returned_at=date)
        unpaid = m.Loan.objects.create(reader=self.reader, copy=copy, borrowed_at=date-timedelta(days=5), due_at=date, returned_at=date)
        m.Fine.objects.create(loan=unpaid, amount=1)
        purge_expired()
        self.assertFalse(m.Loan.objects.filter(pk=clean.pk).exists())
        self.assertTrue(m.Loan.objects.filter(pk=unpaid.pk).exists())

    def test_offline_missing_record_is_conflict_not_batch_failure(self):
        import uuid
        data = {'transactions': [{'event_id': str(uuid.uuid4()), 'kind': 'return', 'loan': 9999,
            'branch': self.branch.pk, 'occurred_at': timezone.now().isoformat()}]}
        result = self.post('offline/sync/', data)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['results'][0]['status'], 'conflict')

    def test_schema_jwt_and_idempotency_contract(self):
        from drf_spectacular.generators import SchemaGenerator
        schema = SchemaGenerator().get_schema(public=True)
        self.assertIn('jwtAuth', schema['components']['securitySchemes'])
        borrow = schema['paths']['/api/v1/loans/borrow/']['post']
        self.assertTrue(any(p['name'] == 'Idempotency-Key' and p['required'] for p in borrow['parameters']))

    def test_deposit_history_isolated_and_idempotent(self):
        body = {'deposit_delta': '50.00', 'reason': '线下押金'}
        path = f'readers/{self.reader.pk}/manage/'
        self.assertEqual(self.post(path, body).status_code, 200)
        self.assertEqual(self.post(path, body).status_code, 200)
        self.assertEqual(m.DepositEntry.objects.count(), 1)
        self.client.force_authenticate(self.reader)
        result = self.client.get('/api/v1/deposit-entries/')
        self.assertEqual(result.data['count'], 1)
        self.client.force_authenticate(self.operator)
        self.assertEqual(self.client.get('/api/v1/deposit-entries/').data['count'], 0)

    def test_fine_manual_review_preserves_paid_balance(self):
        category = m.Category.objects.create(code='TP', name='计算机')
        book = m.Book.objects.create(isbn='test', title='书', author='作者', category=category, call_number='TP', price=1)
        copy = m.Copy.objects.create(book=book, branch=self.branch)
        loan = m.Loan.objects.create(reader=self.reader, copy=copy, borrowed_at=timezone.now(), due_at=timezone.now())
        fine = m.Fine.objects.create(loan=loan, amount=5, paid_amount=2, assessed_days=10)
        response = self.post(f'fines/{fine.pk}/adjust/', {'amount': '1.00', 'reason': '复核'})
        self.assertEqual(response.status_code, 400)
        response = self.post(f'fines/{fine.pk}/adjust/', {'amount': '2.00', 'assessed_days': 4, 'reason': '复核'}, 'review')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(m.AuditLog.objects.filter(action='fine.adjust').exists())

    def test_inventory_events_and_invalid_event_rollback(self):
        import uuid
        device = m.Device.objects.create(branch=self.branch, kind='rfid', name='RFID')
        data = {'event_id': str(uuid.uuid4()), 'kind': 'inventory', 'payload': {'observed': [], 'shelf': 'A1'}}
        result = self.post(f'devices/{device.pk}/events/', data)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(m.Inventory.objects.count(), 1)
        data = {'event_id': str(uuid.uuid4()), 'kind': 'inventory', 'payload': {'observed': ['invalid']}}
        self.assertEqual(self.post(f'devices/{device.pk}/events/', data).status_code, 400)
        self.assertEqual(m.DeviceEvent.objects.count(), 1)

    def test_encrypted_fields_exact_lookup_and_bcrypt(self):
        from django.db import connection
        self.reader.first_name = '示例读者'
        self.reader.contact = '联系地址'
        self.reader.set_password('New-Library-Password-2026')
        self.reader.save()
        with connection.cursor() as cursor:
            cursor.execute('SELECT phone, first_name, contact FROM library_user WHERE id = %s', [self.reader.pk])
            encrypted = cursor.fetchone()
        self.assertTrue(all(value.startswith('siv1:') for value in encrypted))
        self.assertNotIn(self.reader.phone, encrypted)
        found = m.User.objects.get(phone=self.reader.phone)
        self.assertEqual(found.first_name, '示例读者')
        self.assertTrue(found.password.startswith('bcrypt_sha256$'))
        self.assertTrue(found.check_password('New-Library-Password-2026'))

    def test_uniform_http_envelope_and_permissions(self):
        result = self.client.get('/api/v1/books/')
        body = result.json()
        self.assertEqual(set(body), {'code', 'message', 'data', 'request_id'})
        self.assertEqual(body['code'], 0)
        self.assertEqual(body['request_id'], result['X-Request-ID'])
        normal_admin = m.User.objects.create_user(username='normal-admin', phone='13955555555', role='admin')
        device = m.Device.objects.create(branch=self.branch, kind='gate', name='门禁')
        self.client.force_authenticate(normal_admin)
        response = self.post(f'devices/{device.pk}/command/', {'command': 'unlock', 'reason': '测试'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 40300)
        self.client.force_authenticate(self.operator)
        self.assertEqual(self.client.get('/api/v1/reports/summary/').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/reports/export/').status_code, 403)

    def test_outbox_publish_acknowledgement_and_retry(self):
        from library.tasks import publish_events
        event = m.DomainEvent.objects.create(kind='loan.borrowed', payload={'branch': self.branch.pk, 'loan': 1})
        with patch('library.adapters.mqtt_client') as factory, patch('library.adapters.connect'):
            client = factory.return_value
            client.publish.return_value.is_published.return_value = False
            with self.assertRaises(RuntimeError):
                publish_events()
            event.refresh_from_db()
            self.assertIsNone(event.published_at)
            client.publish.return_value.is_published.return_value = True
            self.assertEqual(publish_events(), 1)
        event.refresh_from_db()
        self.assertIsNotNone(event.published_at)

    def test_command_signature_outbox_and_idempotency(self):
        import hashlib
        import hmac
        from django.conf import settings
        gate = m.Device.objects.create(branch=self.branch, name='门禁', kind='gate')
        data = {'command': 'unlock', 'reason': '应急演练'}
        self.assertEqual(self.post(f'devices/{gate.pk}/command/', data).status_code, 200)
        self.assertEqual(self.post(f'devices/{gate.pk}/command/', data).status_code, 200)
        self.assertEqual(m.DeviceCommand.objects.count(), 1)
        item = m.DeviceCommand.objects.get()
        content = f'{item.pk}|{gate.pk}|unlock|{int(item.created_at.timestamp())}|应急演练'
        expected = hmac.new(settings.DEVICE_SIGNING_KEY.encode(), content.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(item.signature, expected)
        self.assertEqual(m.DomainEvent.objects.filter(kind='device.command').count(), 1)

    def test_readiness_checks_database_and_cache(self):
        self.client.force_authenticate(None)
        response = self.client.get('/health/ready/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['checks'], {'database': True, 'cache': True})
