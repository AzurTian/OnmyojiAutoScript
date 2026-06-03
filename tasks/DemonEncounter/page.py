from tasks.DemonEncounter.assets import DemonEncounterAssets
from tasks.GameUi.assets import GameUiAssets
from tasks.GameUi.default_pages import page_demon_encounter, page_town
from tasks.GameUi.page_definition import Page
from tasks.GlobalGame.assets import GlobalGameAssets

# 现世逢魔页面
page_rwt = Page(GameUiAssets.I_CHECK_DEMON_ENCOUNTER)
page_rwt.connect(page_demon_encounter, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_rwt->page_demon_encounter")
# 町中直接到现世逢魔
page_town.connect(page_rwt, GameUiAssets.I_TOWN_GOTO_DEMON_ENCOUNTER, key="page_town->page_rwt")
# 逢魔之时到现世逢魔
page_demon_encounter.connect(page_rwt, DemonEncounterAssets.I_DE_TO_REAL_WORLD, key="page_demon_encounter->page_rwt")
