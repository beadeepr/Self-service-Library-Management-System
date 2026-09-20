from django.core.management.base import BaseCommand
from library.tasks import maintenance, purge_expired, process_mqtt_inbox


class Command(BaseCommand):
    help = '执行预约过期、逾期计费、提醒、离线告警及保留期限清理'

    def handle(self, *args, **options):
        self.stdout.write(str({'mqtt_inbox_processed': process_mqtt_inbox()}))
        self.stdout.write(str(maintenance()))
        self.stdout.write(str(purge_expired()))
