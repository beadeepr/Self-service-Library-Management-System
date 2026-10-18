"""
演示用的「业务故事」数据，供答辩现场演示用。

与 seed_demo 的分工：
- seed_demo 只造最小可运行数据（3 个账号、1 个网点分类、1 本书 3 册、1 台设备）；
- 本命令在此基础上补齐能被「讲成故事」的状态：第二本书与副本、逾期借阅与罚款、
  可预约状态、进馆记录与在馆人数、告警与工单、公告。

设计原则：
1. **复用真实业务服务**，不直接塞数据：借阅走 circulation.borrow、门禁走 operations.access、
   设备事件走 operations.ingest。这样借阅规则、信用扣减、到馆通知、告警联动、审计都会照常发生，
   演示数据与真实操作产生的一致。操作者统一取管理员，审计记录读起来也符合实际。
2. **只在服务做不到的地方直接改 ORM**：把借阅应还日回拨到过去（接口不允许指定借阅日期），
   以及创建公告（没有对应服务）。两处都有注释。
3. **可重复执行**：账号、书目、副本、公告用 get_or_create；设备事件用固定 UUID，
   ingest 会按 event_id 去重；借阅与进馆记录先探测既存状态再决定是否创建。

前置条件：先执行 seed_demo。仅模拟环境（SIMULATION_ENABLED=1）可用，与 seed_demo 一致。
"""
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from library.models import Alert, Announcement, Book, Branch, Category, Copy, Device, Loan, User, Visit
from library.services import circulation, operations

# 逾期取 10 天 1 小时：assess_fine 按「不足一天按一天」向上取整得到 11 天，
# 即 11 × 0.50 = ¥5.50。多出的 1 小时让结果确定，不依赖几毫秒的执行间隔。
OVERDUE_BACKDATE = timedelta(days=10, hours=1)


def showcase_event_id(name):
    """固定事件 ID：重复执行时 ingest 依据 event_id 判定重复，不重复产生告警与工单。"""
    return uuid.uuid5(uuid.NAMESPACE_URL, f'library-demo-showcase/{name}')


