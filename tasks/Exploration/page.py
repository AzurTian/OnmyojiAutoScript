from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Exploration.assets import ExplorationAssets
from tasks.GameUi.page import (all_of, any_of, page_battle, page_battle_prepare, page_battle_team, page_exploration,
                               page_main, page_shikigami_records)
from tasks.GameUi.page_definition import Page
from tasks.GlobalGame.assets import GlobalGameAssets


# 探索副本入口
page_exp_entrance = Page(ExplorationAssets.I_E_EXPLORATION_CLICK)
page_exp_entrance.connect(page_exploration, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_exp_entrance->page_exploration")
page_exploration.connect(page_exp_entrance, action=lambda task: task.open_expect_level,
                         key="page_exploration->page_exp_entrance")


def quit_explore_main(task) -> bool:
    while True:
        task.screenshot()
        if task.appear(ExplorationAssets.I_E_EXPLORATION_CLICK) or \
                task.appear(ExplorationAssets.I_EXPLORATION_TITLE) or \
                task.appear(task.I_CHECK_EXPLORATION):
            return True
        if task.appear_then_click(ExplorationAssets.I_E_EXIT_CONFIRM, interval=0.8) or \
                task.appear_then_click(task.I_UI_BACK_YELLOW, interval=2.8):
            continue
    return False

# 探索副本主界面
page_exp_main = Page(any_of(ExplorationAssets.I_E_SETTINGS_BUTTON, ExplorationAssets.I_E_AUTO_ROTATE_ON,
                            ExplorationAssets.I_E_AUTO_ROTATE_OFF))
page_exp_main.connect(page_exp_entrance, action=quit_explore_main, key="page_exp_main->page_exp_entrance")
page_exp_entrance.connect(page_exp_main, ExplorationAssets.I_E_EXPLORATION_CLICK, key="page_exp_entrance->page_exp_main")

