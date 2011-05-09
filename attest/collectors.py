# coding:utf-8
from __future__ import with_statement

import inspect
from contextlib import contextmanager
import sys
from functools import wraps

from . import statistics
from .contexts import capture_output
from .utils import import_dotted_name, deep_get_members, nested
from .reporters import auto_reporter, AbstractReporter, TestResult


class Tests(object):
    """Collection of test functions.

    :param tests:
        String, or iterable of values, suitable as argument(s) to
        :meth:`register`.
    :param contexts:
        Iterable of callables that take no arguments and return a context
        manager.

    .. versionadded:: 0.6
        Pass a single string to `tests` without wrapping it in an iterable.

    """

    def __init__(self, tests=(), contexts=None):
        self._tests = []
        if isinstance(tests, basestring):
            self.register(tests)
        else:
            for collection in tests:
                self.register(collection)
        self._contexts = []
        if contexts is not None:
            self._contexts.extend(contexts)

    def __iter__(self):
        return iter(self._tests)

    def __len__(self):
        return len(self._tests)

    def test_if(self, condition):
        """Returns :meth:`test` if the `condition` is ``True``.

        .. versionadded:: 0.4

        """
        if condition:
            return self.test
        return lambda x: x

    def test(self, func):
        """Decorate a function as a test belonging to this collection."""
        @wraps(func)
        def wrapper():
            with nested(self._contexts) as context:
                context = [c for c in context if c is not None]
                argc = len(inspect.getargspec(func)[0])
                args = []
                for arg in context:
                    if type(arg) is tuple:  # type() is intentional
                        args.extend(arg)
                    else:
                        args.append(arg)
                func(*args[:argc])
        self._tests.append(wrapper)
        return wrapper

    def context(self, func):
        """Decorate a function as a :func:`~contextlib.contextmanager`
        for running the tests in this collection in. Corresponds to setup
        and teardown in other testing libraries.

        ::

            db = Tests()

            @db.context
            def connect():
                con = connect_db()
                try:
                    yield con
                finally:
                    con.disconnect()

            @db.test
            def using_connection(con):
                assert con is not None

        The above corresponds to::

            db = Tests()

            @contextmanager
            def connect():
                con = connect_db()
                try:
                    yield con
                finally:
                    con.disconnect()

            @db.test
            def using_connection():
                with connect() as con:
                    assert con is not None

        The difference is that this decorator applies the context to all
        tests defined in its collection, so it's less repetitive.

        Yielding :const:`None` or nothing passes no arguments to the test,
        yielding a single value other than a tuple passes that value as
        the sole argument to the test, yielding a tuple splats the tuple
        as the arguments to the test. If you want to yield a tuple as
        the sole argument, wrap it in a one-tuple or unsplat the args
        in the test.

        You can have more than one context, which will be run in order
        using :func:`contextlib.nested`, and their yields will be passed in
        order to the test functions.

        .. versionadded:: 0.2 Nested contexts.

        .. versionchanged:: 0.5
            Tests will gets as many arguments as they ask for.

        """
        func = contextmanager(func)
        self._contexts.append(func)
        return func

    def register_if(self, condition):
        """Returns :meth:`register` if the `condition` is ``True``.

        .. versionadded:: 0.4

        """
        if condition:
            return self.register
        return lambda x: x

    def register(self, tests):
        """Merge in other tests.

        :param tests:
            * A class, which is then instantiated and return allowing it to be
              used as a decorator for :class:`TestBase` classes.
            * A string, representing the dotted name to one of:

              * a module or package, which is recursively scanned for
                :class:`Tests` instances that are not private
              * an iterable yielding tests
            * Otherwise any iterable object is assumed to yield tests.

        Any of these can be passed in a list to the :class:`Tests`
        constructor.

        .. versionadded:: 0.2
            Refer to collections by import path as a string

        .. versionadded:: 0.6
            Recursive scanning of modules and packages

        .. versionchanged:: 0.6
            Tests are only added if not already added

        """
        if inspect.isclass(tests):
            self._tests.extend(tests())
            return tests
        elif isinstance(tests, basestring):
            def istests(obj):
                return isinstance(obj, Tests)
            obj = import_dotted_name(tests)
            if inspect.ismodule(obj):
                for tests in deep_get_members(tests, istests):
                    self.register(tests)
                return
            tests = obj
        for test in tests:
            if not test in self._tests:
                self._tests.append(test)

    def test_suite(self):
        """Create a :class:`unittest.TestSuite` from this collection."""
        from unittest import TestSuite, FunctionTestCase
        suite = TestSuite()
        for test in self:
            suite.addTest(FunctionTestCase(test))
        return suite

    def run(self, reporter=auto_reporter, full_tracebacks=False):
        """Run all tests in this collection.

        :param reporter:
            An instance of :class:`~attest.reporters.AbstractReporter` or a
            callable returning something implementing that API (not
            enforced).
        :param full_tracebacks:
            Control if the call stack of Attest is hidden in tracebacks.

        .. versionchanged:: 0.6 Added `full_tracebacks`.

        """
        assertions, statistics.assertions = statistics.assertions, 0
        if not isinstance(reporter, AbstractReporter):
            reporter = reporter()
        reporter.begin(self._tests)
        for test in self:
            result = TestResult(test=test, full_tracebacks=full_tracebacks)
            try:
                with capture_output() as (out, err):
                    if test() is False:
                        raise AssertionError('test() is False')
            except BaseException, e:
                if isinstance(e, KeyboardInterrupt):
                    break
                result.error = e
                result.stdout, result.stderr = out, err
                result.exc_info = sys.exc_info()
                reporter.failure(result)
            else:
                result.stdout, result.stderr = out, err
                reporter.success(result)
        try:
            reporter.finished()
        finally:
            statistics.assertions = assertions

    def main(self):
        """Interface to :meth:`run` with command-line options.

        ``-h``, ``--help``
            Show a help message

        ``-r NAME``, ``--reporter NAME``
            Select reporter by name with
            :func:`~attest.reporters.get_reporter_by_name`

        ``--full-tracebacks``
            Show complete tracebacks without hiding Attest's own call stack

        ``-l``, ``--list-reporters``
            List the names of all installed reporters


        Remaining arguments are passed to the reporter.

        .. versionadded:: 0.2

        .. versionchanged:: 0.4 ``--list-reporters`` was added.

        .. versionchanged:: 0.6 ``--full-tracebacks`` was added.

        """
        from attest.run import main
        main(self)


def test_if(condition):
    """Returns :func:`test` if the `condition` is ``True``.

    .. versionadded:: 0.4

    """
    if condition:
        return test
    return lambda x: x


def test(meth):
    """Mark a :class:`TestBase` method as a test and wrap it to run in the
    :meth:`TestBase.__context__` of the subclass.

    """
    @wraps(meth)
    def wrapper(self):
        with contextmanager(self.__context__)():
            meth(self)
    wrapper.__test__ = True
    return wrapper


class TestBase(object):
    """Base for test classes. Decorate test methods with :func:`test`. Needs
    to be registered with a :class:`Tests` collection to be run. For setup
    and teardown, override :meth:`__context__` like a
    :func:`~contextlib.contextmanager` (without the decorator).

    ::

        class Math(TestBase):

            def __context__(self):
                self.two = 1 + 1
                yield
                del self.two

            @test
            def arithmetics(self):
                assert self.two == 2

        suite = Tests([Math()])
        suite.run()

    """

    def __context__(self):
        yield

    def __iter__(self):
        for name in dir(self):
            attr = getattr(self, name)
            if getattr(attr, '__test__', False) and callable(attr):
                yield attr
