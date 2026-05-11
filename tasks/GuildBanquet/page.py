from tasks.GameUi.default_pages import page_guild, page_main
from tasks.GameUi.matcher import any_of
from tasks.GameUi.page_definition import Page
from tasks.GlobalGame.assets import GlobalGameAssets
from tasks.GuildBanquet.assets import GuildBanquetAssets

# 宴会式神界面
page_banquet_shikigami = Page(GuildBanquetAssets.I_BANQUET_SWITCH, priority=75)
page_banquet_shikigami.connect(page_guild, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_banquet_shikigami->page_guild")
page_guild.connect(page_banquet_shikigami, GuildBanquetAssets.I_BANQUET_EXP_FULL, key="page_guild->page_banquet_shikigami")

# 宴会切换式神界面
page_banquet_switch_shikigami = Page(any_of(GuildBanquetAssets.I_BANQUET_CONFIRM,
                                            GuildBanquetAssets.I_BANQUET_CLEAR_ALL,
                                            GuildBanquetAssets.I_BANQUET_CLEAR_ALL), priority=75)
page_banquet_switch_shikigami.connect(page_banquet_shikigami, GlobalGameAssets.I_UI_BACK_RED,
                                      key="page_banquet_switch_shikigami->page_banquet_shikigami")
page_banquet_shikigami.connect(page_banquet_switch_shikigami, GuildBanquetAssets.I_BANQUET_SWITCH,
                               key="page_banquet_shikigami->page_banquet_switch_shikigami")

