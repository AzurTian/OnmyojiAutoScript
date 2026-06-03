from tasks.ActivityShikigami.assets import ActivityShikigamiAssets
from tasks.ActivityShikigami.base_act import BaseAct
import tasks.ActivityShikigami.page as pages
from tasks.GlobalGame.assets import GlobalGameAssets


class FakeGodAct(BaseAct):
    """伪神活动"""

    def before_run(self):
        super().before_run()
        page_act = self.navigator.resolve_page(pages.page_act)
        page_act_pass = self.navigator.resolve_page(pages.page_act_pass)
        page_act_ap = self.navigator.resolve_page(pages.page_act_ap)
        # 爬塔活动第2个页面
        page_act_2 = self.navigator.add_page(pages.Page(ActivityShikigamiAssets.I_AS_CHECK_MAIN_2,
                                                        category='activity_shikigami'))
        page_act_2.add_enter_success_hooks(GlobalGameAssets.I_UI_BACK_RED)
        page_act.connect(page_act_2, ActivityShikigamiAssets.I_TO_BATTLE_MAIN, key="page_act->page_act_2")
        page_act_2.connect(page_act, GlobalGameAssets.I_UI_BACK_CIRCLE, key="page_act_2->page_act")
        # 爬塔暗黑页面
        page_act_dark = self.navigator.add_page(pages.Page(ActivityShikigamiAssets.I_AS_CLOSE_EYE,
                                                           category='activity_shikigami', priority=75))
        page_act_dark.add_enter_failure_hooks(GlobalGameAssets.I_UI_BACK_RED)
        page_act_dark.add_enter_success_hooks(ActivityShikigamiAssets.I_AS_LOCATE)
        page_act_dark.connect(page_act, GlobalGameAssets.I_UI_BACK_CIRCLE, key="page_act_dark->page_act")
        page_act_2.connect(page_act_dark, ActivityShikigamiAssets.I_AS_OPEN_EYE, key="page_act_2->page_act_dark")
        # 门票和暗黑页面关联
        page_act_pass.connect(page_act_dark, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_act_pass->page_act_2")
        page_act_dark.connect(page_act_pass, ActivityShikigamiAssets.I_AS_TO_PASS, key="page_act_dark->page_act_pass")
        # 主界面和体力页面关联
        page_act.connect(page_act_ap, ActivityShikigamiAssets.I_TO_BATTLE_AP, key="page_act->page_act_ap")
        # 100体和暗黑页面关联
        pages.page_act_ap100.connect(page_act_dark, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_act_ap100->page_act_2")
        page_act_dark.connect(pages.page_act_ap100, ActivityShikigamiAssets.O_ENTER_AP100,
                              key="page_act_dark->page_act_ap100")
