"""王恒：认证联调入口与兼容性检查。"""
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from library.models import User
from library.services import authentication, auth_service, circulation, circulation_service


class AuthContractTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.password = 'Library-Contract-2026'
        self.reader = User.objects.create_user(username='auth-contract', phone='13911111111', password=self.password)

    def test_login_refresh_and_authenticated_listing(self):
        login = self.client.post('/api/auth/login/', {'phone': self.reader.phone, 'password': self.password}, format='json')
        self.assertEqual(login.status_code, 200, login.data)
        self.assertEqual(login.json()['code'], 0)
        refreshed = self.client.post('/api/auth/refresh/', {'refresh': login.data['refresh']}, format='json')
        self.assertEqual(refreshed.status_code, 200, refreshed.data)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + refreshed.data['access'])
        self.assertEqual(self.client.get('/api/circulation/loans/').status_code, 200)

    @override_settings(SIMULATION_ENABLED=True)
    def test_registration_requires_sms_and_creates_reader(self):
        phone = '13922222222'
        code = auth_service.issue_code(phone, 'register')['simulation_code']
        response = self.client.post('/api/auth/register/', {'phone': phone, 'code': code,
            'password': self.password, 'first_name': '读者'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(User.objects.get(phone=phone).role, 'reader')
        repeat = self.client.post('/api/auth/register/', {'phone': phone, 'code': code,
            'password': self.password, 'first_name': '读者'}, format='json')
        self.assertEqual(repeat.status_code, 400)

    def test_legacy_services_reference_canonical_implementation(self):
        self.assertIs(authentication.password_login, auth_service.password_login)
        self.assertIs(circulation.borrow, circulation_service.borrow)