class Command(BaseCommand):
    help = '在 seed_demo 基础上补齐可演示的业务数据（逾期/罚款/预约/门禁/告警/公告）'

    def add_arguments(self, parser):
        parser.add_argument('--password', required=True, help='新增演示读者的登录口令')

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.SIMULATION_ENABLED:
            raise CommandError('仅模拟环境可初始化演示数据')

        password = options['password']
        from library.services.authentication import validate_secret
        validate_secret(password)

        # ---------- 前置条件：seed_demo 的基础数据 ----------
        branch_main = Branch.objects.filter(name='中心城市书房').first()
        branch_community = Branch.objects.filter(name='社区分馆').first()
        category = Category.objects.filter(code='TP').first()
        actor = User.objects.filter(phone='13800000001').first()
        main_reader = User.objects.filter(phone='13800000002').first()
        if not (branch_main and branch_community and category and actor and main_reader):
            raise CommandError('缺少基础演示数据，请先执行：manage.py seed_demo --password <口令>')

        created = []

        # ---------- 演示读者 ----------
        # 逾期与欠费必须挂在独立账号上：后端 eligible 会因「有逾期图书」和「有未缴清罚款」
        # 阻止借阅；若挂在主演示账号上，答辩时的自助借书演示会直接失败。
        overdue_reader = self._reader('13480588246', 'demo_overdue', '演示读者·逾期', password, created)
        holder_reader = self._reader('13380588246', 'demo_holder', '演示读者·借阅中', password, created)

        # ---------- 第二本书 + 副本 ----------
        book, made = Book.objects.get_or_create(
            isbn='9787111000002',
            defaults={
                'title': '数据结构与算法分析',
                'author': 'Mark Allen Weiss',
                'publisher': '机械工业出版社',
                'category': category,
                'call_number': 'TP/002',
                'price': '89.00',
            },
        )
        if made:
            created.append(f'书目《{book.title}》')

        copies = list(book.copies.order_by('id')[:2])
        while len(copies) < 2:
            copies.append(Copy.objects.create(book=book, branch=branch_community, shelf='B-02'))
            created.append(f'副本（{branch_community.name} B-02）')

        # ---------- 借阅：一册逾期、一册正常，使该书 0 可借（预约演示的前提）----------
        self._ensure_loan(actor, copies[0], overdue_reader, created, overdue=True)
        self._ensure_loan(actor, copies[1], holder_reader, created, overdue=False)

        # ---------- 进馆记录：两位读者进出一次，主账号留在馆内 ----------
        visits_made = self._visit_pair(actor, overdue_reader, branch_main, 'card')
        visits_made = self._visit_pair(actor, holder_reader, branch_main, 'qr') or visits_made
        visits_made = self._keep_inside(actor, main_reader, branch_main) or visits_made
        if visits_made:
            created.append('进馆记录与在馆人数')

        # ---------- 设备事件 → 告警 + 工单 + 门禁联动指令 ----------
        gate = Device.objects.filter(branch=branch_main, kind='gate').first()
        if gate:
            # 心跳让设备在线；烟感生成严重告警、维修工单与门禁解锁指令；故障生成警告与工单。
            results = [
                operations.ingest(actor, gate.pk, showcase_event_id('heartbeat'), 'heartbeat', {'message': '演示心跳'}),
                operations.ingest(actor, gate.pk, showcase_event_id('smoke'), 'smoke', {'message': '模拟烟感告警'}),
                operations.ingest(actor, gate.pk, showcase_event_id('fault'), 'fault', {'message': '门禁读卡器通信异常'}),
            ]
            # 设备在 seed_demo 里是离线状态，beat 的维护任务可能已按 offline_minutes 生成「设备离线」告警。
            # 心跳让它重新在线后，把该设备的离线告警关闭 —— 恢复心跳即自愈，符合真实运维预期。
            # 直接 update 以便批量关闭；seed 命令不需要逐条审计。
            resolved = Alert.objects.filter(
                device=gate, kind='offline', status__in=['open', 'acknowledged'],
            ).update(status='resolved', resolution='设备已恢复心跳（演示初始化）', updated_at=timezone.now())
            if any(not item.get('duplicate') for item in results) or resolved:
                created.append('设备事件 / 告警 / 工单 / 门禁联动指令')
        else:
            self.stdout.write(self.style.WARNING('未找到门禁设备，跳过告警与工单演示数据'))

        # ---------- 公告 ----------
        _, made = Announcement.objects.get_or_create(
            title='欢迎使用无人值守图书馆',
            defaults={
                'body': '本馆支持自助借还、预约取书与刷证进馆。借期 30 天（实名后 45 天），可续借 1 次；'
                        '逾期每天 0.50 元。还书后请放入还书箱，工作人员消毒上架后方可再次外借。',
                'published': True,
            },
        )
        if made:
            created.append('公告 1 条')

        # ---------- 汇总 ----------
        # available_count / total_count 是 API 查询集里的 annotation，不是模型字段，这里直接统计。
        total_copies = book.copies.count()
        available_copies = book.copies.filter(status='available').count()
        self.stdout.write(self.style.SUCCESS('演示数据已就绪：' + ('；'.join(created) if created else '无新增（已存在）')))
        self.stdout.write(
            f'《{book.title}》可借 {available_copies} / 共 {total_copies} 册；'
            f'在馆 {Visit.objects.filter(branch=branch_main, exited_at=None).count()} 人；'
            f'未关闭告警 {Alert.objects.filter(status__in=["open", "acknowledged"]).count()} 条'
        )
        self.stdout.write(
            f'逾期演示账号 {overdue_reader.phone}，借阅中账号 {holder_reader.phone}（口令同 --password）；'
            f'主演示账号 13800000002'
        )

    # ---------- 辅助 ----------

    @staticmethod
    def _reader(phone, username, nickname, password, created):
        user, made = User.objects.get_or_create(
            phone=phone, defaults={'username': username, 'role': 'reader', 'first_name': nickname},
        )
        if made:
            user.set_password(password)
            user.save()
            created.append(f'读者 {phone}（{nickname}）')
        return user

    def _ensure_loan(self, actor, copy, reader, created, *, overdue):
        """确保该副本在指定读者手上；逾期那册把应还日回拨并计罚款。"""
        active = Loan.objects.filter(copy=copy, returned_at=None).first()
        if active:
            if active.reader_id != reader.pk:
                self.stdout.write(self.style.WARNING(
                    f'副本 {copy.pk} 已在读者 {active.reader_id} 手上，跳过（不强行转移）'
                ))
                return active
            # 已逾期就保持原样，不再累计天数；尚未逾期则补正（便于重复执行后状态一致）
            if overdue and active.due_at > timezone.now():
                active.due_at = timezone.now() - OVERDUE_BACKDATE
                active.save(update_fields=['due_at'])
                circulation.assess_fine(active)
            return active

        result = circulation.borrow(actor, reader.pk, copy.pk)
        loan = Loan.objects.get(pk=result['id'])
        if overdue:
            # 借阅接口不允许指定借阅日期；演示需要一笔逾期借阅，只能回拨应还日。
            loan.due_at = timezone.now() - OVERDUE_BACKDATE
            loan.save(update_fields=['due_at'])
            circulation.assess_fine(loan)
            created.append(f'借阅 {loan.pk}（逾期 11 天，已计罚款）')
        else:
            created.append(f'借阅 {loan.pk}（正常在借）')
        return loan

    @staticmethod
    def _visit_pair(actor, reader, branch, method):
        """每个读者只造一次进出对：已有任何进馆记录就跳过，避免重复执行叠加客流。"""
        if Visit.objects.filter(reader=reader).exists():
            return False
        operations.access(actor, reader.pk, branch.pk, 'enter', method)
        operations.access(actor, reader.pk, branch.pk, 'exit', method)
        return True

    @staticmethod
    def _keep_inside(actor, reader, branch):
        """主演示账号留在馆内，使大屏「在馆人数」不为 0、门禁页显示「在馆中」。"""
        if Visit.objects.filter(reader=reader, exited_at=None).exists():
            return False
        operations.access(actor, reader.pk, branch.pk, 'enter', 'qr')
        return True
