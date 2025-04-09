import platform

from loguru import logger
from PyQt6.QtCore import QEvent, QSize, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QFont, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QStatusBar,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDialog,
)

from interview_corvus.config import settings
from interview_corvus.core.hotkey_manager import HotkeyManager
from interview_corvus.core.llm_service import LLMService
from interview_corvus.invisibility.invisibility_manager import InvisibilityManager
from interview_corvus.screenshot.screenshot_manager import ScreenshotManager
from interview_corvus.ui.settings_dialog import SettingsDialog
from interview_corvus.ui.styles import Styles, Theme


class MainWindow(QMainWindow):
    """
    Main application window with unified interface.
    Handles user interactions and coordinates between components.
    """

    def __init__(
        self, invisibility_manager: InvisibilityManager, hotkey_manager: HotkeyManager
    ):
        """
        Initialize the main window.

        Args:
            invisibility_manager: Manager for invisibility features
            hotkey_manager: Manager for hotkey handling
        """
        super().__init__()

        self.invisibility_manager = invisibility_manager
        self.hotkey_manager = hotkey_manager
        self.check_and_request_permissions()

        # Initialize other components
        self.screenshot_manager = ScreenshotManager()
        self.llm_service = LLMService()
        self.styles = Styles()

        # Connect LLM service signals
        self.llm_service.completion_finished.connect(self.on_solution_ready)
        self.llm_service.error_occurred.connect(self.on_processing_error)

        # Processing state
        self.processing_screenshot = False
        self.solution_text = ""

        # Set up UI
        self.init_ui()

        # Connect signals to slots
        self.connect_signals()

        # Set window properties
        self.setWindowTitle(settings.app_name)
        self.resize(800, 600)  # Larger default size for unified interface

        # Initialize opacity
        self.set_opacity(settings.ui.default_window_opacity)

        # Set always on top flag
        self.set_always_on_top(settings.ui.always_on_top)

        # Set this window handle for the invisibility manager
        self.invisibility_manager.set_window_handle(self)
        logger.info(
            f"Window visibility at startup: {self.invisibility_manager.is_visible}"
        )

        # Register hotkeys now that the window is created
        self.hotkey_manager.register_hotkeys(self)
        self.installEventFilter(self.hotkey_manager)

    def init_ui(self):
        """Set up the user interface."""
        # Set stylesheet
        self.setStyleSheet(self.styles.get_stylesheet())

        # Create central widget and layout
        central_widget = QWidget()
        main_layout = QVBoxLayout()

        # Header with controls
        header_layout = QHBoxLayout()

        # Title label
        title_label = QLabel(settings.app_name)
        title_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        header_layout.addWidget(title_label)

        # Language selection
        language_layout = QHBoxLayout()
        language_layout.addWidget(QLabel("Language:"))

        self.language_combo = QComboBox()
        self.language_combo.addItems(settings.available_languages)
        index = self.language_combo.findText(settings.default_language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        language_layout.addWidget(self.language_combo)

        header_layout.addLayout(language_layout)

        # Add settings button
        settings_button = QPushButton("Settings")
        settings_button.clicked.connect(self.show_settings)
        header_layout.addWidget(settings_button)

        # Spacer to push visibility controls to the right
        header_layout.addStretch()

        # Always on top checkbox
        self.always_on_top_checkbox = QCheckBox("Always on Top")
        self.always_on_top_checkbox.setChecked(settings.ui.always_on_top)
        self.always_on_top_checkbox.stateChanged.connect(self.toggle_always_on_top)
        header_layout.addWidget(self.always_on_top_checkbox)

        screen_selection_group = QWidget()
        screen_selection_layout = QVBoxLayout(screen_selection_group)
        screen_selection_layout.setContentsMargins(0, 0, 0, 0)

        screen_header = QHBoxLayout()
        screen_header.addWidget(QLabel("Выберите монитор для скриншота:"))
        screen_selection_layout.addLayout(screen_header)

        # Выпадающий список мониторов
        self.screen_combo = QComboBox()
        self.update_screen_list()  # Метод для обновления списка доступных мониторов
        screen_selection_layout.addWidget(self.screen_combo)

        main_layout.addWidget(screen_selection_group)
        # Visibility indicator
        self.visibility_indicator = QLabel("Visible")
        header_layout.addWidget(self.visibility_indicator)

        # Visibility toggle button
        self.visibility_button = QPushButton("Hide")
        self.visibility_button.clicked.connect(self.toggle_visibility)
        self.visibility_button.setToolTip(
            f"Shortcut: {settings.hotkeys.toggle_visibility_key}"
        )
        header_layout.addWidget(self.visibility_button)

        # Add header to main layout
        main_layout.addLayout(header_layout)

        # Opacity slider
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Opacity:"))

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(int(settings.ui.default_window_opacity * 100))
        self.opacity_slider.valueChanged.connect(self.opacity_changed)
        opacity_layout.addWidget(self.opacity_slider)

        main_layout.addLayout(opacity_layout)

        # Screenshot thumbnails section
        screenshots_group = QWidget()
        screenshots_layout = QVBoxLayout(screenshots_group)
        screenshots_layout.setContentsMargins(0, 0, 0, 0)

        screenshots_header = QHBoxLayout()
        screenshots_header.addWidget(QLabel("Recent Screenshots:"))

        # Clear screenshots button
        clear_screenshots_button = QPushButton("Clear Screenshots")
        clear_screenshots_button.clicked.connect(self.clear_screenshots)
        screenshots_header.addWidget(clear_screenshots_button)

        screenshots_layout.addLayout(screenshots_header)

        # Thumbnails scroll area
        self.thumbnails_container = QWidget()
        self.thumbnails_layout = QHBoxLayout(self.thumbnails_container)
        self.thumbnails_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.thumbnails_layout.setContentsMargins(0, 0, 0, 0)
        self.thumbnails_layout.setSpacing(10)

        thumbnails_scroll = QScrollArea()
        thumbnails_scroll.setWidgetResizable(True)
        thumbnails_scroll.setWidget(self.thumbnails_container)
        thumbnails_scroll.setFixedHeight(120)  # Fixed height for thumbnails
        thumbnails_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        thumbnails_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        screenshots_layout.addWidget(thumbnails_scroll)
        main_layout.addWidget(screenshots_group)

        # Control buttons
        controls_layout = QHBoxLayout()

        # Take Screenshot button
        self.screenshot_button = QPushButton(
            f"Take Screenshot ({settings.hotkeys.screenshot_key})"
        )
        self.screenshot_button.clicked.connect(self.take_screenshot)
        self.screenshot_button.setToolTip(
            f"Take a screenshot of your screen - Shortcut: {settings.hotkeys.screenshot_key}"
        )
        controls_layout.addWidget(self.screenshot_button)

        # Generate Solution button
        self.generate_button = QPushButton(
            f"Generate Solution ({settings.hotkeys.generate_solution_key})"
        )
        self.generate_button.clicked.connect(self.generate_solution)
        self.generate_button.setToolTip(
            f"Generate solution from the selected screenshot - Shortcut: {settings.hotkeys.generate_solution_key}"
        )
        controls_layout.addWidget(self.generate_button)

        # Optimize solution button
        self.optimize_button = QPushButton(
            f"Optimize Solution ({settings.hotkeys.optimize_solution_key})"
        )
        self.optimize_button.clicked.connect(self.optimize_solution)
        self.optimize_button.setToolTip(
            f"Optimize the current solution - Shortcut: {settings.hotkeys.optimize_solution_key}"
        )
        controls_layout.addWidget(self.optimize_button)

        # Copy solution button
        self.copy_button = QPushButton("Copy Solution")
        self.copy_button.clicked.connect(self.copy_solution)
        self.copy_button.setToolTip("Copy the solution code to clipboard")
        controls_layout.addWidget(self.copy_button)

        # Reset history button
        self.reset_history_button = QPushButton(
            f"Reset All ({settings.hotkeys.reset_history_key})"
        )
        self.reset_history_button.clicked.connect(self.reset_chat_history)
        self.reset_history_button.setToolTip(
            f"Reset chat history and clear screenshots - Shortcut: {settings.hotkeys.reset_history_key}"
        )
        controls_layout.addWidget(self.reset_history_button)

        main_layout.addLayout(controls_layout)

        # Content splitter - allowing user to adjust size of sections
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Code editor
        self.code_editor = QPlainTextEdit()
        self.code_editor.setReadOnly(True)
        font = QFont("Consolas", 12)
        self.code_editor.setFont(font)
        splitter.addWidget(self.code_editor)

        # Information section
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)

        # Explanation section
        self.explanation_text = QTextEdit()
        self.explanation_text.setReadOnly(True)

        # Set placeholder text
        self.explanation_text.setPlaceholderText(
            "Solution explanation will appear here after generating a solution."
        )

        info_layout.addWidget(QLabel("Explanation:"))
        info_layout.addWidget(self.explanation_text)

        # Complexity section
        complexity_layout = QHBoxLayout()

        # Time complexity
        time_layout = QVBoxLayout()
        time_layout.addWidget(QLabel("Time Complexity:"))
        self.time_complexity = QLabel("N/A")
        time_layout.addWidget(self.time_complexity)
        complexity_layout.addLayout(time_layout)

        # Space complexity
        space_layout = QVBoxLayout()
        space_layout.addWidget(QLabel("Space Complexity:"))
        self.space_complexity = QLabel("N/A")
        space_layout.addWidget(self.space_complexity)
        complexity_layout.addLayout(space_layout)

        info_layout.addLayout(complexity_layout)

        # Add to splitter
        splitter.addWidget(info_widget)

        # Set initial sizes (70% for code, 30% for info)
        splitter.setSizes([700, 300])

        main_layout.addWidget(splitter)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # Progress indicator in status bar for solution generation
        self.progress_label = QLabel("Idle")
        self.status_bar.addPermanentWidget(self.progress_label)

        # Set up main widget
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # Create menu bar
        self._create_menu_bar()

        # Create system tray
        self._create_system_tray()

        # Initialize selected screenshot index
        self.selected_screenshot_index = -1

        # Update thumbnails
        self.update_thumbnails()
        self.update_button_texts()

    def _create_menu_bar(self):
        """Create the application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        take_screenshot_action = QAction(
            f"Take Screenshot ({settings.hotkeys.screenshot_key})", self
        )
        take_screenshot_action.setShortcut(settings.hotkeys.screenshot_key)
        take_screenshot_action.triggered.connect(self.take_screenshot)
        file_menu.addAction(take_screenshot_action)

        # Add action for settings
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.show_settings)
        file_menu.addAction(settings_action)

        generate_solution_action = QAction(
            f"Generate Solution ({settings.hotkeys.generate_solution_key})", self
        )
        generate_solution_action.setShortcut(settings.hotkeys.generate_solution_key)
        generate_solution_action.triggered.connect(self.generate_solution)
        file_menu.addAction(generate_solution_action)

        # Add action for optimizing solution
        optimize_solution_action = QAction(
            f"Optimize Solution ({settings.hotkeys.optimize_solution_key})", self
        )
        optimize_solution_action.setShortcut(settings.hotkeys.optimize_solution_key)
        optimize_solution_action.triggered.connect(self.optimize_solution)
        file_menu.addAction(optimize_solution_action)

        # Add action for resetting chat history
        reset_history_action = QAction(
            f"Reset All ({settings.hotkeys.reset_history_key})", self
        )
        reset_history_action.setShortcut(settings.hotkeys.reset_history_key)
        reset_history_action.triggered.connect(self.reset_chat_history)
        file_menu.addAction(reset_history_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        toggle_visibility_action = QAction(
            f"Toggle Visibility ({settings.hotkeys.toggle_visibility_key})", self
        )
        toggle_visibility_action.setShortcut(settings.hotkeys.toggle_visibility_key)
        toggle_visibility_action.triggered.connect(self.toggle_visibility)
        view_menu.addAction(toggle_visibility_action)

        # Add always on top action
        self.always_on_top_action = QAction("Always on Top", self)
        self.always_on_top_action.setCheckable(True)
        self.always_on_top_action.setChecked(settings.ui.always_on_top)
        self.always_on_top_action.triggered.connect(self.toggle_always_on_top_menu)
        view_menu.addAction(self.always_on_top_action)

        # Theme submenu
        theme_menu = QMenu("Theme", self)

        light_theme_action = QAction("Light", self)
        light_theme_action.triggered.connect(lambda: self.set_theme(Theme.LIGHT.value))
        theme_menu.addAction(light_theme_action)

        dark_theme_action = QAction("Dark", self)
        dark_theme_action.triggered.connect(lambda: self.set_theme(Theme.DARK.value))
        theme_menu.addAction(dark_theme_action)

        view_menu.addMenu(theme_menu)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        shortcuts_action = QAction("&Keyboard Shortcuts", self)
        shortcuts_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(shortcuts_action)

    def _create_system_tray(self):
        """Create the system tray icon and menu."""
        self.tray_icon = QSystemTrayIcon(self)
        # Используем стандартную иконку
        self.tray_icon.setIcon(QIcon.fromTheme("applications-system"))
        self.tray_icon.setToolTip(settings.app_name)
        self.tray_icon.activated.connect(self.on_tray_activated)

        # Создаем контекстное меню для системного трея
        tray_menu = QMenu()
        show_action = tray_menu.addAction("Show/Hide")
        show_action.triggered.connect(self.toggle_visibility)
        optimize_action = tray_menu.addAction("Optimize Solution")
        optimize_action.triggered.connect(self.optimize_solution)

        # Add always on top action to tray menu
        self.tray_always_on_top_action = QAction("Always on Top", self)
        self.tray_always_on_top_action.setCheckable(True)
        self.tray_always_on_top_action.setChecked(settings.ui.always_on_top)
        self.tray_always_on_top_action.triggered.connect(self.toggle_always_on_top_menu)
        tray_menu.addAction(self.tray_always_on_top_action)

        reset_history_action = tray_menu.addAction("Reset All")
        reset_history_action.triggered.connect(self.reset_chat_history)
        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(self.close)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        """
        Handle tray icon activation.

        Args:
            reason: Activation reason
        """
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            logger.info("Tray icon clicked - toggling visibility")
            self.toggle_visibility()

    def connect_signals(self):
        """Connect signals to slots."""
        # Hotkey manager signals
        self.hotkey_manager.screenshot_triggered.connect(self.take_screenshot)
        self.hotkey_manager.solution_triggered.connect(self.generate_solution)
        self.hotkey_manager.visibility_triggered.connect(self.toggle_visibility)
        self.hotkey_manager.move_window_triggered.connect(self.move_window)
        self.hotkey_manager.panic_triggered.connect(self.activate_panic_mode)
        self.hotkey_manager.optimize_solution_triggered.connect(self.optimize_solution)
        self.hotkey_manager.reset_history_triggered.connect(self.reset_chat_history)

        logger.info("Connected all hotkey signals including optimize and reset history")

        # Invisibility manager signals
        self.invisibility_manager.visibility_changed.connect(self.on_visibility_changed)
        self.invisibility_manager.screen_sharing_detected.connect(
            self.on_screen_sharing_detected
        )

        # Language combo box
        self.language_combo.currentTextChanged.connect(self.on_language_changed)
        QApplication.instance().screenAdded.connect(self.update_screen_list)
        QApplication.instance().screenRemoved.connect(self.update_screen_list)

    def set_always_on_top(self, enabled: bool):
        """
        Set whether the window should always be on top.

        Args:
            enabled: True to enable always on top, False to disable
        """
        # Store current flags
        flags = self.windowFlags()

        # Check if we need to make changes
        has_flag = bool(flags & Qt.WindowType.WindowStaysOnTopHint)
        if has_flag == enabled:
            return

        # Clear or set the flag
        if enabled:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint

        # Remember current position and visibility
        pos = self.pos()
        visible = self.isVisible()

        # Apply new flags - this will hide the window
        self.setWindowFlags(flags)

        # Restore position
        self.move(pos)

        # Restore visibility if it was visible
        if visible:
            self.show()

        # Update settings
        settings.ui.always_on_top = enabled
        settings.save_user_settings()

        # Update UI
        self.always_on_top_checkbox.setChecked(enabled)
        self.always_on_top_action.setChecked(enabled)
        self.tray_always_on_top_action.setChecked(enabled)

        logger.info(f"Always on top set to: {enabled}")
        self.status_bar.showMessage(
            f"Always on top: {'enabled' if enabled else 'disabled'}"
        )

    def toggle_always_on_top(self, state):
        """
        Toggle always on top from checkbox.

        Args:
            state: Checkbox state
        """
        self.set_always_on_top(state == Qt.CheckState.Checked)

    def toggle_always_on_top_menu(self):
        """Toggle always on top from menu action."""
        # Use the current state of the action
        self.set_always_on_top(self.always_on_top_action.isChecked())

    def update_thumbnails(self):
        """Update screenshot thumbnails display."""
        # Clear existing thumbnails
        while self.thumbnails_layout.count():
            item = self.thumbnails_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Get all screenshots
        screenshots = self.screenshot_manager.get_all_screenshots()

        if not screenshots:
            # Add placeholder
            placeholder = QLabel("No screenshots available. Take a screenshot first.")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.thumbnails_layout.addWidget(placeholder)
            self.selected_screenshot_index = -1
            return

        # Add thumbnails for each screenshot
        for i, screenshot in enumerate(screenshots):
            thumbnail_widget = QWidget()
            thumbnail_layout = QVBoxLayout(thumbnail_widget)
            thumbnail_layout.setContentsMargins(5, 5, 5, 5)

            # Create thumbnail label
            thumbnail = QLabel()
            pixmap = screenshot["pixmap"].scaled(
                QSize(100, 80),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumbnail.setPixmap(pixmap)
            thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Add border for selected screenshot
            if i == self.selected_screenshot_index:
                thumbnail.setStyleSheet(
                    "border: 3px solid #4CAF50;"
                )  # Green border for selected
            else:
                thumbnail.setStyleSheet("border: 1px solid gray;")

            thumbnail_layout.addWidget(thumbnail)

            # Add timestamp label
            timestamp_label = QLabel(f"Screenshot {i + 1}")
            timestamp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumbnail_layout.addWidget(timestamp_label)

            # Make widget clickable
            thumbnail_widget.mouseReleaseEvent = (
                lambda event, idx=i: self.select_screenshot(idx)
            )
            thumbnail_widget.setCursor(Qt.CursorShape.PointingHandCursor)

            # Add to container
            self.thumbnails_layout.addWidget(thumbnail_widget)

        # If no screenshot is selected, select the most recent one
        if self.selected_screenshot_index == -1 and screenshots:
            self.select_screenshot(len(screenshots) - 1)

    def select_screenshot(self, index):
        """
        Select a screenshot by index.

        Args:
            index: Index of the screenshot to select
        """
        if index < 0 or index >= len(self.screenshot_manager.get_all_screenshots()):
            return

        self.selected_screenshot_index = index
        logger.info(f"Selected screenshot {index}")
        self.status_bar.showMessage(f"Selected screenshot {index + 1}")

        # Update thumbnails to show selection
        self.update_thumbnails()

    def clear_screenshots(self):
        """Clear all screenshots."""
        self.screenshot_manager.clear_screenshots()
        self.selected_screenshot_index = -1
        self.update_thumbnails()
        self.status_bar.showMessage("All screenshots cleared")

    @pyqtSlot(str)
    def on_language_changed(self, language: str):
        """
        Handle language selection changes.

        Args:
            language: The newly selected programming language
        """
        # Update default language in settings
        settings.default_language = language
        self.status_bar.showMessage(f"Solution language set to {language}")

        # Save settings
        settings.save_user_settings()

    @pyqtSlot()
    def take_screenshot(self):
        """Take a screenshot without generating a solution."""
        self.status_bar.showMessage("Taking screenshot...")
        logger.info("Taking screenshot...")

        # Get the index of the selected monitor
        selected_index = self.screen_combo.currentData()

        # Save the currently active window handle before taking screenshot
        # This can be done with platform-specific code

        # Temporarily hide the window if visible
        was_visible = self.invisibility_manager.is_visible
        self.invisibility_manager.set_visibility(False)
        QApplication.processEvents()

        # Take the screenshot
        screenshot = self.screenshot_manager.take_screenshot(selected_index)

        # Restore visibility if needed, but don't activate the window
        if was_visible:
            QTimer.singleShot(
                200,
                lambda: self.invisibility_manager.restore_visibility_without_focus(),
            )

        # Update UI elements
        self.status_bar.showMessage(
            f"Screenshot captured: {screenshot['width']}x{screenshot['height']}"
        )
        self.update_thumbnails()
        self.select_screenshot(len(self.screenshot_manager.get_all_screenshots()) - 1)

    @pyqtSlot()
    def reset_chat_history(self):
        """Reset the chat history and clear screenshots."""
        if hasattr(self.llm_service, "reset_chat_history"):
            self.llm_service.reset_chat_history()

            # Clear all screenshots
            self.screenshot_manager.clear_screenshots()
            self.selected_screenshot_index = -1
            self.update_thumbnails()

            # Clear UI components
            self.code_editor.clear()
            self.explanation_text.clear()
            self.time_complexity.setText("N/A")
            self.space_complexity.setText("N/A")

            self.status_bar.showMessage("Chat history and screenshots reset.")
            logger.info("Chat history and screenshots have been reset")
        else:
            self.status_bar.showMessage("Chat history reset not implemented.")
            logger.info("Chat history reset not implemented")

    @pyqtSlot()
    def generate_solution(self):
        """Generate a solution based on all available screenshots."""
        # Check if processing is already in progress
        if self.processing_screenshot:
            self.status_bar.showMessage("Already processing screenshot, please wait...")
            return

        # Get all screenshots
        screenshots = self.screenshot_manager.get_all_screenshots()
        if not screenshots:
            self.status_bar.showMessage(
                "No screenshots available. Take a screenshot first."
            )
            logger.info("No screenshots available")
            return

        self.status_bar.showMessage(
            f"Generating solution from {len(screenshots)} screenshots..."
        )
        logger.info(f"Generating solution from {len(screenshots)} screenshots...")

        # Set processing flag
        self.processing_screenshot = True
        self.generate_button.setEnabled(False)
        self.optimize_button.setEnabled(False)
        self.progress_label.setText("Generating solution...")

        # Clear previous solution
        self.solution_text = ""
        self.code_editor.clear()

        # Get the selected language
        selected_language = self.language_combo.currentText()
        logger.info(f"Using language: {selected_language}")

        # Get all screenshot paths
        screenshot_paths = [screenshot["file_path"] for screenshot in screenshots]

        class ScreenshotProcessingThread(QThread):
            solution_ready = pyqtSignal(object)
            error_occurred = pyqtSignal(str)

            def __init__(self, llm_service, screenshot_paths, language):
                super().__init__()
                self.llm_service = llm_service
                self.screenshot_paths = screenshot_paths
                self.language = language

            def run(self):
                try:
                    logger.info(
                        f"Processing {len(self.screenshot_paths)} screenshots in thread"
                    )
                    solution = self.llm_service.get_solution_from_screenshots(
                        self.screenshot_paths, self.language
                    )
                    self.solution_ready.emit(solution)
                except Exception as e:
                    err_message = str(e)
                    logger.info(f"Error in processing thread: {e}")
                    if 'NoneType' in err_message:
                        err_message += '\nTip: check your VPN'
                    self.error_occurred.emit(err_message)

        # Create and start the thread
        self.processing_thread = ScreenshotProcessingThread(
            self.llm_service, screenshot_paths, selected_language
        )

        self.processing_thread.solution_ready.connect(self.on_solution_ready)
        self.processing_thread.error_occurred.connect(self.on_processing_error)
        self.processing_thread.start()

    @pyqtSlot()
    def optimize_solution(self):
        """Optimize the current solution."""
        # Check if there's a solution to optimize
        current_code = self.code_editor.toPlainText()
        if not current_code.strip():
            self.status_bar.showMessage(
                "No solution to optimize. Generate a solution first."
            )
            logger.info("No code to optimize")
            return

        # Check if processing is already in progress
        if self.processing_screenshot:
            self.status_bar.showMessage("Already processing request, please wait...")
            return

        self.status_bar.showMessage("Optimizing solution...")
        logger.info("Optimizing solution...")

        # Set processing flag
        self.processing_screenshot = True
        self.generate_button.setEnabled(False)
        self.optimize_button.setEnabled(False)
        self.progress_label.setText("Optimizing solution...")

        # Save original code and explanation for comparison
        self.original_code = current_code
        self.original_explanation = self.explanation_text.toPlainText()
        self.original_time_complexity = self.time_complexity.text()
        self.original_space_complexity = self.space_complexity.text()

        # Reset solution text
        self.solution_text = ""

        # Get the selected language
        selected_language = self.language_combo.currentText()
        logger.info(f"Using language: {selected_language} for optimization")

        class OptimizationThread(QThread):
            solution_ready = pyqtSignal(object)
            error_occurred = pyqtSignal(str)

            def __init__(self, llm_service, code, language):
                super().__init__()
                self.llm_service = llm_service
                self.code = code
                self.language = language

            def run(self):
                try:
                    logger.info("Optimizing code in thread")
                    solution = self.llm_service.get_code_optimization(
                        self.code, self.language
                    )
                    self.solution_ready.emit(solution)
                except Exception as e:
                    logger.info(f"Error in optimization thread: {e}")
                    self.error_occurred.emit(str(e))

        # Create and start the thread
        self.optimization_thread = OptimizationThread(
            self.llm_service, current_code, selected_language
        )

        self.optimization_thread.solution_ready.connect(self.on_optimization_ready)
        self.optimization_thread.error_occurred.connect(self.on_processing_error)
        self.optimization_thread.start()

    def update_screen_list(self):
        """Обновить список доступных мониторов в выпадающем списке."""
        self.screen_combo.clear()

        screens = self.screenshot_manager.get_available_screens()
        for screen in screens:
            display_name = f"{screen['name']} ({screen['width']}x{screen['height']})"
            if screen["primary"]:
                display_name += " (Основной)"
            self.screen_combo.addItem(display_name, screen["index"])

    @pyqtSlot(object)
    def on_solution_ready(self, solution):
        """
        Handle completed solution from LLM.

        Args:
            solution: The completed solution object
        """
        # Reset processing flag
        self.processing_screenshot = False
        self.generate_button.setEnabled(True)
        self.optimize_button.setEnabled(True)
        self.progress_label.setText("Idle")

        # Update UI with solution
        self.code_editor.setPlainText(solution.code)
        self.explanation_text.setText(solution.explanation)
        self.time_complexity.setText(solution.time_complexity)
        self.space_complexity.setText(solution.space_complexity)

        self.status_bar.showMessage("Solution generated")
        logger.info("Solution generated successfully")

    @pyqtSlot(object)
    def on_optimization_ready(self, optimization):
        """
        Handle completed optimization from LLM.

        Args:
            optimization: The completed optimization object
        """
        # Reset processing flag
        self.processing_screenshot = False
        self.generate_button.setEnabled(True)
        self.optimize_button.setEnabled(True)
        self.progress_label.setText("Idle")

        # Update UI with optimized solution
        self.code_editor.setPlainText(optimization.optimized_code)

        # Create a detailed explanation that includes the improvements
        detailed_explanation = "## Optimization Details\n\n"
        detailed_explanation += optimization.explanation + "\n\n"
        detailed_explanation += "## Improvements\n\n"
        for improvement in optimization.improvements:
            detailed_explanation += f"- {improvement}\n"
        detailed_explanation += "\n\n## Time Complexity\n\n"
        detailed_explanation += f"Original: {optimization.original_time_complexity}\n"
        detailed_explanation += (
            f"Optimized: {optimization.optimized_time_complexity}\n\n"
        )
        detailed_explanation += "## Space Complexity\n\n"
        detailed_explanation += f"Original: {optimization.original_space_complexity}\n"
        detailed_explanation += (
            f"Optimized: {optimization.optimized_space_complexity}\n"
        )

        self.explanation_text.setText(detailed_explanation)
        self.time_complexity.setText(optimization.optimized_time_complexity)
        self.space_complexity.setText(optimization.optimized_space_complexity)

        self.status_bar.showMessage("Solution optimized")
        logger.info("Solution optimized successfully")

    @pyqtSlot(str)
    def on_processing_error(self, error_message):
        """
        Handle errors during screenshot processing.

        Args:
            error_message: The error message
        """
        # Reset processing flag
        self.processing_screenshot = False
        self.generate_button.setEnabled(True)
        self.optimize_button.setEnabled(True)
        self.progress_label.setText("Error")

        # Display error message
        self.status_bar.showMessage(f"Error processing request: {error_message}")
        logger.info(f"Error processing request: {error_message}")
        QMessageBox.critical(
            self, "Error", f"Failed to process request: {error_message}"
        )

    def copy_solution(self):
        """Copy the solution code to clipboard."""
        from PyQt6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        clipboard.setText(self.code_editor.toPlainText())
        self.status_bar.showMessage("Solution copied to clipboard")
        logger.info("Solution copied to clipboard")

    @pyqtSlot()
    def toggle_visibility(self):
        """Toggle the visibility of the application window."""
        logger.info(
            f"Toggle visibility called, current state: {self.invisibility_manager.is_visible}"
        )
        new_state = self.invisibility_manager.toggle_visibility()
        logger.info(f"Toggled visibility, new state: {new_state}")
        self.on_visibility_changed(new_state)

    @pyqtSlot(bool)
    def on_visibility_changed(self, is_visible: bool):
        """
        Handle visibility state changes.

        Args:
            is_visible: The new visibility state
        """
        if is_visible:
            self.visibility_indicator.setText("Visible")
            self.visibility_button.setText("Hide")
        else:
            self.visibility_indicator.setText("Hidden")
            self.visibility_button.setText("Show")

        self.status_bar.showMessage(
            f"Visibility set to {'visible' if is_visible else 'hidden'}"
        )
        logger.info(f"Visibility changed to: {is_visible}")

    @pyqtSlot(bool)
    def on_screen_sharing_detected(self, is_sharing: bool):
        """
        Handle screen sharing detection.

        Args:
            is_sharing: True if screen sharing was detected, False otherwise
        """
        if is_sharing:
            self.status_bar.showMessage(
                "Screen sharing detected! Window hidden automatically."
            )
            logger.info("Screen sharing detected, hiding window")
            # The invisibility manager should automatically hide the window
        else:
            self.status_bar.showMessage("Screen sharing ended.")
            logger.info("Screen sharing ended")

    @pyqtSlot(str)
    def move_window(self, direction: str):
        """
        Move the window in the specified direction.

        Args:
            direction: Direction to move ("up", "down", "left", "right")
        """
        # Fixed direct implementation to ensure window movement works
        distance = 60  # pixels to move
        current_pos = self.pos()
        new_x, new_y = current_pos.x(), current_pos.y()

        if direction == "up":
            new_y -= distance
        elif direction == "down":
            new_y += distance
        elif direction == "left":
            new_x -= distance
        elif direction == "right":
            new_x += distance

        # Direct window movement
        self.move(new_x, new_y)
        logger.info(f"Window moved {direction} to position ({new_x}, {new_y})")
        self.status_bar.showMessage(
            f"Window moved {direction} to position ({new_x}, {new_y})"
        )

    @pyqtSlot()
    def activate_panic_mode(self):
        """Activate panic mode to quickly hide the application."""
        logger.info("Panic mode activated!")
        self.invisibility_manager.set_visibility(False)
        self.status_bar.showMessage("Panic mode activated!")

    @pyqtSlot(int)
    def opacity_changed(self, value: int):
        """
        Handle opacity slider changes.

        Args:
            value: Opacity value from 10-100
        """
        opacity = value / 100.0
        self.set_opacity(opacity)

    def set_opacity(self, opacity: float):
        """
        Set the window opacity.

        Args:
            opacity: Opacity value from 0.0 to 1.0
        """
        # Set window opacity
        self.setWindowOpacity(opacity)
        logger.info(f"Window opacity set to {opacity}")

    def set_theme(self, theme_name: str):
        """
        Set the application theme.

        Args:
            theme_name: Name of the theme ("light" or "dark")
        """
        self.styles.set_theme(theme_name)

        # Update the application stylesheet
        self.setStyleSheet(self.styles.get_stylesheet())

        self.status_bar.showMessage(f"Theme changed to {theme_name}")
        logger.info(f"Theme changed to {theme_name}")

    def show_about(self):
        """Show the about dialog."""
        QMessageBox.about(
            self,
            "About Interview Corvus",
            f"""
            <h1>Interview Corvus</h1>
            <p>Version: {__import__("interview_corvus").__version__}</p>
            <p>An invisible AI assistant for technical interviews.</p>
            <p>This application helps users solve programming problems during technical interviews 
            by providing real-time solutions while remaining invisible during screen sharing.</p>
            <p>&copy; 2023 Your Company</p>
            """,
        )

    def show_shortcuts(self):
        """Show the keyboard shortcuts dialog."""
        shortcuts = f"""
        <h2>Keyboard Shortcuts</h2>
        <ul>
            <li><b>{settings.hotkeys.screenshot_key}</b>: Take Screenshot</li>
            <li><b>{settings.hotkeys.generate_solution_key}</b>: Generate Solution</li>
            <li><b>{settings.hotkeys.optimize_solution_key}</b>: Optimize Solution</li>
            <li><b>{settings.hotkeys.toggle_visibility_key}</b>: Toggle Visibility</li>
            <li><b>{settings.hotkeys.reset_history_key}</b>: Reset Chat History and Screenshots</li>
            <li><b>{settings.hotkeys.move_window_keys["up"]}</b>: Move Window Up</li>
            <li><b>{settings.hotkeys.move_window_keys["down"]}</b>: Move Window Down</li>
            <li><b>{settings.hotkeys.move_window_keys["left"]}</b>: Move Window Left</li>
            <li><b>{settings.hotkeys.move_window_keys["right"]}</b>: Move Window Right</li>
            <li><b>{settings.hotkeys.panic_key}</b>: Panic Mode (Instant Hide)</li>
        </ul>
        """

        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts)

    def show_settings(self):
        """Show the settings dialog."""
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Update services that depend on settings
            self.llm_service = LLMService()

            # Reconnect signals
            self.llm_service.completion_finished.connect(self.on_solution_ready)
            self.llm_service.error_occurred.connect(self.on_processing_error)

            # Update UI to reflect new settings
            index = self.language_combo.findText(settings.default_language)
            if index >= 0:
                self.language_combo.setCurrentIndex(index)

            # Update always on top setting
            self.set_always_on_top(settings.ui.always_on_top)

            # Update button texts with new hotkey settings
            self.update_button_texts()

            # Re-register hotkeys with the hotkey manager
            self.hotkey_manager.register_hotkeys(self)

            self.status_bar.showMessage("Settings updated")
            logger.info("Settings updated")

    def closeEvent(self, event):
        """
        Handle window close event.

        Args:
            event: Close event
        """
        if hasattr(self, "hotkey_manager"):
            self.hotkey_manager.stop_global_listener()

        event.accept()

        logger.info("Application closed")

        QApplication.quit()

    def changeEvent(self, event):
        """
        Handle window state changes for proper hotkey operation.
        """
        if event.type() == QEvent.Type.WindowStateChange:
            # Re-register hotkeys when minimizing/restoring
            self.hotkey_manager.register_hotkeys(self)
            logger.info("Re-registered hotkeys after window state change")

        super().changeEvent(event)

    def keyPressEvent(self, event):
        """
        Additional key press event handling.
        """
        # Отладочная информация о нажатых клавишах
        logger.info(f"Key pressed: {event.key()}, modifiers: {event.modifiers()}")

        # Standard key press handling
        super().keyPressEvent(event)

    def update_button_texts(self):
        """Update button texts to reflect current hotkey settings."""
        self.screenshot_button.setText(
            f"Take Screenshot ({settings.hotkeys.screenshot_key})"
        )
        self.generate_button.setText(
            f"Generate Solution ({settings.hotkeys.generate_solution_key})"
        )
        self.optimize_button.setText(
            f"Optimize Solution ({settings.hotkeys.optimize_solution_key})"
        )
        self.reset_history_button.setText(
            f"Reset All ({settings.hotkeys.reset_history_key})"
        )

        # Update visibility button tooltip
        self.visibility_button.setToolTip(
            f"Shortcut: {settings.hotkeys.toggle_visibility_key}"
        )

        # Update button tooltips
        self.screenshot_button.setToolTip(
            f"Take a screenshot of your screen - Shortcut: {settings.hotkeys.screenshot_key}"
        )
        self.generate_button.setToolTip(
            f"Generate solution from the selected screenshot - Shortcut: {settings.hotkeys.generate_solution_key}"
        )
        self.optimize_button.setToolTip(
            f"Optimize the current solution - Shortcut: {settings.hotkeys.optimize_solution_key}"
        )
        self.reset_history_button.setToolTip(
            f"Reset chat history and clear screenshots - Shortcut: {settings.hotkeys.reset_history_key}"
        )

        # Also update menu actions if they exist
        if hasattr(self, "take_screenshot_action"):
            self.take_screenshot_action.setText(
                f"Take Screenshot ({settings.hotkeys.screenshot_key})"
            )
            self.take_screenshot_action.setShortcut(
                QKeySequence(settings.hotkeys.screenshot_key)
            )

        if hasattr(self, "generate_solution_action"):
            self.generate_solution_action.setText(
                f"Generate Solution ({settings.hotkeys.generate_solution_key})"
            )
            self.generate_solution_action.setShortcut(
                QKeySequence(settings.hotkeys.generate_solution_key)
            )

        if hasattr(self, "toggle_visibility_action"):
            self.toggle_visibility_action.setText(
                f"Toggle Visibility ({settings.hotkeys.toggle_visibility_key})"
            )
            self.toggle_visibility_action.setShortcut(
                QKeySequence(settings.hotkeys.toggle_visibility_key)
            )

        if hasattr(self, "optimize_solution_action"):
            self.optimize_solution_action.setText(
                f"Optimize Solution ({settings.hotkeys.optimize_solution_key})"
            )
            self.optimize_solution_action.setShortcut(
                QKeySequence(settings.hotkeys.optimize_solution_key)
            )

        if hasattr(self, "reset_history_action"):
            self.reset_history_action.setText(
                f"Reset All ({settings.hotkeys.reset_history_key})"
            )
            self.reset_history_action.setShortcut(
                QKeySequence(settings.hotkeys.reset_history_key)
            )

    def check_and_request_permissions(self):
        """Check for and request required permissions for global hotkey monitoring."""
        if platform.system() == "Darwin":
            import Cocoa
            import HIServices
            try:
                # Check if we have accessibility permissions
                trusted = HIServices.AXIsProcessTrusted()
                logger.info(f"Application accessibility permissions status: {trusted}")

                if not trusted:
                    # Show dialog explaining why we need permissions
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Icon.Information)
                    msg.setWindowTitle("Permissions Required")
                    msg.setText(
                        "Interview Corvus needs Accessibility permissions to use global hotkeys."
                    )
                    msg.setInformativeText(
                        "You'll need to enable Interview Corvus in System Preferences → Security & Privacy → Privacy → Accessibility."
                    )
                    msg.setDetailedText(
                        "Without these permissions, global hotkeys (like taking screenshots or toggling visibility) won't work outside the application window."
                    )

                    # Add button to open System Preferences
                    open_prefs_btn = msg.addButton(
                        "Open System Preferences", QMessageBox.ButtonRole.ActionRole
                    )
                    msg.addButton("Later", QMessageBox.ButtonRole.RejectRole)

                    msg.exec()

                    # If user clicked the button to open System Preferences
                    if msg.clickedButton() == open_prefs_btn:
                        # Open System Preferences at the Accessibility pane
                        Cocoa.NSWorkspace.sharedWorkspace().openURL_(
                            Cocoa.NSURL.URLWithString_(
                                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
                            )
                        )
            except Exception as e:
                logger.error(f"Error checking accessibility permissions: {e}")
