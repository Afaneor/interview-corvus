"""Manager for invisibility features during screen sharing."""

import platform
from typing import Tuple

from loguru import logger
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, Qt


class InvisibilityManager(QObject):
    """
    Manages the invisibility features of the application during screen sharing.

    Signals:
        visibility_changed: Emitted when the visibility state changes
        screen_sharing_detected: Emitted when screen sharing is detected
    """

    visibility_changed = pyqtSignal(bool)
    screen_sharing_detected = pyqtSignal(bool)

    def __init__(self):
        """Initialize the invisibility manager."""
        super().__init__()

        self.is_visible = True
        self.is_screen_sharing_active = False
        self.window_handle = None

        # Для macOS: создаем крошечное невидимое окно, чтобы приложение оставалось активным
        self.is_macos = platform.system() == "Darwin"
        self.helper_window = None

    def set_window_handle(self, window_handle):
        """
        Set the window handle for this invisibility manager.

        Args:
            window_handle: The window handle (QWidget) to control
        """
        self.window_handle = window_handle

        # На macOS, создаем вспомогательное крошечное вспомогательное окно
        if self.is_macos:
            # Если мы на macOS, инициализируем вспомогательное окно
            from PyQt6.QtWidgets import QWidget

            self.helper_window = QWidget()
            self.helper_window.setWindowTitle("Helper")
            self.helper_window.resize(1, 1)  # Крошечный размер
            self.helper_window.setWindowOpacity(0.0)  # Полностью прозрачное

            # Размещаем за пределами экрана
            self.helper_window.move(-10000, -10000)
            self.helper_window.show()

            logger.info("Created helper window for macOS hotkey handling")

        # Start monitoring for screen sharing after window handle is set
        self._start_monitoring()

    def _start_monitoring(self):
        """Start monitoring for screen sharing activity."""
        # Ensure we have a window handle before starting monitoring
        if not self.window_handle:
            logger.info("Warning: Cannot start monitoring without window handle")
            return

        # In real implementation, would monitor screen sharing
        # For now, just assume no screen sharing is happening
        self._on_screen_sharing_change(False)

    def _on_screen_sharing_change(self, is_active: bool):
        """
        Callback for when screen sharing state changes.

        Args:
            is_active: True if screen sharing is active, False otherwise
        """
        if is_active != self.is_screen_sharing_active:
            self.is_screen_sharing_active = is_active
            self.screen_sharing_detected.emit(is_active)

            # If screen sharing becomes active and we're visible,
            # automatically hide the window
            if is_active and self.is_visible:
                self.set_visibility(False)

    def toggle_visibility(self) -> bool:
        """
        Toggle the visibility state of the application.

        Returns:
            The new visibility state (True for visible, False for invisible)
        """
        logger.info(f"Toggle visibility called, current state: {self.is_visible}")
        return self.set_visibility(not self.is_visible)

    def set_visibility(self, visible: bool) -> bool:
        """
        Set the visibility state of the application.

        Args:
            visible: True to make visible, False to make invisible

        Returns:
            The new visibility state
        """
        logger.info(
            f"Setting visibility to {visible}, current state: {self.is_visible}"
        )

        # Skip if state is already correct
        if visible == self.is_visible:
            logger.info(f"Visibility already set to {visible}, returning")
            return self.is_visible

        # Ensure we have a window handle
        if not self.window_handle:
            logger.info("Warning: Cannot set visibility without window handle")
            return self.is_visible

        # Update the internal state
        self.is_visible = visible

        if visible:
            self._show_window()
        else:
            self._hide_window()

        # Emit signal
        self.visibility_changed.emit(visible)
        logger.info(f"Visibility changed to {visible}")

        return self.is_visible

    def _show_window(self):
        """Show and activate the window with platform-specific handling."""
        logger.info("Making window visible")

        if self.is_macos:
            # macOS requires special handling for reliable window activation
            self.window_handle.setHidden(False)
            self.window_handle.show()
            self.window_handle.raise_()

            # Schedule multiple activation attempts with increasing delays
            # This improves reliability on macOS which can be inconsistent
            QTimer.singleShot(50, lambda: self._macos_activate_window(1))
        else:
            # Standard window showing for other platforms
            self.window_handle.show()
            self.window_handle.raise_()
            self.window_handle.activateWindow()

    def set_screen_reader_protection(self, enabled: bool):
        """
        Set the screen reader protection for the window (macOS only).

        Args:
            enabled: True to enable protection, False to disable
        """
        if not self.is_macos or not self.window_handle:
            return

        try:
            from AppKit import NSWindow, NSWindowSharingType

            native_handle = self.window_handle.winId()
            window = NSWindow.alloc().initWithWindowRef_(native_handle)

            if enabled:
                window.setSharingType_(NSWindowSharingType.NSWindowSharingNone)
                logger.info("Screen reader protection enabled for macOS.")
            else:
                window.setSharingType_(NSWindowSharingType.NSWindowSharingReadOnly)
                logger.info("Screen reader protection disabled for macOS.")

        except ImportError:
            logger.error("Failed to import AppKit for macOS screen reader protection.")
        except Exception as e:
            logger.error(f"Error setting macOS screen reader protection: {e}")

    def set_screen_reader_protection(self, enabled: bool):
        """
        Set the screen reader protection for the window.

        Args:
            enabled: True to enable protection, False to disable
        """
        if not self.window_handle:
            return

        if self.is_macos:
            try:
                from AppKit import NSWindow, NSWindowSharingType

                native_handle = self.window_handle.winId()
                window = NSWindow.alloc().initWithWindowRef_(native_handle)

                if enabled:
                    window.setSharingType_(NSWindowSharingType.NSWindowSharingNone)
                    logger.info("Screen reader protection enabled for macOS.")
                else:
                    window.setSharingType_(NSWindowSharingType.NSWindowSharingReadOnly)
                    logger.info("Screen reader protection disabled for macOS.")

            except ImportError:
                logger.error("Failed to import AppKit for macOS screen reader protection.")
            except Exception as e:
                logger.error(f"Error setting macOS screen reader protection: {e}")
        else:
            try:
                import ctypes

                hwnd = self.window_handle.winId()
                if enabled:
                    # WDA_EXCLUDEFROMCAPTURE
                    ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)
                    logger.info("Screen reader protection enabled for Windows.")
                else:
                    # WDA_NONE
                    ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000000)
                    logger.info("Screen reader protection disabled for Windows.")
            except (ImportError, AttributeError):
                logger.error("Failed to set screen reader protection for Windows.")
            except Exception as e:
                logger.error(f"Error setting Windows screen reader protection: {e}")

    def _hide_window(self):
        """Hide the window."""
        logger.info("Hiding window")
        self.window_handle.hide()

    def set_visibility_without_activation(self, visible: bool) -> bool:
        """
        Set visibility without activating the window (doesn't steal focus).

        Args:
            visible: True to make visible, False to make invisible

        Returns:
            The new visibility state
        """
        logger.info(f"Setting visibility without activation to {visible}")

        if visible == self.is_visible:
            return self.is_visible

        if not self.window_handle:
            return self.is_visible

        self.is_visible = visible

        if visible:
            # Show without activating/focusing
            if self.is_macos:
                # macOS-specific way to show without focusing
                self.window_handle.setHidden(False)
                self.window_handle.show()
                # Don't call raise_() or activateWindow()
            else:
                # For Windows/Linux
                flags = self.window_handle.windowFlags()
                self.window_handle.setWindowFlags(
                    flags | Qt.WindowType.WindowDoesNotAcceptFocus
                )
                self.window_handle.show()
                # Restore original flags
                self.window_handle.setWindowFlags(flags)
        else:
            self.window_handle.hide()

        # Emit signal
        self.visibility_changed.emit(visible)

        return self.is_visible

    def restore_visibility_without_focus(self):
        """Restore window visibility without stealing focus from other applications."""
        # Make window visible but don't activate it
        if self.is_macos:
            # Use a new method in InvisibilityManager that doesn't activate the window
            self.set_visibility_without_activation(True)
        else:
            self.window_handle.show()
            self.window_handle.setWindowFlag(
                Qt.WindowType.WindowDoesNotAcceptFocus, False
            )
        self.is_visible = True

    def _macos_activate_window(self, attempt):
        """Многократная попытка активации окна для macOS"""
        if self.window_handle and self.is_visible:
            logger.info(f"Activating window attempt {attempt}")
            self.window_handle.raise_()
            self.window_handle.activateWindow()

            # На macOS этот метод часто дает лучшие результаты
            if hasattr(self.window_handle.windowHandle(), "requestActivate"):
                self.window_handle.windowHandle().requestActivate()

    def move_window(self, direction: str, distance: int = 20) -> Tuple[int, int]:
        """
        Move the window in the specified direction.
        Direct implementation without layers of abstraction.

        Args:
            direction: Direction to move ("up", "down", "left", "right")
            distance: Distance to move in pixels

        Returns:
            New window position as (x, y) coordinates
        """
        # Ensure we have a window handle
        if not self.window_handle:
            logger.info("Warning: Cannot move window without window handle")
            return (0, 0)

        # Get current position directly from window
        current_pos = self.window_handle.pos()
        new_x, new_y = current_pos.x(), current_pos.y()

        # Calculate new position
        if direction == "up":
            new_y -= distance
        elif direction == "down":
            new_y += distance
        elif direction == "left":
            new_x -= distance
        elif direction == "right":
            new_x += distance

        # Direct window move without intermediate functions
        logger.info(
            f"Moving window {direction} from ({current_pos.x()}, {current_pos.y()}) to ({new_x}, {new_y})"
        )
        self.window_handle.move(new_x, new_y)

        return (new_x, new_y)

    def get_panic_behavior(self):
        """
        Get the behavior for panic mode.

        Returns:
            A callable that performs the panic action
        """

        def panic_action():
            """Panic action to immediately hide the window."""
            if self.window_handle:
                self.set_visibility(False)

        return panic_action
