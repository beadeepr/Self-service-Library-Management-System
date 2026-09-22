"""王恒：分工约定接口的联调与权限回归测试。"""
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from library import models as m
from library.services.common import rules


class CirculationContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reader = m.User.objects.create_user(username='contract', phone='13911111111')
        cls.other = m.User.objects.create_user(username='other-contract', phone='13922222222')
        cls.branch = m.Branch.objects.create(name='中心馆', address='A')
        cls.category = m.Category.objects.create(code='TP', name='计算机')
        cls.book = m.Book.objects.create(isbn='9780000000001', title='数据库事务', author='作者', category=cls.category, call_number='TP1', price=10)
        cls.copy = m.Copy.objects.create(book=cls.book, branch=cls.branch, shelf='A1')
        cls.rule = rules()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.reader)

    def post(self, action, data, key):
        return self.client.post('/api/circulation/' + action + '/', data, format='json', HTTP_IDEMPOTENCY_KEY=key)

    def borrow(self):
        response = self.post('borrow', {'copy': self.copy.pk}, 'borrow')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['id']

    def test_borrow_renew_return_and_cross_route_retries(self):
        loan = self.borrow()
        repeat = self.client.post('/api/v1/loans/borrow/', {'copy': self.copy.pk}, format='json', HTTP_IDEMPOTENCY_KEY='borrow')
        self.assertEqual(repeat.data['id'], loan)
        renewed = self.post('renew', {'loan': loan}, 'renew')
        self.assertEqual(renewed.status_code, 200, renewed.data)
        again = self.client.post(f'/api/v1/loans/{loan}/renew/', {}, format='json', HTTP_IDEMPOTENCY_KEY='renew')
        self.assertEqual(again.data, renewed.data)
        returned = self.post('return', {'loan': loan, 'branch': self.branch.pk}, 'return')
        self.assertEqual(returned.status_code, 200, returned.data)
        again = self.client.post(f'/api/v1/loans/{loan}/return/', {'branch': self.branch.pk}, format='json', HTTP_IDEMPOTENCY_KEY='return')
        self.assertEqual(again.data, returned.data)
        self.assertEqual(m.Loan.objects.count(), 1)
        listing = self.client.get('/api/circulation/loans/')
        self.assertEqual(listing.json()['code'], 0)
        self.assertEqual(listing.data['count'], 1)

    def test_reader_cannot_operate_on_others_loans(self):
        loan = self.borrow()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.post('renew', {'loan': loan}, 'renew-other').status_code, 404)
        self.assertEqual(self.post('return', {'loan': loan, 'branch': self.branch.pk}, 'return-other').status_code, 404)
        self.assertEqual(self.client.get('/api/circulation/loans/').data['count'], 0)
        self.assertEqual(self.client.post('/api/offline/sync/', {'transactions': []}, format='json').status_code, 403)

    def test_invalid_input_and_missing_idempotency_key(self):
        self.assertEqual(self.post('return', {'branch': self.branch.pk}, 'missing-loan').status_code, 400)
        self.assertEqual(self.post('renew', {'loan': 0}, 'invalid-loan').status_code, 400)
        response = self.client.post('/api/circulation/borrow/', {'copy': self.copy.pk}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(m.Loan.objects.exists())

    def test_rules_readable_but_not_writable_by_reader(self):
        current = self.client.get('/api/rules/current/')
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.data['loan_days'], self.rule.loan_days)
        self.assertEqual(self.client.patch(f'/api/v1/rules/{self.rule.pk}/', {'loan_limit': 99}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/rules/current/', {}, format='json').status_code, 405)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/rules/current/').status_code, 401)

    def test_search_combines_keyword_and_filters(self):
        self.client.force_authenticate(None)
        found = self.client.get('/api/books/search/', {'q': '事务', 'category': self.category.pk})
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.data['count'], 1)
        self.assertEqual(self.client.get('/api/books/search/', {'q': '不存在'}).data['count'], 0)
        self.assertEqual(self.client.get('/api/books/search/', {'q': '事务', 'isbn': 'other'}).data['count'], 0)

    def test_verified_reader_uses_verified_borrowing_rules(self):
        self.reader.verified = True
        self.reader.save(update_fields=['verified'])
        self.rule.verified_loan_days = 45
        self.rule.save()
        loan = m.Loan.objects.get(pk=self.borrow())
        self.assertEqual(loan.due_at - loan.borrowed_at, timedelta(days=45))

    def test_offline_sync_deduplicates_event(self):
        import uuid
        admin = m.User.objects.create_user(username='sync-admin', phone='13933333333', role='admin')
        self.client.force_authenticate(admin)
        body = {'transactions': [{'event_id': str(uuid.uuid4()), 'kind': 'borrow',
            'reader': self.reader.pk, 'copy': self.copy.pk, 'occurred_at': timezone.now().isoformat()}]}
        first = self.client.post('/api/offline/sync/', body, format='json')
        second = self.client.post('/api/v1/offline/sync/', body, format='json')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data['results'][0]['status'], 'applied')
        self.assertEqual(first.data, second.data)
        self.assertEqual(m.Loan.objects.count(), 1)
