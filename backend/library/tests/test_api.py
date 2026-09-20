import time
import uuid
from datetime import timedelta
from decimal import Decimal
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from library import models as m
from library.services import circulation, payments, authentication
from library.services.common import rules
from library.tasks import maintenance, purge_expired


class ApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = m.User.objects.create_user(username='reader', phone='13811111111', password='Library-Test-2026')
        cls.other = m.User.objects.create_user(username='other', phone='13822222222', password='Library-Test-2026')
        cls.admin = m.User.objects.create_user(username='admin', phone='13833333333', password='Library-Test-2026', role='admin', is_superuser=True)
        cls.operator = m.User.objects.create_user(username='ops', phone='13844444444', password='Library-Test-2026', role='operator')
        cls.branch = m.Branch.objects.create(name='中心馆', address='A')
        cls.branch2 = m.Branch.objects.create(name='分馆', address='B')
        cls.category = m.Category.objects.create(code='TP', name='计算机')
        cls.book = m.Book.objects.create(isbn='9780000000001', title='事务测试', author='作者', category=cls.category, call_number='TP1', price=10)
        cls.copy = m.Copy.objects.create(book=cls.book, branch=cls.branch, shelf='A1')
        cls.rule = rules()

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(self.reader)

    def post(self, path, data=None, key=None):
        return self.client.post('/api/v1/'+path, data or {}, format='json', HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))

    def borrow(self, copy=None, key=None):
        result = self.post('loans/borrow/', {'copy': (copy or self.copy).pk}, key)
        self.assertEqual(result.status_code, 201, result.data)
        return result

    def test_borrow_return_disinfect_shelve_flow(self):
        result = self.borrow()
        loan_id = result.data['id']
        returned = self.post(f'loans/{loan_id}/return/', {'branch': self.branch2.pk})
        self.assertEqual(returned.status_code, 200, returned.data)
        self.copy.refresh_from_db()
        self.assertEqual((self.copy.status, self.copy.branch_id), ('processing', self.branch2.pk))
        self.client.force_authenticate(self.operator)
        self.assertEqual(self.post(f'copies/{self.copy.pk}/shelve/', {'shelf': 'B2'}).status_code, 400)
        self.assertEqual(self.post(f'copies/{self.copy.pk}/disinfect/').status_code, 200)
        self.assertEqual(self.post(f'copies/{self.copy.pk}/shelve/', {'shelf': 'B2'}).data['status'], 'available')

    def test_idempotent_borrow_and_payload_mismatch(self):
        first = self.borrow(key='borrow-1')
        second = self.borrow(key='borrow-1')
        self.assertEqual(first.data, second.data)
        self.assertEqual(m.Loan.objects.count(), 1)
        response = self.post('loans/borrow/', {'copy': self.copy.pk, 'reader': self.reader.pk}, key='borrow-1')
        self.assertEqual(response.status_code, 400)

    def test_cannot_borrow_busy_copy_or_exceed_limit(self):
        self.borrow()
        self.client.force_authenticate(self.other)
        response = self.post('loans/borrow/', {'copy': self.copy.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 4001)
        self.client.force_authenticate(self.reader)
        self.rule.loan_limit = 1
        self.rule.save()
        another = m.Copy.objects.create(book=self.book, branch=self.branch)
        self.assertEqual(self.post('loans/borrow/', {'copy': another.pk}).status_code, 400)
        another.refresh_from_db()
        self.assertEqual(another.status, 'available')

    def test_reader_cannot_borrow_for_other_or_read_other_history(self):
        self.assertEqual(self.post('loans/borrow/', {'copy': self.copy.pk, 'reader': self.other.pk}).status_code, 403)
        loan_id = self.borrow().data['id']
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/v1/loans/{loan_id}/').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/loans/').data['count'], 0)

    def test_renew_limit_and_due_date(self):
        loan_id = self.borrow().data['id']
        loan = m.Loan.objects.get(pk=loan_id)
        due = loan.due_at
        self.assertEqual(self.post(f'loans/{loan_id}/renew/').status_code, 200)
        loan.refresh_from_db()
        self.assertEqual(loan.due_at, due+timedelta(days=30))
        self.assertEqual(self.post(f'loans/{loan_id}/renew/').status_code, 400)

    def test_overdue_fine_payment_and_credit_idempotency(self):
        loan_id = self.borrow().data['id']
        m.Loan.objects.filter(pk=loan_id).update(due_at=timezone.now()-timedelta(days=2, minutes=1))
        maintenance()
        fine = m.Fine.objects.get(loan_id=loan_id)
        self.assertEqual(fine.amount, Decimal('1.50'))
        maintenance()
        self.assertEqual(m.CreditEntry.objects.count(), 1)
        self.assertEqual(self.post(f'loans/{loan_id}/renew/').status_code, 400)
        payment = self.post('payments/', {'fine': fine.pk})
        self.assertEqual(payment.status_code, 201, payment.data)
        payment_id = payment.data['id']
        self.assertEqual(self.post(f'payments/{payment_id}/simulate/').status_code, 200)
        self.assertEqual(self.post(f'payments/{payment_id}/simulate/').status_code, 200)
        fine.refresh_from_db()
        self.assertEqual(fine.paid_amount, Decimal('1.50'))

    def test_reservation_queue_collect_and_renew_block(self):
        loan_id = self.borrow().data['id']
        self.client.force_authenticate(self.other)
        hold = self.post('reservations/', {'book': self.book.pk, 'branch': self.branch.pk})
        self.assertEqual(hold.status_code, 201, hold.data)
        self.assertEqual(self.post('reservations/', {'book': self.book.pk, 'branch': self.branch.pk}).status_code, 400)
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.post(f'loans/{loan_id}/renew/').status_code, 400)
        self.post(f'loans/{loan_id}/return/', {'branch': self.branch.pk})
        self.client.force_authenticate(self.operator)
        self.post(f'copies/{self.copy.pk}/disinfect/')
        self.post(f'copies/{self.copy.pk}/shelve/', {'shelf': 'A1'})
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.post('loans/borrow/', {'copy': self.copy.pk}).status_code, 400)
        self.client.force_authenticate(self.other)
        response = self.post(f'reservations/{hold.data["id"]}/collect/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(m.Loan.objects.filter(returned_at=None).count(), 1)

    def test_expired_hold_advances_queue(self):
        self.borrow()
        self.client.force_authenticate(self.other)
        first = self.post('reservations/', {'book': self.book.pk, 'branch': self.branch.pk}).data['id']
        third = m.User.objects.create_user(username='third', phone='13855555555')
        m.Reservation.objects.create(reader=third, book=self.book, branch=self.branch)
        self.rule.disinfection_required = False
        self.rule.save()
        circulation.return_book(self.admin, m.Loan.objects.get().pk, self.branch.pk)
        m.Reservation.objects.filter(pk=first).update(expires_at=timezone.now()-timedelta(seconds=1))
        maintenance()
        self.assertEqual(m.Reservation.objects.get(pk=first).status, 'expired')
        self.assertEqual(m.Reservation.objects.get(reader=third).status, 'ready')

    def test_public_catalogue_search_and_reader_write_forbidden(self):
        self.client.force_authenticate(None)
        result = self.client.get('/api/v1/books/?search=事务')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['results'][0]['available_count'], 1)
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.post('categories/', {'code': 'A', 'name': 'A'}).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/readers/').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/audit-logs/').status_code, 403)

    def test_intake_tags_and_stock_not_user_writable(self):
        self.client.force_authenticate(self.admin)
        result = self.post(f'books/{self.book.pk}/intake/', {'branch': self.branch.pk, 'quantity': 2}, key='intake')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(len(set(item['rfid'] for item in result.data['copies'])), 2)
        self.post(f'books/{self.book.pk}/intake/', {'branch': self.branch.pk, 'quantity': 2}, key='intake')
        self.assertEqual(m.Copy.objects.count(), 3)
        self.assertEqual(self.client.patch(f'/api/v1/copies/{self.copy.pk}/', {'status': 'loaned'}, format='json').status_code, 405)

    def test_login_lockout_survives_failed_requests(self):
        self.client.force_authenticate(None)
        for _ in range(5):
            self.assertEqual(self.post('auth/login/', {'phone': self.reader.phone, 'password': 'bad'}).status_code, 401)
        self.reader.refresh_from_db()
        self.assertEqual(self.reader.failed_logins, 5)
        self.assertIsNotNone(self.reader.locked_until)
        self.assertEqual(self.post('auth/login/', {'phone': self.reader.phone, 'password': 'Library-Test-2026'}).status_code, 401)
        m.User.objects.filter(pk=self.reader.pk).update(locked_until=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.post('auth/login/', {'phone': self.reader.phone, 'password': 'Library-Test-2026'}).status_code, 200)

    def test_sms_attempt_limit_and_registration(self):
        code = authentication.issue_code('13912345678', 'register')['simulation_code']
        self.client.force_authenticate(None)
        result = self.post('auth/register/', {'phone': '13912345678', 'code': code, 'password': 'Library-New-2026'})
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(m.User.objects.get(phone='13912345678').role, 'reader')
        self.assertEqual(self.post('auth/register/', {'phone': '13912345678', 'code': code, 'password': 'Library-New-2026'}).status_code, 400)
        code = authentication.issue_code(self.reader.phone, 'login')['simulation_code']
        for _ in range(5):
            bad = '000000' if code != '000000' else '111111'
            self.assertEqual(self.post('auth/sms-login/', {'phone': self.reader.phone, 'code': bad}).status_code, 400)
        self.assertEqual(self.post('auth/sms-login/', {'phone': self.reader.phone, 'code': code}).status_code, 400)

    def test_frozen_user_existing_token_rejected(self):
        token = authentication.tokens(self.reader)['access']
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+token)
        m.User.objects.filter(pk=self.reader.pk).update(frozen=True)
        self.assertEqual(self.client.get('/api/v1/readers/me/').status_code, 401)

    def test_profile_cannot_escalate_role(self):
        result = self.client.patch('/api/v1/readers/me/', {'role': 'admin', 'credit': 200, 'deposit': 999}, format='json')
        self.assertEqual(result.status_code, 200)
        self.reader.refresh_from_db()
        self.assertEqual((self.reader.role, self.reader.credit, self.reader.deposit), ('reader', 100, 0))

    def test_payment_callback_signature_amount_replay(self):
        loan_id = self.borrow().data['id']
        fine = m.Fine.objects.create(loan_id=loan_id, amount=2)
        payment = self.post('payments/', {'fine': fine.pk}).data
        stamp = int(time.time())
        payload = {'reference': payment['reference'], 'amount': '2.00', 'timestamp': stamp,
            'signature': payments.signature(payment['reference'], '2.00', stamp)}
        self.client.force_authenticate(None)
        bad = dict(payload, amount='0.01')
        self.assertEqual(self.post('payments/callback/', bad).status_code, 400)
        self.assertEqual(self.post('payments/callback/', payload).status_code, 200)
        self.assertEqual(self.post('payments/callback/', payload).status_code, 200)
        fine.refresh_from_db()
        self.assertEqual(fine.paid_amount, Decimal('2.00'))

    def test_face_consent_and_capacity_and_exit_when_frozen(self):
        payload = {'branch': self.branch.pk, 'direction': 'enter', 'method': 'face'}
        self.assertEqual(self.post('visits/access/', payload).status_code, 400)
        self.post('consents/', {'purpose': 'biometric', 'policy_version': '1.0', 'granted': True})
        self.assertEqual(self.post('visits/access/', payload).status_code, 200)
        self.assertEqual(self.post('visits/access/', payload).status_code, 400)
        self.client.force_authenticate(self.admin)
        m.User.objects.filter(pk=self.reader.pk).update(frozen=True)
        response = self.post('visits/access/', {'reader': self.reader.pk, 'branch': self.branch.pk, 'direction': 'exit'})
        self.assertEqual(response.status_code, 200, response.data)

    def test_transfer_workflow_and_inventory(self):
        self.client.force_authenticate(self.operator)
        data = {'copy': self.copy.pk, 'destination': self.branch2.pk, 'route': 'A-B', 'schedule': timezone.now().isoformat()}
        transfer = self.post('transfers/', data)
        self.assertEqual(transfer.status_code, 201, transfer.data)
        pk = transfer.data['id']
        self.assertEqual(self.post(f'transfers/{pk}/transition/', {'action': 'receive'}).status_code, 400)
        self.assertEqual(self.post(f'transfers/{pk}/transition/', {'action': 'ship'}).status_code, 200)
        self.assertEqual(self.post(f'transfers/{pk}/transition/', {'action': 'receive'}).status_code, 200)
        self.copy.refresh_from_db()
        self.assertEqual((self.copy.branch_id, self.copy.status), (self.branch2.pk, 'processing'))
        result = self.post('inventories/', {'branch': self.branch.pk, 'shelf': 'A1', 'observed': [str(self.copy.rfid)]})
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data['report']['misplaced'], [str(self.copy.rfid)])

    def test_device_event_dedupe_alert_and_workorder(self):
        device = m.Device.objects.create(name='烟感', branch=self.branch, kind='smoke')
        self.client.force_authenticate(self.operator)
        event = {'event_id': str(uuid.uuid4()), 'kind': 'smoke', 'payload': {'message': '火警'}}
        self.assertEqual(self.post(f'devices/{device.pk}/events/', event).status_code, 200)
        self.assertTrue(self.post(f'devices/{device.pk}/events/', event).data['duplicate'])
        self.assertEqual(m.Alert.objects.count(), 1)
        work = m.WorkOrder.objects.get()
        self.assertEqual(self.post(f'work-orders/{work.pk}/transition/', {'status': 'completed'}).status_code, 400)
        self.post(f'work-orders/{work.pk}/transition/', {'status': 'in_progress'})
        self.assertEqual(self.post(f'work-orders/{work.pk}/transition/', {'status': 'completed', 'result': '已检修'}).status_code, 200)
        self.assertEqual(self.post(f'work-orders/{work.pk}/transition/', {'status': 'reviewed', 'review': '通过'}).status_code, 400)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.post(f'work-orders/{work.pk}/transition/', {'status': 'reviewed', 'review': '通过'}).status_code, 200)

    def test_offline_batch_retry_and_conflict(self):
        self.client.force_authenticate(self.admin)
        item = {'event_id': str(uuid.uuid4()), 'kind': 'borrow', 'reader': self.reader.pk, 'copy': self.copy.pk,
            'occurred_at': (timezone.now()-timedelta(hours=1)).isoformat()}
        data = {'transactions': [item]}
        self.assertEqual(self.post('offline/sync/', data).data['results'][0]['status'], 'applied')
        self.assertEqual(self.post('offline/sync/', data).data['results'][0]['status'], 'applied')
        self.assertEqual(m.Loan.objects.count(), 1)
        item['event_id'] = str(uuid.uuid4())
        self.assertEqual(self.post('offline/sync/', data).data['results'][0]['status'], 'conflict')

    def test_retention_only_expires_eligible_data(self):
        expired = m.OperationRecord.objects.create(branch=self.branch, kind='video', title='索引', occurred_on=timezone.now().date(), expires_at=timezone.now()-timedelta(days=1))
        m.OperationRecord.objects.create(branch=self.branch, kind='emergency_plan', title='消防预案', occurred_on=timezone.now().date())
        purge_expired()
        self.assertFalse(m.OperationRecord.objects.filter(pk=expired.pk).exists())
        self.assertEqual(m.OperationRecord.objects.count(), 1)

    def test_schema_and_reports(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get('/api/schema/').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/reports/summary/').status_code, 200)
        result = self.client.get('/api/v1/reports/export/')
        self.assertEqual(result.status_code, 200)
        self.assertTrue(m.AuditLog.objects.filter(action='report.export').exists())

    def test_qr_login_one_time_poll(self):
        self.client.force_authenticate(None)
        challenge = self.post('auth/qr-challenge/').data
        self.assertEqual(self.post('auth/qr-poll/', challenge).data['status'], 'waiting')
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.post('auth/qr-confirm/', {'token': challenge['token']}).status_code, 200)
        self.client.force_authenticate(None)
        self.assertIn('access', self.post('auth/qr-poll/', challenge).data)
        self.assertEqual(self.post('auth/qr-poll/', challenge).status_code, 400)

    def test_identity_consent_unique_and_digest_only(self):
        data = {'identity': '110101199001010011'}
        self.assertEqual(self.post('readers/verify-identity/', data).status_code, 400)
        self.post('consents/', {'purpose': 'identity', 'policy_version': '1', 'granted': True})
        self.assertEqual(self.post('readers/verify-identity/', data).status_code, 200)
        self.reader.refresh_from_db()
        self.assertNotEqual(self.reader.identity_digest, data['identity'])
        self.client.force_authenticate(self.other)
        self.post('consents/', {'purpose': 'identity', 'policy_version': '1', 'granted': True})
        self.assertEqual(self.post('readers/verify-identity/', data).status_code, 400)

    def test_activity_capacity_and_category_cycle(self):
        activity = m.Activity.objects.create(branch=self.branch, title='阅读会', audience='亲子', starts_at=timezone.now()+timedelta(days=1), capacity=1)
        self.assertEqual(self.post(f'activities/{activity.pk}/enroll/').status_code, 200)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.post(f'activities/{activity.pk}/enroll/').status_code, 400)
        self.client.force_authenticate(self.admin)
        result = self.client.patch(f'/api/v1/categories/{self.category.pk}/', {'parent': self.category.pk}, format='json')
        self.assertEqual(result.status_code, 400)

    @override_settings(SIMULATION_ENABLED=False)
    def test_simulation_disabled(self):
        loan_id = self.borrow().data['id']
        fine = m.Fine.objects.create(loan_id=loan_id, amount=1)
        payment = self.post('payments/', {'fine': fine.pk}).data
        self.assertEqual(self.post(f'payments/{payment["id"]}/simulate/').status_code, 400)
