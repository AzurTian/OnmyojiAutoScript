from tasks.GameUi.action import sequence
from tasks.GameUi.default_pages import random_click, page_battle, page_battle_prepare, page_battle_result, page_reward
from tasks.GameUi.matcher import any_of, all_of
from tasks.GameUi.page_definition import Page
from tasks.GlobalGame.assets import GlobalGameAssets
from tasks.SixRealms.assets import SixRealmsAssets
from tasks.SixRealms.page import page_peacock_kingdom, page_sr_prepare_exit, page_sr_open_store

# 孔雀国准备界面
page_pk_prepare = Page(any_of(SixRealmsAssets.I_PK_START_CONFIRM, SixRealmsAssets.I_PK_START_CONFIRM2,
                              SixRealmsAssets.I_PK_START_THIRD_SKILL, SixRealmsAssets.I_MFIRST_SKILL))
# 孔雀国主界面
page_pk_main = Page(any_of(SixRealmsAssets.I_PK_CHECK_MAIN, SixRealmsAssets.I_PK_BOSS_PREPARE),
                          category="peacock_kingdom", priority=25)
page_pk_prepare.connect(page_pk_main, sequence(SixRealmsAssets.I_PK_START_CONFIRM,
                                               SixRealmsAssets.I_PK_START_CONFIRM2, SixRealmsAssets.I_PK_START_THIRD_SKILL,
                                               SixRealmsAssets.I_MFIRST_SKILL, success_index=3),
                        key="page_pk_prepare->page_pk_main")

# 挑战页面
page_pk_challenge = Page(SixRealmsAssets.I_PK_BATTLE_FIRE, category="peacock_kingdom", priority=25)

# 宁息之屿
page_pk_shop_land = Page(all_of(SixRealmsAssets.I_PK_STORE_EXIT, SixRealmsAssets.I_PK_STORE_REFRESH,
                                SixRealmsAssets.I_PK_STORE_STABLE_FLAG), category="peacock_kingdom")
page_pk_shop_land.connect(page_pk_main, SixRealmsAssets.I_PK_STORE_EXIT, key="page_pk_shop_land->page_pk_main")

# 神秘之屿
page_pk_mistery_land = Page(any_of(SixRealmsAssets.I_PK_MYSTERY_IMITATE, SixRealmsAssets.I_MISTERY_COIN_RIGHT_TOP),
                            category="peacock_kingdom")
page_pk_mistery_land.connect(page_pk_main, GlobalGameAssets.I_UI_BACK_BLUE, key="page_pk_mistery_land->page_pk_main")

# 混沌之屿
page_pk_chaos_land = Page(any_of(SixRealmsAssets.I_PK_CHAOS_BOX, SixRealmsAssets.I_PK_CHAOS_ELITE_FLAG),
                          category="peacock_kingdom")
page_pk_chaos_land.connect(page_pk_main, SixRealmsAssets.I_PK_CHAOS_EXIT, key="page_pk_chaos_land->page_pk_main")
page_pk_chaos_land.connect(page_pk_challenge, SixRealmsAssets.C_NPC_FIRE_CENTER, key="page_pk_chaos_land->page_pk_challenge")
page_pk_challenge.connect(page_pk_chaos_land, GlobalGameAssets.I_UI_BACK_BLUE, key="page_pk_challenge->page_pk_chaos_land")

# 绽放之屿
page_pk_bloom_land = Page(SixRealmsAssets.I_PK_BLOOM_EXIT, category="peacock_kingdom")
page_pk_bloom_land.connect(page_pk_main, SixRealmsAssets.I_PK_BLOOM_EXIT, key="page_pk_bloom_land->page_pk_main")

# 鏖战之屿
page_pk_battle_land = Page(SixRealmsAssets.I_PK_BATTLE_COMMON, category="peacock_kingdom")
page_pk_battle_land.connect(page_pk_challenge, SixRealmsAssets.C_NPC_FIRE_RIGHT, key="page_pk_battle_land->page_pk_challenge")
page_pk_challenge.connect(page_pk_battle_land, GlobalGameAssets.I_UI_BACK_BLUE, key="page_pk_challenge->page_pk_battle_land")

# 孔雀国地图
page_pk_map = Page(SixRealmsAssets.I_PK_CHECK_MAP, category="peacock_kingdom")
page_pk_map.connect(page_pk_main, GlobalGameAssets.I_UI_BACK_BLUE, key="page_pk_map->page_pk_main")

# 主界面退出弹窗
page_pk_exit = Page(SixRealmsAssets.I_PK_EXIT_MAIN, category="peacock_kingdom", priority=88)
page_pk_exit.connect(page_peacock_kingdom, SixRealmsAssets.I_PK_EXIT_MAIN, key="page_pk_exit->page_moon_sea")
page_pk_exit.connect(page_pk_shop_land, random_click(ltrb=(True, True, True, True)), key="page_pk_exit->page_pk_shop_land")
page_pk_exit.connect(page_pk_main, random_click(ltrb=(True, True, True, True)), key="page_pk_exit->page_pk_main")
page_pk_exit.connect(page_pk_chaos_land, random_click(ltrb=(True, True, True, True)), key="page_pk_exit->page_pk_chaos_land")
page_pk_main.connect(page_pk_exit, GlobalGameAssets.I_UI_BACK_BLUE, key="page_pk_main->page_pk_exit")
page_pk_battle_land.connect(page_pk_exit, GlobalGameAssets.I_UI_BACK_BLUE, key="page_pk_battle_land->page_pk_exit")

# 准备界面退出
page_sr_prepare_exit.connect(page_peacock_kingdom, GlobalGameAssets.I_UI_CONFIRM, key="page_sr_prepare_exit->page_moon_sea")
page_sr_prepare_exit.connect(page_pk_prepare, GlobalGameAssets.I_UI_CANCEL, key="page_sr_prepare_exit->page_pk_prepare")
page_pk_prepare.connect(page_sr_prepare_exit, GlobalGameAssets.I_UI_BACK_BLUE, key="page_pk_prepare->page_sr_prepare_exit")
page_sr_prepare_exit.add_enter_failure_hooks(GlobalGameAssets.I_UI_BACK_BLUE)

# 商店打开弹窗
page_sr_open_store.connect(page_pk_main, GlobalGameAssets.I_UI_CANCEL, key="page_sr_open_store->page_pk_main")
page_pk_main.connect(page_sr_open_store, SixRealmsAssets.I_M_STORE_ACTIVITY, key="page_pk_main->page_sr_open_store")
