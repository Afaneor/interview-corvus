"""Main entry point for the Interview Corvus application."""

import atexit
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from interview_corvus.config import settings
from interview_corvus.core.hotkey_manager import HotkeyManager
from interview_corvus.invisibility.invisibility_manager import InvisibilityManager
from interview_corvus.ui.main_window import MainWindow


def setup_environment():
    """Set up the application environment."""
    # Create application data directory if it doesn't exist
    os.makedirs(settings.app_data_dir, exist_ok=True)

    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


def main():
    """Main entry point for the application."""
    # Set up environment
    setup_environment()

    # Create the application
    app = QApplication(sys.argv)
    app.setApplicationName(settings.app_name)
    app.setApplicationVersion(__import__("interview_corvus").__version__)

    # Initialize managers
    invisibility_manager = InvisibilityManager()
    hotkey_manager = HotkeyManager()

    # Create and show the main window
    window = MainWindow(invisibility_manager, hotkey_manager)

    # Регистрируем функцию очистки при выходе из приложения
    atexit.register(hotkey_manager.stop_global_listener)

    # Устанавливаем фильтр событий на уровне приложения для локальных шорткатов
    app.installEventFilter(hotkey_manager)

    # Показываем окно
    window.show()

    # Apply screen reader protection if on macOS
    import platform
    if platform.system() == "Darwin":
        invisibility_manager.set_screen_reader_protection(True)

    # Start the application event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
