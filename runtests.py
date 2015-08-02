#!/usr/bin/env python
# vim:ts=4:sw=4:et:
import unittest
import os
import os.path
import sys
# Ensure that we can find pywatchman
sys.path.append(os.path.join(os.getcwd(), 'python'))
sys.path.append(os.path.join(os.getcwd(), 'tests', 'integration'))
import tempfile
import shutil
import subprocess
import traceback
import time
import argparse
import atexit
import WatchmanTapTests
import WatchmanInstance
import glob

parser = argparse.ArgumentParser(
    description="Run the watchman unit and integration tests")
parser.add_argument('-v', '--verbosity', default=2,
                    help="test runner verbosity")
parser.add_argument(
    "--keep",
    action='store_true',
    help="preserve all temporary files created during test execution")

parser.add_argument(
    "files",
    nargs='*',
    help='specify which test files to run')

parser.add_argument(
    '--method',
    action='append',
    help='specify which python test method names to run')

args = parser.parse_args()

# We test for this in a test case
os.environ['WATCHMAN_EMPTY_ENV_VAR'] = ''

unittest.installHandler()

# We'll put all our temporary stuff under one dir so that we
# can clean it all up at the end
temp_dir = os.path.realpath(tempfile.mkdtemp(prefix='watchmantest'))
if args.keep:
    atexit.register(sys.stdout.write,
                    'Preserving output in %s\n' % temp_dir)
else:
    atexit.register(shutil.rmtree, temp_dir)
# Redirect all temporary files to that location
tempfile.tempdir = temp_dir

# Start up a shared watchman instance for the tests.
inst = WatchmanInstance.Instance()
inst.start()

# Allow tests to locate our instance by default
os.environ['WATCHMAN_SOCK'] = inst.getSockPath()


class Result(unittest.TestResult):
    # Make it easier to spot success/failure by coloring the status
    # green for pass, red for fail and yellow for skip.
    # also print the elapsed time per test
    transport = None
    encoding = None

    def startTest(self, test):
        self.startTime = time.time()
        super(Result, self).startTest(test)

    def setFlavour(self, transport, encoding):
        self.transport = transport
        self.encoding = encoding

    def flavour(self, test):
        if self.transport:
            return '%s [%s, %s]' % (test.id(), self.transport, self.encoding)
        return test.id()

    def addSuccess(self, test):
        elapsed = time.time() - self.startTime
        super(Result, self).addSuccess(test)
        print('\033[32mPASS\033[0m %s (%.3fs)' % (self.flavour(test), elapsed))

    def addSkip(self, test, reason):
        elapsed = time.time() - self.startTime
        super(Result, self).addSkip(test, reason)
        print('\033[33mSKIP\033[0m %s (%.3fs) %s' %
              (self.flavour(test), elapsed, reason))

    def __printFail(self, test, err):
        elapsed = time.time() - self.startTime
        t, val, trace = err
        print('\033[31mFAIL\033[0m %s (%.3fs)\n%s' % (
            self.flavour(test),
            elapsed,
            ''.join(traceback.format_exception(t, val, trace))))

    def addFailure(self, test, err):
        self.__printFail(test, err)
        super(Result, self).addFailure(test, err)

    def addError(self, test, err):
        self.__printFail(test, err)
        super(Result, self).addError(test, err)


def expandFilesList(files):
    """ expand any dir names into a full list of files """
    res = []
    for g in args.files:
        if os.path.isdir(g):
            for dirname, dirs, files in os.walk(g):
                for f in files:
                    if not f.startswith('.'):
                        res.append(os.path.join(dirname, f))
        else:
            res.append(g)
    return res

if args.files:
    args.files = expandFilesList(args.files)


def shouldIncludeTestFile(filename):
    """ used by our loader to respect the set of tests to run """
    global args
    fname = os.path.relpath(filename.replace('.pyc', '.py'))
    if args.files:
        for f in args.files:
            if f == fname:
                return True
        return False

    if args.method:
        # implies python tests only
        if not fname.endswith('.py'):
            return False

    return True

def shouldIncludeTestName(name):
    """ used by our loader to respect the set of tests to run """
    global args
    if args.method:
        method = name.split('.').pop()
        for f in args.method:
            if method == f:
                return True
        return False
    return True


class Loader(unittest.TestLoader):
    """ allows us to control the subset of which tests are run """

    def __init__(self):
        super(Loader, self).__init__()

    def loadTestsFromTestCase(self, testCaseClass):
        return super(Loader, self).loadTestsFromTestCase(testCaseClass)

    def getTestCaseNames(self, testCaseClass):
        names = super(Loader, self).getTestCaseNames(testCaseClass)
        return filter(lambda name: shouldIncludeTestName(name), names)

    def loadTestsFromModule(self, module):
        if not shouldIncludeTestFile(module.__file__):
            return unittest.TestSuite()
        return super(Loader, self).loadTestsFromModule(module)

loader = Loader()
suite = unittest.TestSuite()
for d in ['python/tests', 'tests/integration']:
    suite.addTests(loader.discover(d, top_level_dir=d))
suite.addTests(WatchmanTapTests.discover(
    shouldIncludeTestFile, 'tests/*.t'))
suite.addTests(WatchmanTapTests.discover(
    shouldIncludeTestFile, 'tests/integration/*.php'))

unittest.TextTestRunner(
    resultclass=Result,
    verbosity=args.verbosity
).run(suite)