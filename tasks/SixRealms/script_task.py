# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import datetime

from pathlib import Path

from tasks.GameUi.page import page_main, page_soul_zones, page_shikigami_records
from module.logger import logger
from module.exception import TaskEnd


from tasks.SixRealms.config import SixRealmsType
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_six_gates
from tasks.SixRealms.moon_sea.moon_sea import MoonSea
from module.logger import logger
from tasks.SixRealms.peacock_kingdom.peacock_kingdom import PeacockKingdom


class ScriptTask(GameUi, SwitchSoul, MoonSea, PeacockKingdom):

    def run(self):
        _config = self.config.model.six_realms
        if _config.switch_soul_config_1.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(_config.switch_soul_config_1.switch_group_team)
        if _config.switch_soul_config_1.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(
                _config.switch_soul_config_1.group_name,
                _config.switch_soul_config_1.team_name
            )
        if _config.switch_soul_config_2.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(_config.switch_soul_config_2.switch_group_team)
        if _config.switch_soul_config_2.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(
                _config.switch_soul_config_2.group_name,
                _config.switch_soul_config_2.team_name
            )
        self.goto_page(page_six_gates)
        cnt = 0
        while True:
            if cnt >= self._conf.limit_count:
                logger.info('Run out of count, exit')
                break
            if datetime.now() - self.start_time >= self._conf.limit_time_v:
                logger.info('Run out of time, exit')
                break
            match _config.six_realms_gate.six_realms_type:
                case SixRealmsType.MOON_SEA:
                    self.run_moon_sea()
                case SixRealmsType.PEACOCK_KINGDOM:
                    self.run_peacock_kingdom()
                case _:
                    logger.warning('Unknown six realms type')
                    self.run_moon_sea()
            cnt += 1
        self.goto_page(page_main)
        self.set_next_run('SixRealms', success=True, finish=True)
        raise TaskEnd

if __name__ == '__main__':
    path = Path(r'D:\dev\OnmyojiAutoScript\tasks\SixRealms\moon_sea\ms')

    for file in path.iterdir():
        # 只处理文件，并且文件名以 gate1_ 开头
        if file.is_file() and file.name.startswith('gate1_'):
            new_name = 'ms_' + file.name[len('gate1_'):]
            new_path = file.with_name(new_name)

            print(f'{file.name} -> {new_name}')
            file.rename(new_path)

