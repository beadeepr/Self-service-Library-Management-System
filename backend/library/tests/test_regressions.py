import importlib
import json
import uuid
from datetime import datetime, timedelta, timezone as utc
from types import SimpleNamespace
from unittest.mock import patch
from django.apps import apps
from django.contrib.auth.hashers import make_password
from django.db import OperationalError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from library import models as m
from library.api.operations import WorkOrderViewSet
from library.api.serializers import UserSerializer, WorkOrderSerializer
from library.services import circulation
from library.services.common import idempotent, rules
from library.services.mqtt import record_message, process_message
from library.tasks import process_mqtt_inbox


class RegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = m.User.objects.create_user(username='reader-regression', phone='13980000001')
        cls.admin = m.User.objects.create_user(username='admin-regression', phone='13980000002', role='admin')
        cls.admin2 = m.User.objects.create_user(username='admin2-regression', phone='13980000003', role='admin')
        cls.branch = m.Branch.objects.create(name='Regression branch', address='test')
        category = m.Category.objects.create(code='REG', name='Regression')
        cls.book = m.Book.objects.create(isbn='regression', title='Regression', author='Test', category=category, call_number='REG/1', price=10)
        cls.copy = m.Copy.objects.create(book=cls.book, branch=cls.branch)
        cls.device = m.Device.objects.create(name='Smoke sensor', branch=cls.branch, kind='smoke')
        rule = rules()
        rule.disinfection_required = False
        rule.save()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_profile_patch_preserves_concurrent_credit_deposit_role_and_password(self):
        stale = m.User.objects.get(pk=self.reader.pk)
        password = make_password('Changed-Library-2026!')
        m.User.objects.filter(pk=stale.pk).update(credit=20, deposit=80, password=password, role='operator')
        self.client.force_authenticate(stale)
        response = self.client.patch('/api/v1/readers/me/', {'contact': 'New contact'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        actual = m.User.objects.get(pk=stale.pk)
        self.assertEqual((actual.credit, actual.deposit, actual.role, actual.password), (20, 80, 'operator', password))
        self.assertEqual(actual.contact, 'New contact')

    def test_profile_request_authenticated_before_freeze_cannot_unfreeze(self):
        stale = m.User.objects.get(pk=self.reader.pk)
        self.client.force_authenticate(stale)
        m.User.objects.filter(pk=stale.pk).update(frozen=True)
        response = self.client.patch('/api/v1/readers/me/', {'contact': 'New contact'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(m.User.objects.get(pk=stale.pk).frozen)

    def test_profile_serializer_only_updates_supplied_profile_fields(self):
        stale = m.User.objects.get(pk=self.reader.pk)
        serializer = UserSerializer(stale, data={'contact': 'New contact'}, partial=True)
        serializer.is_valid(raise_exception=True)
        m.User.objects.filter(pk=stale.pk).update(frozen=True, credit=30, deposit=90)
        serializer.save()
        actual = m.User.objects.get(pk=stale.pk)
        self.assertEqual((actual.frozen, actual.credit, actual.deposit), (True, 30, 90))

    def work_serializer(self):
        work = m.WorkOrder.objects.create(branch=self.branch, title='Original', kind='technical',
            status='in_progress', due_at=timezone.now()+timedelta(days=1))
        serializer = WorkOrderSerializer(work, data={'title': 'Edited'}, partial=True)
        serializer.is_valid(raise_exception=True)
        view = WorkOrderViewSet()
        view.request = SimpleNamespace(user=self.admin)
        return work, serializer, view

    def test_edit_cannot_revert_concurrently_completed_workorder(self):
        work, serializer, view = self.work_serializer()
        completed_at = timezone.now()
        m.WorkOrder.objects.filter(pk=work.pk).update(status='completed', result='Finished', completed_at=completed_at)
        with self.assertRaises(ValidationError):
            view.perform_update(serializer)
        work.refresh_from_db()
        self.assertEqual((work.status, work.result, work.completed_at, work.title), ('completed', 'Finished', completed_at, 'Original'))

    def test_edit_revalidates_relations_and_preserves_latest_assignment(self):
        work, serializer, view = self.work_serializer()
        m.WorkOrder.objects.filter(pk=work.pk).update(assignee=self.admin2)
        view.perform_update(serializer)
        work.refresh_from_db()
        self.assertEqual((work.title, work.assignee_id), ('Edited', self.admin2.pk))

    def offline_event(self):
        return {'event_id': str(uuid.uuid4()), 'kind': 'borrow', 'reader': self.reader.pk,
            'copy': self.copy.pk, 'occurred_at': (timezone.now()-timedelta(hours=1)).isoformat()}

    def upload(self, actor, item):
        self.client.force_authenticate(actor)
        response = self.client.post('/api/v1/offline/sync/', {'transactions': [item]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['results'][0]

    def test_same_event_across_uploaders_does_not_reborrow_returned_copy(self):
        item = self.offline_event()
        first = self.upload(self.admin, item)
        self.assertEqual(first['status'], 'applied')
        circulation.return_book(self.admin, first['result']['id'], self.branch.pk)
        second = self.upload(self.admin2, item)
        self.assertEqual(second, first)
        self.assertEqual(m.Loan.objects.count(), 1)
        self.copy.refresh_from_db()
        self.assertEqual(self.copy.status, 'available')
        self.assertEqual(m.OfflineReceipt.objects.count(), 1)

    def test_same_event_with_different_content_is_rejected_across_uploaders(self):
        item = self.offline_event()
        self.upload(self.admin, item)
        item['reader'] = self.admin2.pk
        self.assertEqual(self.upload(self.admin2, item)['status'], 'conflict')
        self.assertEqual(m.Loan.objects.count(), 1)

    def test_failed_offline_transaction_does_not_reserve_event_id(self):
        item = self.offline_event()
        item['copy'] = 99999
        self.assertEqual(self.upload(self.admin, item)['status'], 'conflict')
        self.assertFalse(m.OfflineReceipt.objects.exists())

    def test_legacy_offline_results_backfilled_for_cross_account_retry(self):
        from library.api.serializers import OfflineItemSerializer
        serializer = OfflineItemSerializer(data=self.offline_event())
        serializer.is_valid(raise_exception=True)
        item = serializer.validated_data
        expected = idempotent(self.admin, f'offline:{item["event_id"]}', 'offline.sync', item,
            lambda: circulation.borrow(self.admin, self.reader.pk, self.copy.pk, occurred_at=item['occurred_at']))
        migration = importlib.import_module('library.migrations.0009_backfill_offline_receipts')
        migration.backfill(apps, SimpleNamespace(connection=SimpleNamespace(alias='default')))
        response = self.upload(self.admin2, json.loads(json.dumps(item, default=str)))
        self.assertEqual(response['result'], expected)
        self.assertEqual(m.Loan.objects.count(), 1)

    def test_conflicting_legacy_results_stop_backfill_instead_of_overwriting(self):
        event_id = uuid.uuid4()
        for actor, result in [(self.admin, {'id': 1}), (self.admin2, {'id': 2})]:
            m.Idempotency.objects.create(actor=actor, key=f'offline:{event_id}', operation='offline.sync', digest='same', response=result)
        migration = importlib.import_module('library.migrations.0009_backfill_offline_receipts')
        with self.assertRaises(RuntimeError), transaction.atomic():
            migration.backfill(apps, SimpleNamespace(connection=SimpleNamespace(alias='default')))
        self.assertFalse(m.OfflineReceipt.objects.exists())

    def test_holidays_use_business_timezone_and_skip_consecutive_days(self):
        rule = rules()
        rule.holidays = ['2026-10-01', '2026-10-02']
        due = datetime(2026, 9, 30, 18, tzinfo=utc.utc)
        with timezone.override('Asia/Shanghai'):
            shifted = circulation.shift_holidays(due, rule)
            self.assertEqual(timezone.localtime(shifted).isoformat(), '2026-10-03T02:00:00+08:00')
            self.assertEqual(circulation.shift_holidays(datetime(2026, 9, 30, 12, tzinfo=utc.utc), rule).date().isoformat(), '2026-09-30')

    def mqtt_message(self, payload=None):
        envelope = {'event_id': str(uuid.uuid4()), 'kind': 'smoke', 'payload': {}}
        return SimpleNamespace(topic=f'library/{self.branch.pk}/device/{self.device.pk}/event',
            payload=json.dumps(envelope).encode() if payload is None else payload, mid=42, qos=1)

    def bridge(self):
        from library.management.commands.mqtt_bridge import Command
        with patch('library.management.commands.mqtt_bridge.mqtt_client') as factory, patch('library.management.commands.mqtt_bridge.connect'):
            client = factory.return_value
            client.loop_forever.side_effect = KeyboardInterrupt
            Command().handle()
            factory.assert_called_once_with('library-backend-bridge', persistent=True, manual_ack=True)
        return client

    def test_mqtt_ack_occurs_only_after_inbox_persistence(self):
        client = self.bridge()
        message = self.mqtt_message()
        client.ack.side_effect = lambda *args: self.assertTrue(m.MqttInbox.objects.filter(status='pending').exists())
        client.on_message(client, None, message)
        client.ack.assert_called_once_with(42, 1)
        self.assertEqual(m.MqttInbox.objects.get().status, 'processed')
        self.assertEqual(m.Alert.objects.count(), 1)

    def test_mqtt_failed_persistence_does_not_ack(self):
        client = self.bridge()
        with patch('library.management.commands.mqtt_bridge.record_message', side_effect=OperationalError('DB down')):
            with self.assertRaises(OperationalError):
                client.on_message(client, None, self.mqtt_message())
        client.ack.assert_not_called()
        self.assertFalse(m.MqttInbox.objects.exists())

    def test_mqtt_processing_failure_is_retried_without_duplicate_alerts(self):
        client = self.bridge()
        message = self.mqtt_message()
        with patch('library.services.mqtt.ingest', side_effect=OperationalError('DB down')), self.assertLogs('library.management.commands.mqtt_bridge', level='ERROR'):
            client.on_message(client, None, message)
        self.assertEqual(m.MqttInbox.objects.get().status, 'pending')
        self.assertEqual(m.Alert.objects.count(), 0)
        self.assertEqual(process_mqtt_inbox(), 1)
        client.on_message(client, None, message)
        self.assertEqual(m.Alert.objects.count(), 1)
        self.assertEqual(m.MqttInbox.objects.count(), 1)
        self.assertEqual(m.MqttInbox.objects.get().status, 'processed')

    def test_mqtt_invalid_messages_are_persisted_as_rejected(self):
        client = self.bridge()
        client.on_message(client, None, self.mqtt_message(b'not-json'))
        self.assertEqual(m.MqttInbox.objects.get().status, 'rejected')
        self.assertTrue(m.MqttInbox.objects.get().error)
        client.ack.assert_called_once_with(42, 1)
        self.assertEqual(process_mqtt_inbox(), 0)

    def test_mqtt_reconnects_after_persistence_failure(self):
        from library.management.commands.mqtt_bridge import Command
        with patch('library.management.commands.mqtt_bridge.mqtt_client') as factory, \
             patch('library.management.commands.mqtt_bridge.connect') as connect, \
             patch('library.management.commands.mqtt_bridge.time.sleep') as sleep, \
             self.assertLogs('library.management.commands.mqtt_bridge', level='ERROR'):
            client = factory.return_value
            client.loop_forever.side_effect = [OperationalError('DB down'), KeyboardInterrupt]
            Command().handle()
            self.assertEqual(connect.call_count, 2)
            sleep.assert_called_once_with(5)

    def test_mqtt_factory_configures_persistent_session_and_manual_ack(self):
        from library.adapters import mqtt_client
        with patch('library.adapters.Client') as constructor:
            mqtt_client('test-bridge', persistent=True, manual_ack=True)
        self.assertFalse(constructor.call_args.kwargs['clean_session'])
        self.assertTrue(constructor.call_args.kwargs['manual_ack'])
