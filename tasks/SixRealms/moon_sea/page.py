from tasks.GameUi.action import sequence
from tasks.GameUi.default_pages import random_click, page_battle, page_battle_prepare, page_battle_result, page_reward
from tasks.GameUi.matcher import any_of, all_of
from tasks.GameUi.page_definition import Page
from tasks.GlobalGame.assets import GlobalGameAssets
from tasks.SixRealms.assets import SixRealmsAssets
from tasks.SixRealms.page import page_moon_sea, page_sr_prepare_exit, page_sr_open_store

# 月之海准备界面
page_ms_prepare = Page(any_of(SixRealmsAssets.I_MSTART_CONFIRM, SixRealmsAssets.I_MSTART_CONFIRM2,
                              SixRealmsAssets.I_MFIRST_SKILL))
# 月之海主界面
page_ms_main = Page(any_of(SixRealmsAssets.I_MS_CHECK_MAIN, SixRealmsAssets.I_BOSS_FIRE_PREPARE),
                    category="moon_sea", priority=25)
page_ms_prepare.connect(page_ms_main, sequence(SixRealmsAssets.I_MSTART_CONFIRM,
                                               SixRealmsAssets.I_MSTART_CONFIRM2, SixRealmsAssets.I_MFIRST_SKILL,
                                               success_index=2),
                        key="page_ms_prepare->page_ms_main")
# 挑战页面
page_ms_challenge = Page(SixRealmsAssets.I_BATTLE_FIRE, category="moon_sea", priority=25)

# 宁息之屿
page_ms_shop_land = Page(all_of(SixRealmsAssets.I_STORE_EXIT, SixRealmsAssets.I_STORE_REFRESH,
                                SixRealmsAssets.I_STORE_STABLE_FLAG), category="moon_sea")
page_ms_shop_land.connect(page_ms_main, SixRealmsAssets.I_STORE_EXIT, key="page_ms_shop_land->page_ms_main")
page_ms_main.connect(page_ms_shop_land, SixRealmsAssets.I_MS_LAND_SHOP, key="page_ms_main->page_ms_shop_land")

# 神秘之屿
page_ms_mistery_land = Page(any_of(SixRealmsAssets.I_MISTERY_IMITATE, SixRealmsAssets.I_MISTERY_COIN_RIGHT_TOP), 
                            category="moon_sea")
page_ms_mistery_land.connect(page_ms_main, GlobalGameAssets.I_UI_BACK_BLUE, key="page_ms_mistery_land->page_ms_main")

# 混沌之屿
page_ms_chaos_land = Page(any_of(SixRealmsAssets.I_CHAOS_BOX_EXIT, SixRealmsAssets.I_CHAOS_ELITE_FLAG), 
                          category="moon_sea")
page_ms_chaos_land.connect(page_ms_main, SixRealmsAssets.I_CHAOS_BOX_EXIT, key="page_ms_chaos_land->page_ms_main")
page_ms_chaos_land.connect(page_ms_challenge, SixRealmsAssets.C_NPC_FIRE_CENTER, key="page_ms_chaos_land->page_ms_challenge")
page_ms_challenge.connect(page_ms_chaos_land, GlobalGameAssets.I_UI_BACK_BLUE, key="page_ms_challenge->page_ms_chaos_land")
page_ms_main.connect(page_ms_chaos_land, SixRealmsAssets.I_MS_LAND_CHAOS, key="page_ms_main->page_ms_chaos_land")

# 星之屿
page_ms_star_land = Page(SixRealmsAssets.I_STAR_DANGER, category="moon_sea")
page_ms_star_land.connect(page_ms_challenge, SixRealmsAssets.C_NPC_FIRE_LEFT, key="page_ms_star_land->page_ms_challenge")
page_ms_challenge.connect(page_ms_star_land, GlobalGameAssets.I_UI_BACK_BLUE, key="page_ms_challenge->page_ms_star_land")
page_ms_main.connect(page_ms_star_land, SixRealmsAssets.I_MS_LAND_STAR, key="page_ms_main->page_ms_star_land")

# 鏖战之屿
page_ms_battle_land = Page(SixRealmsAssets.I_BATTLE_COMMON, category="moon_sea")
page_ms_battle_land.connect(page_ms_challenge, SixRealmsAssets.C_NPC_FIRE_RIGHT, key="page_ms_battle_land->page_ms_challenge")
page_ms_challenge.connect(page_ms_battle_land, GlobalGameAssets.I_UI_BACK_BLUE, key="page_ms_challenge->page_ms_battle_land")
page_ms_main.connect(page_ms_battle_land, SixRealmsAssets.I_MS_LAND_FIRE, key="page_ms_main->page_ms_battle_land")

# 月之海地图
page_ms_map = Page(SixRealmsAssets.I_MS_CHECK_MAP, category="moon_sea")
page_ms_map.connect(page_ms_main, GlobalGameAssets.I_UI_BACK_BLUE, key="page_ms_map->page_ms_main")

# 主界面退出弹窗
page_ms_exit = Page(SixRealmsAssets.I_EXIT_SIXREALMS, category="moon_sea", priority=88)
page_ms_exit.connect(page_moon_sea, SixRealmsAssets.I_EXIT_SIXREALMS, key="page_ms_exit->page_moon_sea")
page_ms_exit.connect(page_ms_shop_land, random_click(ltrb=(True, True, True, True)), key="page_ms_exit->page_ms_shop_land")
page_ms_exit.connect(page_ms_main, random_click(ltrb=(True, True, True, True)), key="page_ms_exit->page_ms_main")
page_ms_exit.connect(page_ms_chaos_land, random_click(ltrb=(True, True, True, True)), key="page_ms_exit->page_ms_chaos_land")
page_ms_main.connect(page_ms_exit, GlobalGameAssets.I_UI_BACK_BLUE, key="page_ms_main->page_ms_exit")
page_ms_battle_land.connect(page_ms_exit, GlobalGameAssets.I_UI_BACK_BLUE, key="page_ms_battle_land->page_ms_exit")

# 准备界面退出
page_sr_prepare_exit.connect(page_moon_sea, GlobalGameAssets.I_UI_CONFIRM, key="page_sr_prepare_exit->page_moon_sea")
page_sr_prepare_exit.connect(page_ms_prepare, GlobalGameAssets.I_UI_CANCEL, key="page_sr_prepare_exit->page_ms_prepare")
page_ms_prepare.connect(page_sr_prepare_exit, GlobalGameAssets.I_UI_BACK_BLUE, key="page_ms_prepare->page_sr_prepare_exit")
page_sr_prepare_exit.add_enter_failure_hooks(GlobalGameAssets.I_UI_BACK_BLUE)
# 商店
page_sr_open_store.connect(page_ms_main, GlobalGameAssets.I_UI_CANCEL, key="page_sr_open_store->page_ms_main")
page_ms_main.connect(page_sr_open_store, SixRealmsAssets.I_M_STORE_ACTIVITY, key="page_ms_main->page_sr_open_store")
