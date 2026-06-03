from tasks.GameUi.page import page_shikigami_records, page_realm_raid
from tasks.GlobalGame.assets import GlobalGameAssets

page_shikigami_records.connect(page_realm_raid, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_shikigami_records->page_realm_raid", cost=2)
