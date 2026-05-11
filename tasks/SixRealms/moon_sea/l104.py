
from module.logger import logger
from tasks.SixRealms.moon_sea.skills import MoonSeaSkills


class MoonSeaL104(MoonSeaSkills):
    def run_l104(self):
        logger.hr('Start Island battle')
        logger.info('Island 104')
        self.ui_click(self.C_NPC_FIRE_RIGHT, self.I_NPC_FIRE, interval=2.5)
        self.battle_lock_team()
        self.island_battle()
        logger.info('Island battle finished')
        self.select_skill()

if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    t = MoonSeaL104(c, d)
    t.screenshot()

    t.run_l104()

