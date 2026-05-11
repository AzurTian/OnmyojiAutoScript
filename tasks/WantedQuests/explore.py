from module.atom.gif import RuleGif
from module.atom.image import RuleImage
from module.logger import logger
from tasks.Exploration import page as pages
from tasks.Exploration.config import UpType
from tasks.Exploration.script_task import ScriptTask as ExplorationScriptTask
from tasks.Exploration.version import HighLight
from typing import Optional


class ExploreWantedBoss(Exception):
    # 出现一种情况，要求的怪是仅仅最后的Boss，其他小怪不是
    pass


class WQExplore(ExplorationScriptTask, HighLight):
    _explor_cnt: int = 0  # 探索次数
    _max_cnt: int = 0  # 探索最大次数

    def search_up_fight(self, up_type: UpType = None) -> Optional[RuleImage | RuleGif]:
        if self.appear(self.TEMPLATE_GIF):
            self.fire_monster_type = 'wq_normal'
            return self.TEMPLATE_GIF
        return None

    def check_exit(self, current_page: pages.Page | None) -> bool:
        need_exit = self._explor_cnt >= self._max_cnt
        # 探索次数已经够了但是任何怪物都没打过
        if need_exit and self.fire_monster_type == '':
            raise ExploreWantedBoss
        return need_exit

    def arrive_end(self) -> bool:
        arrived_end = super().arrive_end()
        self._explor_cnt += 1 if arrived_end else 0
        return arrived_end

    def fire(self, button) -> bool:
        fired = super().fire(button)
        self._explor_cnt += 1 if fired and self.fire_monster_type == 'boss' else 0
        return fired

    def explore(self, goto: RuleImage, num: int):
        logger.info(f'Start exploring with number: {num}')
        self._max_cnt = num
        self._explor_cnt = 0
        while True:
            self.screenshot()
            if pages.page_exp_entrance == self.get_current_page(False):
                break
            if self.appear_then_click(goto, interval=2):
                continue
        self.run_alone()

if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    from tasks.WantedQuests.assets import WantedQuestsAssets

    config = Config('oas1')
    device = Device(config)
    t = WQExplore(config, device)
    t.explore(goto=WantedQuestsAssets.I_GOTO_1, num=2)
