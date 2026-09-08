# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import timedelta

from module.logger import logger
from module.exception import TaskEnd
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
        self.goto_page(page_assist_battle)
        self.screenshot()
        _, evozone_res, _ = self.O_NORMAL_ASSIST_COUNT.ocr(self.device.image)
        _, realmraid_res, _ = self.O_REALMRAID_ASSIT_COUNT.ocr(self.device.image)
        logger.info(
            "协战次数：觉醒副本剩余 %s 次，结界突破剩余 %s 次",
            evozone_res,
            realmraid_res,
        )
        # test
        # realmraid_res = 1

        if self.conf.assist_battle_config.evozone_enable and evozone_res > 0:
            self.run_evozone(evozone_res)
            self.goto_page(page_main)
        if self.conf.assist_battle_config.realmraid_enable and realmraid_res > 0:
            self.run_realmraid(realmraid_res)
            self.goto_page(page_main)
        self.set_next_run(task='AssistBattle', success=True, finish=True)
        raise TaskEnd('AssistBattle')

    def run_evozone(self, count: int):
        """运行觉醒协战"""
        logger.hr('Run Evozone AssistBattle', 3)
        self.config.evo_zone.evo_zone_config.layer = Layer.FIVE
        self.config.evo_zone.evo_zone_config.kirin_type = KirinType.LIGHTNINGKIRIN
        self.config.evo_zone.general_battle_config.lock_team_enable = True
        self.limit_count = count
        self.limit_time = timedelta(hours=10)
        self.run_alone()

    def run_realmraid(self, count: int):
        """运行结界突破"""
        logger.hr('Run RealmRaid AssistBattle', 3)

        con = self.config.realm_raid

        con.raid_config.number_attack = count
        con.raid_config.exit_four = False
        con.raid_config.order_attack = '0 > 1 > 2 > 3 > 4 > 5'
        con.general_battle_config.lock_team_enable = True
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
