"""Page class, intended to be sub classed as an abstraction for a real web page

Page classes collect the logic for how to use a certain part of the web site
under test into one area.

"""
import time
from selenium.common import exceptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import TimeoutException, WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

ELEMENT_TIMEOUT = 10


class SeleniumWrapper(object):

    class ComponentMissing(Exception):
        pass

    def _get_component_class(self, component_or_selector):
        """Ensure we have a component

        Find a return if arguement is component, get registered component,
        or dynamically create a component.

        """
        if isinstance(component_or_selector, Component):
            return component_or_selector(self)
        try:
            return self._registry[component_or_selector]
        except KeyError:
            return type(
                'DynamicComponent',
                (Component,), {'selector': component_or_selector}
            )

    def get_component(self, component_or_selector):
        """Return an initialised component present in page

        takes either a component class to find in the page or a css selector.

        If the selector is not present in the page raises a ComponentMissing
        error.
        """
        ComponentClass = self._get_component_class(component_or_selector)

        try:
            return ComponentClass(self)
        except TimeoutException:
            raise self.ComponentMissing(
                '{} could not be found in page'.format(ComponentClass))

    def get_components(self, component_or_selector):
        """Return an list of initialised components present in page

        Returns an empty list if no components could be found
        """
        ComponentClass = self._get_component_class(component_or_selector)

        return [
            ComponentClass(self._parent, el)
                for el in self.get_elements(ComponentClass.selector)
        ]

    def _wait_for_condition(self, condition):
        """Wait until the expected condition is true and return the result"""
        return WebDriverWait(self._driver, ELEMENT_TIMEOUT).until(condition)

    def get_element(self, selector):
        """Get the DOM element identified by the css selector"""
        return self._wait_for_condition(
            ec.presence_of_element_located((By.CSS_SELECTOR, selector))
        )

    def get_element_by_link_text(self, link_text):
        """Get the DOM element identified by the css selector"""
        return self._wait_for_condition(
            ec.presence_of_element_located((By.LINK_TEXT, link_text))
        )

    def get_elements(self, selector):
        """Get a list of elements identified by the css selector"""
        return self._wait_for_condition(
            ec.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
        )

    def assert_text_in_element(self, selector, text):
        return self._wait_for_condition(
            ec.text_to_be_present_in_element((By.CSS_SELECTOR, selector), text)
        )

    def assert_element_invisible(self, selector):
        return self._wait_for_condition(
            ec.invisibility_of_element_located((By.CSS_SELECTOR, selector))
        )

    def _click(self, element, opens=None):
        element.click()
        if opens:
            return self._registry[opens](self)
        if self.url != self.location() and self.location() in self._registry:
            return self._registry[self._driver.current_url](
                self.tc, driver=self._driver)
        return self

    def click(self, selector, opens=None):
        """Main method for interacting with a page

        Returns either self, a new page object based on browser url, or a
        page component based on the selector passed in as 'opens'.

        """
        return self._click(self.get_element(selector), opens)

    def click_link(self, link_text, opens=None):
        return self._click(self.get_element_by_link_text(link_text), opens)

    def location(self):
        return self._driver.current_url.split('?')[0]

    def enter_text(self, selector, text):
        """Enter text into DOM element identified by selector

        The function performs some error checking because as of Jan 2014
        send_keys on the element is unreliable at text entry.

        """
        element = self.get_element(selector)
        for _ in range(5):
            element.send_keys(*text)
            try:
                value_in_place = element.get_attribute("value") or element.text
            except exceptions.StaleElementReferenceException:
                return
            expected = "".join([unicode(v) for v in text])
            if value_in_place == expected:
                return
            try:
                element.clear()
            except (exceptions.InvalidElementStateException,
                    exceptions.WebDriverException):
                return  # Element is not user editable and can't be cleared

            time.sleep(0.2)
        raise AssertionError("Unable to correctly type {}".format(text))

    @property
    def text(self):
        return self._element.text


