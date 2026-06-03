from tasks.CollectiveMissions.assets import CollectiveMissionsAssets
from tasks.GameUi.default_pages import page_shirin
from tasks.GameUi.matcher import all_of
from tasks.GameUi.page_definition import Page
from tasks.GlobalGame.assets import GlobalGameAssets

page_collective_missions = Page(all_of(CollectiveMissionsAssets.I_CM_RECORDS, CollectiveMissionsAssets.I_CM_SWITCH,
                                       GlobalGameAssets.I_UI_BACK_RED))
page_collective_missions.connect(page_shirin, GlobalGameAssets.I_UI_BACK_RED, key="page_collective_missions->page_shirin")
page_shirin.connect(page_collective_missions, CollectiveMissionsAssets.I_CM_CM, key="page_shirin->page_collective_missions")
