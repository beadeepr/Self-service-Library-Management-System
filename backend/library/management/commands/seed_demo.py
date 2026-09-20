from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from library.models import User, Branch, Category, Book, Copy, Rule, Device


class Command(BaseCommand):
    help = '创建演示数据，必须显式指定演示账号密码'

    def add_arguments(self, parser):
        parser.add_argument('--password', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.SIMULATION_ENABLED:
            raise CommandError('仅模拟环境可初始化演示数据')
        from library.services.authentication import validate_secret
        validate_secret(options['password'])
        for phone, role in [('13800000001', 'admin'), ('13800000002', 'reader'), ('13800000003', 'operator')]:
            user, created = User.objects.get_or_create(phone=phone, defaults={'username': 'demo_'+role, 'role': role,
                'is_staff': role == 'admin', 'is_superuser': role == 'admin'})
            if created:
                user.set_password(options['password'])
                user.save()
            elif user.username == phone and user.role == role and not User.objects.filter(username='demo_'+role).exists():
                user.username = 'demo_'+role
                user.save(update_fields=['username'])
        branch, _ = Branch.objects.get_or_create(name='中心城市书房', defaults={'address': '示例路 1 号'})
        Branch.objects.get_or_create(name='社区分馆', defaults={'address': '示例路 2 号'})
        category, _ = Category.objects.get_or_create(code='TP', defaults={'name': '计算机技术'})
        book, _ = Book.objects.get_or_create(isbn='9787111000001', defaults={'title': '软件工程导论（演示）',
            'author': '示例作者', 'category': category, 'call_number': 'TP/001', 'price': '59.00'})
        if not book.copies.exists():
            Copy.objects.bulk_create([Copy(book=book, branch=branch, shelf='A-01') for _ in range(3)])
        Rule.objects.get_or_create(name='default')
        Device.objects.get_or_create(name='模拟门禁', branch=branch, defaults={'kind': 'gate'})
        self.stdout.write(self.style.SUCCESS('演示数据已创建；重复执行不会重置已有账号密码。'))