class RegisterMeta(type):

    def __init__(cls, name, bases, dct):
        if dct.get('url'):
            cls._registry[dct.get('url')] = cls
        elif dct.get('component_selector'):
            cls._registry[dct.get('component_selector')] = cls

        return super(RegisterMeta, cls).__init__(name, bases, dct)


class Registry(object):
    _registry = dict()


class Component(SeleniumWrapper, Registry):
    __metaclass__ = RegisterMeta
    selector = None

    def __repr__(self):
        return '{}(selector="{}")'.format(
            self.__class__.__name__, self.component_selector)

    def __init__(self, parent, element=None):
        self._parent = parent
        self._driver = parent._driver
        if element:
            self._element = element
        else:
            self._element = self.get_element(self.selector)


class Page(SeleniumWrapper, Registry):
    """Generic web page, intended to be subclassed

    Pages and Components are

    class LoginPage(Page):
        url = 'https://your-site.com/login

        def login(username, password):
            self.enter_text("input[name=username]", username)
            self.enter_text("input[name=password]", password)
            return self.click("input[type=submit]")
    """
    __metaclass__ = RegisterMeta
    url = None

    def __init__(self, tc, driver=None):
        self.tc = tc
        if driver:
            self._driver = driver
        else:
            self._driver = tc.browser
        self._driver.get(self.url)
        self._element = self.get_element('body')

    def get_via_css(self, selector):
        """Shortand for getting html elements via css selectors"""
        try:
            return self._driver.find_element_by_css_selector(selector)
        except exceptions.NoSuchElementException:
            raise exceptions.NoSuchElementException(
                'Could not find element identified by css selector: "%s". '
                'in page with text: %s' % (selector, self.body_text()[:1000]))

    def get_all_via_css(self, selector):
        """Shortand for getting a list of html elements via css selectors"""
        try:
            return self._driver.find_elements_by_css_selector(selector)
        except exceptions.NoSuchElementException:
            raise exceptions.NoSuchElementException(
                'Could not find elements identified by css selector: "%s". '
                'in page with text: %s' % (selector, self.body_text()[:1000]))

    def drop_into_shell(self):
        """Drop into an IPython shell at the point this method is called

        Useful for interactive debugging. Inside the shell self is the
        test case.

        """
        self.tc.drop_into_shell()

    def body_text(self):
        """Get body text for current page"""
        return self.get_via_css("body").text

    def wait_for_visibility(self, selector, timeout_seconds=20):
        """Waits for an element to be displayed and returns it

        Raises an ElementNotVisibleException if the element does not become
        visible or doesn't exist after the timeout.
        """
        pause_interval = 1
        retries = timeout_seconds / pause_interval
        while retries:
            try:
                element = self.get_via_css(selector)
                if element.is_displayed():
                    return element
            except (exceptions.NoSuchElementException,
                    exceptions.StaleElementReferenceException):
                if retries <= 0:
                    raise
                else:
                    pass

            retries = retries - pause_interval
            time.sleep(pause_interval)
        raise exceptions.ElementNotVisibleException(
            "Element %s not visible despite waiting for %s seconds" % (
                selector, timeout_seconds)
        )

    def wait_for_invisibility(self, selector, timeout_seconds=20):
        """Waits for an element to not be displayed or not exist

        Raises an InvalidElementStateException if the element does not become
        invisible or exists after the timeout.
        """
        pause_interval = 1
        retries = timeout_seconds / pause_interval
        while retries:
            try:
                element = self.get_via_css(selector)
                if not element.is_displayed():
                    return element
            except (exceptions.NoSuchElementException,
                    exceptions.StaleElementReferenceException):
                return None

            retries = retries - pause_interval
            time.sleep(pause_interval)
        raise exceptions.InvalidElementStateException(
            "Element %s is visible despite waiting for %s seconds" % (
                selector, timeout_seconds)
        )

    def click_button_with_text(self, text):
        """Find buttons on the page and click the first one with the text"""
        for button in self.get_all_via_css("button"):
            if button.text == text and button.is_displayed():
                button.click()
                return
        raise AssertionError(
            "Could not find a button with the text '%s'" % (text,)
        )
