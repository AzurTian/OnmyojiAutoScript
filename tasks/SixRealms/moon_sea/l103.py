from module.base.timer import Timer
from module.logger import logger
from tasks.SixRealms.moon_sea.skills import MoonSeaSkills


class MoonSeaL103(MoonSeaSkills):
    def run_l103(self):
        # 宝箱还是精英
        logger.hr('Island 103')
        timeout_timer = Timer(2).start()
        while True:
            self.screenshot()
            if timeout_timer.reached():
                logger.warning('Not recognize chaos land')
                break
            if self.appear(self.I_L103_LAND_FLAG) or \
                    self.appear(self.I_L103_EXIT):
                break
        is_box: bool = self.appear(self.I_L103_EXIT)
        if is_box:
            logger.info('Access to Box')
            while 1:
                self.screenshot()
                if self.in_main():
                    logger.info('Not punched the treasure box')
                    return
                if self.appear_then_click(self.I_UI_UNCHECK, interval=0.5):
                    continue
                if self.appear_then_click(self.I_UI_CONFIRM, interval=1):
                    continue
                if self.appear_then_click(self.I_L103_EXIT, interval=4):
                    continue
        if not is_box :
            self.battle_l103()
        logger.info('Island 103 Finished')

    def battle_l103(self):
        # 打精英
        logger.info('Start Island battle')
        self.device.stuck_record_clear()
        self.ui_click(self.C_NPC_FIRE_CENTER, self.I_NPC_FIRE, interval=2.5)
        self.battle_lock_team()
        self.island_battle()
        logger.info('Island battle finished')
        self.select_skill()

if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    t = MoonSeaL103(c, d)
    t.screenshot()

    t.run_l103()
