# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
from datetime import datetime, time, timedelta

from module.logger import logger
from module.exception import TaskEnd, GameStuckError
from module.base.timer import Timer
from tasks.Orochi.page import page_orochi
from tasks.Orochi.script_task import ScriptTask as OrochiScriptTask
from tasks.Orochi.config import Layer
from tasks.GameUi.page import page_main, page_soul_zones, page_shikigami_records
from tasks.TrueOrochi.assets import TrueOrochiAssets


class ScriptTask(OrochiScriptTask, TrueOrochiAssets):

    def _default_detect_categories(self) -> set[str]:
        categories = super()._default_detect_categories()
        categories.add("orochi")
        return categories

    def run(self):
        conf = self.config.true_orochi.true_orochi_config
        if conf.current_success >= 2:
            # 超过两次就说明这周打完了没有必要再打了
            logger.warning('This week is full')
            self.check_times(True)
            raise TaskEnd('TrueOrochi')
        self.goto_page(page_orochi)
        battle = self.check_true_orochi(True)
        if not battle:
            logger.warning('Not find true orochi')
            logger.warning('Try to battle orochi for ten times')
            # 判断是否需要挑战十层触发真蛇
            if not conf.find_true_orochi:
                logger.info('Not find_true_orochi_help')
                self.check_times(False)
                raise TaskEnd('TrueOrochi')
            battle = self.get_true_orochi()
        if not battle:
            # 如果还没有真蛇，那么就退出
            self.check_times(battle)
            raise TaskEnd('TrueOrochi')
        # 如果有真蛇，那么就开始战斗
        logger.hr('True Orochi Battle')
        # 御魂切换方式一
        if self.config.true_orochi.switch_soul.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(self.config.true_orochi.switch_soul.switch_group_team)
        # 御魂切换方式二
        if self.config.true_orochi.switch_soul.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(self.config.true_orochi.switch_soul.group_name,
                                         self.config.true_orochi.switch_soul.team_name)
        self.goto_page(page_orochi)
        conf.current_success += 1
        while 1:
            self.screenshot()
            if self.appear(self.I_ST_CREATE_ROOM):
                break
            if self.appear_then_click(self.I_UI_CONFIRM, interval=1):
                continue
            if self.appear_then_click(self.I_ST_FIRE, interval=4):
                # 修正已经挑战的次数, 注意这个是战斗开始之前的次数
                current, current_success, total = self.O_TIMES.ocr(self.device.image)
                if current_success < 0 or current_success > 2:
                    continue
                logger.info(f'current: {current}, current_success: {current_success}, total: {total}')
                conf.current_success = current_success
                self.config.save()
                continue
            if self.appear_then_click(self.I_FIND_TS, interval=1):
                continue
        self.ensure_private()
        while 1:
            self.screenshot()
            if self.appear(self.I_ST_FIRE_PREPARE):
                break
            if self.appear_then_click(self.I_FIRE, interval=3, threshold=0.7):
                continue
            if self.appear_then_click(self.I_UI_CONFIRM, interval=1):
                continue
            if self.appear_then_click(self.I_ST_CREATE_ROOM, interval=1):
                continue
        # 战斗准备
        logger.info('Battle prepare')
        self.ui_click(self.I_ST_FIRE_PREPARE, self.I_BUFF)
        while 1:
            self.screenshot()
            if not self.appear(self.I_BUFF):
                break
            if self.appear_then_click(self.I_ST_AUTO_FALSE, interval=1.8):
                continue

            # 下面代码 "点击准备" 会造成，点击了准备打第一层 循环 if not self.appear(self.I_BUFF): 时候跳出while循环，导致真蛇卡在第二层
            # if self.appear_then_click(self.I_PREPARE_HIGHLIGHT, interval=1.8):
            #     continue
        self.device.stuck_record_add('BATTLE_STATUS_S')
        self.device.click_record_clear()
        logger.info("Start battle process")
        check_timer = Timer(280)
        check_timer.start()
        check_count = 0
        while 1:
            self.screenshot()
            if self.appear(self.I_GREED_GHOST):
                sleep(0.7)
                self.screenshot()
                if not self.appear(self.I_GREED_GHOST):
                    continue
                # 左上角的贪吃鬼
                while 1:
                    self.screenshot()
                    if not self.appear(self.I_GREED_GHOST):
                        break
                    if self.appear_then_click(self.I_GREED_GHOST, interval=1):
                        continue
                    if self.appear_then_click(self.I_ST_FRAME, interval=1):
                        continue
                break
            if self.appear_then_click(self.I_ST_FRAME, interval=1):
                continue
            if check_timer.reached():
                if check_count > 3:
                    raise GameStuckError
                check_count += 1
                logger.warning('Battle timeout')
                check_timer.reset()
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')
            sleep(0.5)

        logger.info("Battle process end")
        self.goto_page(page_main)
        self.check_times(battle)
        raise TaskEnd('TrueOrochi')

    def get_true_orochi(self) -> bool:
        """获取真蛇(攻打十层10次, 发现真蛇就退出, 会更改limit_count)"""
        self.config.orochi.orochi_config.layer = Layer.TEN
        self.limit_count = 0
        self.limit_time = timedelta(hours=10)
        # 切换十层御魂
        if self.config.true_orochi.switch_soul.enable_switch_layer_soul:
            self.switch_orochi_souls()
            self.goto_page(page_orochi)
        while True:
            self.screenshot()
            if self.check_true_orochi(False):
                logger.info('Find true orochi')
                return True
            if self.limit_count >= 10:
                logger.warning('Not find true orochi')
                break
            self.limit_count += 1
            self.run_alone()
        return False

    def check_true_orochi(self, screenshot=False) -> bool:
        """
        检查是否出现真蛇（要求当前的界面必须是在御魂挑战的界面）
        :return:
        """
        if screenshot:
            self.screenshot()
        return self.appear(self.I_FIND_TS)

    def check_times(self, battle: bool):
        """
        后续的次数和时间设置
        :param battle:
        :param current_success: 这周的成功次数
        :return:
        """
        now = datetime.now()
        now_year, now_week_number, now_weekday = now.isocalendar()
        if battle:
            next_run = now + self.config.true_orochi.scheduler.success_interval
        else:
            next_run = now + self.config.true_orochi.scheduler.failure_interval
        next_run_year, next_run_week_number, next_run_weekday = next_run.isocalendar()
        # 如果下次运行的时间是下一周，那么就重置成功次数
        if now_week_number != next_run_week_number:
            logger.info('Reset current_success')
            self.config.true_orochi.true_orochi_config.current_success = 0
        else:
            # 如果不是下一周且战斗成功那么就加一
            logger.info('Add current_success by 1')
            self.config.true_orochi.true_orochi_config.current_success += 1 if battle else 0
            self.config.true_orochi.true_orochi_config.current_success = min(2, self.config.true_orochi.true_orochi_config.current_success)
        self.config.save()
        self.set_next_run(task='TrueOrochi', target=next_run)


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()
