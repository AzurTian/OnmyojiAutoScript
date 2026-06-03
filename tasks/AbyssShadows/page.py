from tasks.AbyssShadows.assets import AbyssShadowsAssets
from tasks.GameUi.page import Page, page_shirin, page_shikigami_records
from tasks.GlobalGame.assets import GlobalGameAssets

page_abyss = Page(AbyssShadowsAssets.I_CHECK_ABYSS)
page_abyss_map = Page(AbyssShadowsAssets.I_ABYSS_NAVIGATION)
page_shirin.connect(page_abyss, AbyssShadowsAssets.L_SHENSHE_TO_ABYSS, key="page_shirin->page_abyss")
page_abyss.connect(page_shirin, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_abyss->page_shirin")
page_abyss_map.connect(page_abyss, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_abyss_map->page_abyss")
page_abyss_map.connect(page_shikigami_records, AbyssShadowsAssets.I_ABYSS_SHIKI, key="page_abyss_map->page_shikigami_records", cost=4)
page_shikigami_records.connect(page_abyss_map, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_shikigami_records->page_abyss_map", cost=4)
