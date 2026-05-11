from module.logger import logger

from tasks.SixRealms.moon_sea.skills import MoonSeaSkills


class MoonSeaMap(MoonSeaSkills):

    @staticmethod
    def contains_any_char(string, chars):
        return not set(string).isdisjoint(set(chars))

    def enter_island(self, isl_rule) -> bool:
        """进入岛屿, 失败返回False"""
        max_tries = 4
        self.device.click_record_clear()
        while True:
            self.screenshot()
            if max_tries <= 0:
                return False
            if not self.in_main() and self.appear(self.I_BACK_EXIT):
                break
            if self.appear_then_click(isl_rule, interval=2.5):
                max_tries -= 1
                continue
        logger.info('Entering island')
        return True

    def activate_store(self) -> bool:
        """
        最后打boss前面激活一次商店买东西
        @return: 有钱够就是True
        """
        logger.info('Activating store')
        cnt_act = 0
        while True:
            self.screenshot()
            if self.appear(self.I_UI_CONFIRM):
                self.ui_click_until_disappear(self.I_UI_CONFIRM, interval=2)
                break
            if cnt_act >= 3:
                logger.warning('Store is not active')
                return False
            if self.appear_then_click(self.I_M_STORE_ACTIVITY, interval=1.5):
                cnt_act += 1
                continue
        return True


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('日常1')
    d = Device(c)
    t = MoonSeaMap(c, d)
