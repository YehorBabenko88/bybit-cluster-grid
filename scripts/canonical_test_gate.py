"""Exact reviewed pytest obligations; no skip or expected-failure success."""
class StrictTestRoster:
    """Require the complete reviewed roster to pass setup, call and teardown."""
    def __init__(self, expected, *, expected_count):
        if (type(expected_count) is not int or not 1 <= expected_count <= 4096
                or type(expected) not in (list, tuple) or len(expected) != expected_count
                or any(type(node) is not str or not 1 <= len(node) <= 2048 for node in expected)
                or len(set(expected)) != expected_count):
            raise ValueError('exact bounded successful-case roster required')
        self.expected=tuple(expected);self.errors=[];self.diagnostics=[];self.reports={};self.collected=False;self.accepted=False

    def _detail(self,text):
        if len(self.diagnostics)<16:self.diagnostics.append(text[:2048])

    def pytest_collection_finish(self,session):
        actual=[item.nodeid for item in session.items]
        self.collected=True
        if sorted(actual)!=sorted(self.expected):
            self.errors.append('unexpected or incomplete collection roster')
            missing=[node for node in self.expected if node not in actual][:4]
            extra=[node for node in actual if node not in self.expected][:4]
            self._detail('ROSTER_DIFF missing='+repr(missing)+' unexpected='+repr(extra))

    def pytest_deselected(self,items):
        if items:self.errors.append('deselected obligations')

    def pytest_collectreport(self,report):
        if report.outcome!='passed':self.errors.append('collection did not pass')

    def pytest_runtest_logreport(self,report):
        key=(report.nodeid,report.when)
        shape=type(report).__name__+' node='+repr(report.nodeid)+' phase='+repr(report.when)+' outcome='+repr(report.outcome)
        if report.nodeid not in self.expected or report.when not in ('setup','call','teardown'):
            self.errors.append('unexpected execution report');self._detail('UNEXPECTED_REPORT '+shape)
        if key in self.reports:
            self.errors.append('duplicate execution report');self._detail('DUPLICATE_REPORT '+shape)
        self.reports[key]=report.outcome
        if report.outcome!='passed' or hasattr(report,'wasxfail'):
            self.errors.append('skipped, failed, xfail or xpass obligation');self._detail('NONPASS_REPORT '+shape)

    def pytest_sessionfinish(self,session,exitstatus):
        required={(node,phase) for node in self.expected for phase in ('setup','call','teardown')}
        self.accepted=(exitstatus==0 and self.collected and not self.errors
                       and set(self.reports)==required
                       and all(value=='passed' for value in self.reports.values()))
        if not self.accepted:session.exitstatus=1

    def pytest_terminal_summary(self,terminalreporter):
        if not self.accepted:
            terminalreporter.write_sep('=', 'STRICT TEST ROSTER REFUSED: '+('; '.join(self.errors) or 'missing successful execution reports'))
            for detail in self.diagnostics:terminalreporter.write_line(detail)

