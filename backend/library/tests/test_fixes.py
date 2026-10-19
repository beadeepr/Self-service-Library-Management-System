"""针对本次缺陷修复的回归测试。"""
import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from library import models as m
from library.services import circulation_service, operations
from library.services.common import rules


class FixRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = m.User.objects.create_user(username='fix-admin', phone='13970000001', role='admin')
        cls.superuser = m.User.objects.create_user(
            username='fix-super', phone='13970000002', role='reader', is_superuser=True,
            password='Superuser-Pass-2026!')
        cls.reader = m.User.objects.create_user(username='fix-reader', phone='13970000003')
        cls.reader2 = m.User.objects.create_user(username='fix-reader2', phone='13970000004')
        cls.reader3 = m.User.objects.create_user(username='fix-reader3', phone='13970000005')
        cls.branch = m.Branch.objects.create(name='修复中心馆', address='A')
        cls.branch2 = m.Branch.objects.create(name='修复分馆', address='B')
        category = m.Category.objects.create(code='FIX', name='修复测试')
        cls.book = m.Book.objects.create(isbn='fix-0001', title='修复测试书', author='Test',
            category=category, call_number='FIX/1', price=10)
        cls.copy = m.Copy.objects.create(book=cls.book, branch=cls.branch, shelf='A1')
        cls.copy2 = m.Copy.objects.create(book=cls.book, branch=cls.branch, shelf='A2')
        cls.copy_other = m.Copy.objects.create(book=cls.book, branch=cls.branch2, shelf='B1')
        rule = rules()
        rule.disinfection_required = False
        rule.renewal_limit = 2
        rule.save()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def post(self, url, data, key='fix-key'):
        return self.client.post(url, data, format='json', HTTP_IDEMPOTENCY_KEY=f'{key}-{uuid.uuid4()}')

    def test_renew_ignores_other_branch_and_ready_reservations(self):
        loan1 = circulation_service.borrow(self.reader, self.reader.pk, self.copy.pk)
        circulation_service.borrow(self.reader2, self.reader2.pk, self.copy_other.pk)
        # 分馆的等待预约不应阻止本馆续借
        circulation_service.reserve(self.reader3, self.book.pk, self.branch2.pk)
        circulation_service.renew(self.reader, loan1['id'])
        # 分馆预约已经拿到归还的副本（ready），也不应阻止本馆续借
        other_loan = m.Loan.objects.get(reader=self.reader2, returned_at=None)
        circulation_service.return_book(self.reader2, other_loan.pk, self.branch2.pk)
        self.assertEqual(m.Reservation.objects.get(reader=self.reader3).status, 'ready')
        result = circulation_service.renew(self.reader, loan1['id'])
        self.assertEqual(result['renewals'], 2)

    def test_intake_assigns_new_copy_to_waiting_reservation(self):
        circulation_service.borrow(self.reader, self.reader.pk, self.copy.pk)
        # 让该馆没有可借副本，才能进入预约队列
        m.Copy.objects.filter(pk=self.copy2.pk).update(status='withdrawn')
        circulation_service.reserve(self.reader3, self.book.pk, self.branch.pk)
        response = self.post(f'/api/v1/books/{self.book.pk}/intake/',
                             {'branch': self.branch.pk, 'quantity': 1, 'shelf': 'A3'})
        self.assertEqual(response.status_code, 201, response.data)
        new_copy = m.Copy.objects.exclude(pk__in=[self.copy.pk, self.copy2.pk, self.copy_other.pk]).get()
        self.assertEqual(new_copy.status, m.Copy.Status.RESERVED)
        reservation = m.Reservation.objects.get(reader=self.reader3)
        self.assertEqual((reservation.status, reservation.copy_id), ('ready', new_copy.pk))

    def test_cancelled_transfer_reassigns_copy_to_waiting_reservation(self):
        circulation_service.borrow(self.reader, self.reader.pk, self.copy.pk)
        # copy2 可借时不能预约；先计划调拨让它变为 withdrawn
        transfer = operations.plan_transfer(self.admin, self.copy2.pk, self.branch2.pk, 'A-B', timezone.now())
        circulation_service.reserve(self.reader3, self.book.pk, self.branch.pk)
        operations.transition_transfer(self.admin, transfer['id'], 'cancel')
        reservation = m.Reservation.objects.get(reader=self.reader3)
        self.assertEqual(reservation.status, 'ready')
        self.copy2.refresh_from_db()
        self.assertEqual(self.copy2.status, m.Copy.Status.RESERVED)

    def test_stale_visit_is_closed_and_reader_can_enter_again(self):
        stale = m.Visit.objects.create(reader=self.reader, active_reader=self.reader, branch=self.branch,
            entered_at=timezone.now() - timedelta(hours=13))
        self.client.force_authenticate(self.reader)
        response = self.post('/api/v1/visits/access/',
                             {'branch': self.branch.pk, 'direction': 'enter', 'method': 'qr'})
        self.assertEqual(response.status_code, 200, response.data)
        stale.refresh_from_db()
        self.assertIsNotNone(stale.exited_at)
        self.assertIsNone(stale.active_reader)
        self.assertEqual(response.data['occupancy'], 1)

    def test_access_queues_gate_unlock_command(self):
        gate = m.Device.objects.create(name='门禁', branch=self.branch, kind='gate')
        response = self.post('/api/v1/visits/access/',
                             {'branch': self.branch.pk, 'direction': 'enter', 'method': 'card'})
        self.assertEqual(response.status_code, 200, response.data)
        command = m.DeviceCommand.objects.get(device=gate)
        self.assertEqual(command.command, 'unlock')

    def test_long_alert_message_is_truncated_for_workorder(self):
        smoke = m.Device.objects.create(name='烟感', branch=self.branch, kind='smoke')
        operations.ingest(None, smoke.pk, uuid.uuid4(), 'smoke', {'message': '烟' * 500})
        work = m.WorkOrder.objects.get()
        self.assertEqual(len(work.title), 200)
        self.assertEqual(m.Alert.objects.get().message, '烟' * 500)

    def test_non_superuser_admin_cannot_manage_peer_admin(self):
        peer = m.User.objects.create_user(username='fix-peer', phone='13970000006', role='admin')
        response = self.post(f'/api/v1/readers/{peer.pk}/manage/', {'frozen': True, 'reason': '越权'})
        self.assertEqual(response.status_code, 400, response.data)
        peer.refresh_from_db()
        self.assertFalse(peer.frozen)
        reader_response = self.post(f'/api/v1/readers/{self.reader.pk}/manage/',
                                    {'frozen': True, 'reason': '正常管理'})
        self.assertEqual(reader_response.status_code, 200, reader_response.data)

    def test_verified_identity_cannot_be_rebound(self):
        m.Consent.objects.create(reader=self.reader, purpose='identity', policy_version='1.0', granted=True)
        m.User.objects.filter(pk=self.reader.pk).update(verified=True, identity_digest='existing-digest')
        response = self.post('/api/v1/readers/verify-identity/', {'identity': '110101199001011234'})
        self.assertEqual(response.status_code, 400, response.data)
        self.reader.refresh_from_db()
        self.assertEqual(self.reader.identity_digest, 'existing-digest')

    def test_superuser_login_reports_effective_admin_role(self):
        self.client.force_authenticate(None)
        response = self.client.post('/api/v1/auth/login/',
            {'phone': self.superuser.phone, 'password': 'Superuser-Pass-2026!'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['role'], 'admin')
        self.assertTrue(response.data['is_superuser'])

    def test_reader_can_return_other_loan_but_cannot_mark_it_damaged(self):
        loan = circulation_service.borrow(self.reader, self.reader.pk, self.copy.pk)
        self.client.force_authenticate(self.reader2)
        response = self.post(f'/api/v1/loans/{loan["id"]}/return/',
                             {'branch': self.branch.pk, 'damaged': True})
        self.assertEqual(response.status_code, 200, response.data)
        self.reader.refresh_from_db()
        self.assertEqual(self.reader.credit, 100)
        self.assertIsNotNone(m.Loan.objects.get(pk=loan['id']).returned_at)
