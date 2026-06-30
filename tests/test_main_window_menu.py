from app.ui.main_window import MainWindow


def test_file_menu_has_one_export_action_per_format(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    file_menu = window.menuBar().actions()[0].menu()
    labels = [action.text() for action in file_menu.actions() if not action.isSeparator()]

    assert labels.count("导出 Markdown(&M)...") == 1
    assert labels.count("导出 EPUB(&E)...") == 1
