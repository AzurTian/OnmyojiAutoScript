from tasks.Chess.assets import ChessAssets
from tasks.GameUi.assets import GameUiAssets
from tasks.GameUi.default_pages import page_entertainment, random_click
from tasks.GameUi.page_definition import Page
from tasks.GlobalGame.assets import GlobalGameAssets

page_chess = Page(ChessAssets.I_CHECK_CHESS, category="global")
page_chess.add_enter_failure_hooks(ChessAssets.I_SKIP)
page_entertainment.connect(page_chess, ChessAssets.I_ENTERTAINMENT_GOTO_CHESS, key="page_entertainment->page_chess")
page_chess.connect(page_entertainment, GlobalGameAssets.I_UI_BACK_YELLOW, key="page_chess->page_entertainment")