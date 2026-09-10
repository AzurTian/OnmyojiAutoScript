# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import timedelta
from time import sleep

from module.logger import logger
from module.exception import TaskEnd
from tasks.Component.SwitchAccount.switch_account import SwitchAccount
from tasks.EvoZone.config import Layer, KirinType
from tasks.EvoZone.script_task import ScriptTask as EvoZoneScriptTask
from tasks.RealmRaid.script_task import ScriptTask as RealmRaidScriptTask
from tasks.GameUi.page import (
    page_main,
    page_awake_zones,
    page_realm_raid,
    page_assist_battle,
    page_friends,
)
from tasks.AssistBattle.assets import AssistBattleAssets
from tasks.AssistBattle.config import AssistBattleConfig


class ScriptTask(
    EvoZoneScriptTask,
    RealmRaidScriptTask,
    AssistBattleAssets,
):

    conf: AssistBattleConfig

    def run(self):
        self.conf = self.config.model.assist_battle
        accounts = [account for account in self.conf.account_list if account.is_valid()]
        results = []
        if not accounts:
            logger.info('No AssistBattle account configured; run on current account')
            evozone_done, realmraid_done, evozone_final, realmraid_final = (
                self.run_current_account()
            )
            results.append(
                {
                    'character': account.character,
                    'svr': account.svr,
                    'evozone_done': evozone_done,
                    'realmraid_done': realmraid_done,
                    'evozone_final': evozone_final,
                    'realmraid_final': realmraid_final,
                }
            )
        else:
            for account in accounts:
                logger.hr(
                    'Run AssistBattle for %s-%s' % (account.character, account.svr), 2
                )
                if not SwitchAccount(self.config, self.device, account).switchAccount():
                    logger.warning(
                        'Switch to %s-%s failed; skip it',
                        account.character,
                        account.svr,
                    )
                    continue
                evozone_done, realmraid_done, evozone_final, realmraid_final = (
                    self.run_current_account()
                )
                results.append(
                    {
                        'character': account.character,
                        'svr': account.svr,
                        'evozone_done': evozone_done,
                        'realmraid_done': realmraid_done,
                        'evozone_final': evozone_final,
                        'realmraid_final': realmraid_final,
                    }
                )
        # 输出协战结果
        logger.hr('AssistBattle Result', 2)
        push_content = []
        push_content.append(f"本次执行任务：")
        for result in results:
            message = (
                f"{result['character']}-{result['svr']}: "
                f"觉醒副本 {result['evozone_done']}/15，"
                f"结界突破 {result['realmraid_done']}/3"
            )
            logger.info(message)
            push_content.append(message)
        push_content.append(f"今日协战任务：")
        for result in results:
            message = (
                f"{result['character']}-{result['svr']}: "
                f"觉醒副本 {result['evozone_final']}/15，"
                f"结界突破 {result['realmraid_final']}/3"
            )
            logger.info(message)
            push_content.append(message)
        # 推送协战完成结果
        if self.conf.assist_battle_config.result_push_enable:
            self.config.notifier.push(
                title='一键协战完成',
                content='<{}><br>{}'.format(
                    self.config.config_name,
                    '<br>'.join(push_content),
                ),
            )
        self.set_next_run(task='AssistBattle', success=True, finish=True)
        raise TaskEnd('AssistBattle')

    def run_current_account(self):
        # 执行任务前先获取本账号协战剩余次数
        start_evozone, start_realmraid = self.get_assist_battle_count()
        total_evozone = 15
        total_realmraid = 3

        if self.conf.assist_battle_config.evozone_enable and start_evozone > 0:
            self.run_evozone(start_evozone)
            self.goto_page(page_main)
        if self.conf.assist_battle_config.realmraid_enable and start_realmraid > 0:
            self.run_realmraid(start_realmraid)
            self.goto_page(page_main)

        end_evozone, end_realmraid = self.get_assist_battle_count()
        evozone_done = start_evozone - end_evozone
        realmraid_done = start_realmraid - end_realmraid

        evozone_final = total_evozone - end_evozone
        realmraid_final = total_realmraid - end_realmraid
        logger.info(
            "本次协战完成：觉醒 %s 次，结界突破 %s 次",
            evozone_done,
            realmraid_done,
        )
        logger.info(
            "最终协战完成：觉醒 %s 次，结界突破 %s 次",
            evozone_final,
            realmraid_final,
        )
        return evozone_done, realmraid_done, evozone_final, realmraid_final

    def get_assist_battle_count(self):
        """获取当前账号剩余的协战次数。"""
        self.goto_page(page_assist_battle)
        # 切换界面可能卡顿等个动画
        sleep(0.5)
        self.screenshot()
        _, evozone_res, _ = self.O_NORMAL_ASSIST_COUNT.ocr(self.device.image)
        _, realmraid_res, _ = self.O_REALMRAID_ASSIT_COUNT.ocr(self.device.image)

        return evozone_res, realmraid_res

    def run_evozone(self, count: int):
        """运行觉醒协战"""
        logger.hr('Run Evozone AssistBattle', 3)
        self.config.evo_zone.evo_zone_config.layer = Layer.FIVE
        self.config.evo_zone.evo_zone_config.kirin_type = KirinType.LIGHTNINGKIRIN
        self.config.evo_zone.general_battle_config.lock_team_enable = True
        self.current_count = 0
        self.limit_count = count
        self.limit_time = timedelta(hours=10)
        self.run_alone()

    def run_realmraid(self, count: int):
        """运行结界突破"""
        logger.hr('Run RealmRaid AssistBattle', 3)

        con = self.config.realm_raid

        con.raid_config.number_attack = count
        if self.conf.assist_battle_config.realmraid_easy_enable:
            con.raid_config.exit_four = False
            con.raid_config.order_attack = '0 > 1 > 2 > 3 > 4 > 5'
        con.general_battle_config.lock_team_enable = True
        con.switch_soul_config.enable = False
        if self.conf.assist_battle_config.switch_soul_enable:
            con.switch_soul_config.enable = True
        self.run_realmraid_core(con)


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()
