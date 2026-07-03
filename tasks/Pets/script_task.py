# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import timedelta

from module.logger import logger
from module.exception import TaskEnd
from tasks.GameUi.default_pages import page_pet, page_shikigami_records
from tasks.Orochi.config import Layer
from tasks.Orochi.page import page_orochi
from tasks.Orochi.script_task import ScriptTask as OrochiScriptTask
from tasks.GameUi.page import page_main
from tasks.Pets.assets import PetsAssets
from tasks.Pets.config import PetsConfig

class ScriptTask(OrochiScriptTask, PetsAssets):

    conf: PetsConfig

    def run(self):
        self.conf = self.config.pets.pets_config
        self.goto_page(page_pet)
        if self.conf.pets_feast:
            self._feed()
            self.goto_page(page_main)
        if self.conf.enable_orochi_ten_once:
            self.run_orochi()
            self.goto_page(page_main)
        self.set_next_run(task='Pets', success=True, finish=True)
        raise TaskEnd('Pets')

    def _feed(self):
        """快速喂养"""
        logger.hr('Feed', 3)
        self.ui_click(self.I_PET_FEAST, self.I_PET_FEED)
        number = self.O_PET_FEED_AP.ocr(self.device.image)
        if number == 0:
            # 已经投喂过了
            logger.warning('Already feed')
            self.appear_then_click(self.I_UI_BACK_CIRCLE)
            return
        self.ui_click(self.I_PET_FEED, self.I_PET_SKIP)
        self.ui_click_until_disappear(self.I_PET_SKIP)

    def run_orochi(self):
        """运行一次御魂十层"""
        logger.hr('Run Orochi', 3)
        self.config.orochi.orochi_config.layer = Layer.TEN
        self.limit_count = 1
        self.limit_time = timedelta(hours=10)
        self.goto_page(page_orochi)
        if self.conf.enable_switch_layer_soul:
            self.switch_orochi_souls()
        self.run_alone()

if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()
