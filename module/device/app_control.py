from lxml import etree

from module.device.method.adb import Adb
from module.device.method.uiautomator_2 import Uiautomator2
from module.device.method.utils import HierarchyButton
# from module.device.method.wsa import WSA
from module.logger import logger


class AppControl(Adb, Uiautomator2):
    hierarchy: etree._Element
    _app_u2_family = ['uiautomator2', 'minitouch', 'scrcpy']

    def app_is_alive(self, package_name=None) -> bool:
        """
        判断目标应用进程是否仍然存活，不要求当前位于前台。

        这用于区分“应用被切到后台”和“应用已经被真正杀掉”两种情况。
        """
        if getattr(self, 'is_playcover', False):
            return True
        if not package_name:
            package_name = self.package

        try:
            result = self.adb_shell(['pidof', package_name])
        except Exception as e:
            logger.info(f'Check app alive by pidof failed: {e}')
            return False

        result = result.strip(' \t\r\n')
        logger.attr('Package_pid', result if result else 'None')
        return bool(result)

    def app_is_running(self) -> bool:
        if getattr(self, 'is_playcover', False):
            return True
        method = self.config.script.device.control_method
        # if self.is_wsa:
        #     package = self.app_current_wsa()
        if method in AppControl._app_u2_family:
            package = self.app_current_uiautomator2()
        else:
            package = self.app_current_adb()

        package = package.strip(' \t\r\n')
        logger.attr('Package_name', package)
        return package == self.package

    def app_start(self):
        if getattr(self, 'is_playcover', False):
            return
        method = self.config.script.device.screenshot_method
        logger.info(f'App start: {self.package}')
        # if self.config.Emulator_Serial == 'wsa-0':
        #     self.app_start_wsa(display=0)
        if method in AppControl._app_u2_family:
            self.app_start_uiautomator2()
        else:
            self.app_start_adb()

    def app_stop(self):
        if getattr(self, 'is_playcover', False):
            return
        method = self.config.script.device.screenshot_method
        logger.info(f'App stop: {self.package}')
        if method in AppControl._app_u2_family:
            self.app_stop_uiautomator2()
        else:
            self.app_stop_adb()

    def dump_hierarchy(self) -> etree._Element:
        """
        Returns:
            etree._Element: Select elements with `self.hierarchy.xpath('//*[@text="Hermit"]')` for example.
        """
        if getattr(self, 'is_playcover', False):
            self.hierarchy = etree.Element('hierarchy')
            return self.hierarchy
        method = self.config.script.device.screenshot_method
        if method in AppControl._app_u2_family:
            self.hierarchy = self.dump_hierarchy_uiautomator2()
        else:
            self.hierarchy = self.dump_hierarchy_adb()
        return self.hierarchy

    def xpath_to_button(self, xpath: str) -> HierarchyButton:
        """
        Args:
            xpath (str):

        Returns:
            HierarchyButton:
                An object with methods and properties similar to Button.
                If element not found or multiple elements were found, return None.
        """
        return HierarchyButton(self.hierarchy, xpath)
