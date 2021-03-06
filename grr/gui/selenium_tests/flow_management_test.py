#!/usr/bin/env python
"""Test the flow_management interface."""


import os


import unittest
from grr.gui import gui_test_lib

from grr.lib import flags
from grr.lib import rdfvalue
from grr.lib.rdfvalues import client as rdf_client
from grr.lib.rdfvalues import flows as rdf_flows
from grr.lib.rdfvalues import paths as rdf_paths
from grr.server import aff4
from grr.server import data_store
from grr.server import flow
from grr.server.flows.general import filesystem as flows_filesystem
from grr.server.flows.general import processes as flows_processes
from grr.server.flows.general import transfer as flows_transfer
from grr.server.flows.general import webhistory as flows_webhistory
from grr.server.hunts import implementation
from grr.server.hunts import standard
from grr.server.hunts import standard_test
from grr.test_lib import action_mocks
from grr.test_lib import flow_test_lib
from grr.test_lib import test_lib


class TestFlowManagement(gui_test_lib.GRRSeleniumTest,
                         standard_test.StandardHuntTestMixin):
  """Test the flow management GUI."""

  def setUp(self):
    super(TestFlowManagement, self).setUp()

    self.client_id = rdf_client.ClientURN("C.0000000000000001")
    with aff4.FACTORY.Open(
        self.client_id, mode="rw", token=self.token) as client:
      client.Set(client.Schema.HOSTNAME("HostC.0000000000000001"))
    self.RequestAndGrantClientApproval(self.client_id)
    self.action_mock = action_mocks.FileFinderClientMock()

  def testOpeningManageFlowsOfUnapprovedClientRedirectsToHostInfoPage(self):
    self.Open("/#/clients/C.0000000000000002/flows/")

    # As we don't have an approval for C.0000000000000002, we should be
    # redirected to the host info page.
    self.WaitUntilEqual("/#/clients/C.0000000000000002/host-info",
                        self.GetCurrentUrlPath)
    self.WaitUntil(self.IsTextPresent,
                   "You do not have an approval for this client.")

  def testPageTitleReflectsSelectedFlow(self):
    pathspec = rdf_paths.PathSpec(
        path=os.path.join(self.base_path, "test.plist"),
        pathtype=rdf_paths.PathSpec.PathType.OS)
    flow_urn = flow.GRRFlow.StartFlow(
        flow_name=flows_transfer.GetFile.__name__,
        client_id=self.client_id,
        pathspec=pathspec,
        token=self.token)

    self.Open("/#/clients/C.0000000000000001/flows/")
    self.WaitUntilEqual("GRR | C.0000000000000001 | Flows", self.GetPageTitle)

    self.Click("css=td:contains('GetFile')")
    self.WaitUntilEqual("GRR | C.0000000000000001 | " + flow_urn.Basename(),
                        self.GetPageTitle)

  def testFlowManagement(self):
    """Test that scheduling flows works."""
    self.Open("/")

    self.Type("client_query", "C.0000000000000001")
    self.Click("client_query_submit")

    self.WaitUntilEqual(u"C.0000000000000001", self.GetText,
                        "css=span[type=subject]")

    # Choose client 1
    self.Click("css=td:contains('0001')")

    # First screen should be the Host Information already.
    self.WaitUntil(self.IsTextPresent, "HostC.0000000000000001")

    self.Click("css=a[grrtarget='client.launchFlows']")
    self.Click("css=#_Processes")
    self.Click("link=" + flows_processes.ListProcesses.__name__)
    self.WaitUntil(self.IsTextPresent, "C.0000000000000001")

    self.WaitUntil(self.IsTextPresent, "List running processes on a system.")

    self.Click("css=button.Launch")
    self.WaitUntil(self.IsTextPresent, "Launched Flow ListProcesses")

    self.Click("css=#_Browser")
    # Wait until the tree has expanded.
    self.WaitUntil(self.IsTextPresent, flows_webhistory.FirefoxHistory.__name__)

    # Check that we can get a file in chinese
    self.Click("css=#_Filesystem")

    # Wait until the tree has expanded.
    self.WaitUntil(self.IsTextPresent,
                   flows_filesystem.UpdateSparseImageChunks.__name__)

    self.Click("link=" + flows_transfer.GetFile.__name__)

    self.Select("css=.form-group:has(> label:contains('Pathtype')) select",
                "OS")
    self.Type("css=.form-group:has(> label:contains('Path')) input",
              u"/dev/c/msn[1].exe")

    self.Click("css=button.Launch")

    self.WaitUntil(self.IsTextPresent, "Launched Flow GetFile")

    # Test that recursive tests are shown in a tree table.
    flow.GRRFlow.StartFlow(
        client_id="aff4:/C.0000000000000001",
        flow_name=gui_test_lib.RecursiveTestFlow.__name__,
        token=self.token)

    self.Click("css=a[grrtarget='client.flows']")

    # Some rows are present in the DOM but hidden because parent flow row
    # wasn't expanded yet. Due to this, we have to explicitly filter rows
    # with "visible" jQuery filter.
    self.WaitUntilEqual(gui_test_lib.RecursiveTestFlow.__name__, self.GetText,
                        "css=grr-client-flows-list tr:visible:nth(1) td:nth(2)")

    self.WaitUntilEqual(flows_transfer.GetFile.__name__, self.GetText,
                        "css=grr-client-flows-list tr:visible:nth(2) td:nth(2)")

    # Click on the first tree_closed to open it.
    self.Click("css=grr-client-flows-list tr:visible:nth(1) .tree_closed")

    self.WaitUntilEqual(gui_test_lib.RecursiveTestFlow.__name__, self.GetText,
                        "css=grr-client-flows-list tr:visible:nth(2) td:nth(2)")

    # Select the requests tab
    self.Click("css=td:contains(GetFile)")
    self.Click("css=li[heading=Requests]")

    self.WaitUntil(self.IsElementPresent, "css=td:contains(1)")

    # Check that a StatFile client action was issued as part of the GetFile
    # flow.
    self.WaitUntil(self.IsElementPresent,
                   "css=.tab-content td.proto_value:contains(StatFile)")

  def testOverviewIsShownForNestedFlows(self):
    for _ in flow_test_lib.TestFlowHelper(
        gui_test_lib.RecursiveTestFlow.__name__,
        self.action_mock,
        client_id=self.client_id,
        token=self.token):
      pass

    self.Open("/#c=C.0000000000000001")
    self.Click("css=a[grrtarget='client.flows']")

    # There should be a RecursiveTestFlow in the list. Expand nested flows.
    self.Click("css=tr:contains('RecursiveTestFlow') span.tree_branch")
    # Click on a nested flow.
    self.Click("css=tr:contains('RecursiveTestFlow'):nth(2)")

    # Nested flow should have Depth argument set to 1.
    self.WaitUntil(self.IsElementPresent,
                   "css=td:contains('Depth') ~ td:nth(0):contains('1')")

    # Check that flow id of this flow has forward slash - i.e. consists of
    # 2 components.
    self.WaitUntil(self.IsTextPresent, "Flow ID")
    flow_id = self.GetText("css=dt:contains('Flow ID') ~ dd:nth(0)")
    self.assertTrue("/" in flow_id)

  def testOverviewIsShownForNestedHuntFlows(self):
    with implementation.GRRHunt.StartHunt(
        hunt_name=standard.GenericHunt.__name__,
        flow_runner_args=rdf_flows.FlowRunnerArgs(
            flow_name=gui_test_lib.RecursiveTestFlow.__name__),
        client_rate=0,
        token=self.token) as hunt:
      hunt.Run()

    self.AssignTasksToClients(client_ids=[self.client_id])
    self.RunHunt(client_ids=[self.client_id])

    self.Open("/#c=C.0000000000000001")
    self.Click("css=a[grrtarget='client.flows']")

    # There should be a RecursiveTestFlow in the list. Expand nested flows.
    self.Click("css=tr:contains('RecursiveTestFlow') span.tree_branch")
    # Click on a nested flow.
    self.Click("css=tr:contains('RecursiveTestFlow'):nth(2)")

    # Nested flow should have Depth argument set to 1.
    self.WaitUntil(self.IsElementPresent,
                   "css=td:contains('Depth') ~ td:nth(0):contains('1')")

    # Check that flow id of this flow has forward slash - i.e. consists of
    # 2 components.
    self.WaitUntil(self.IsTextPresent, "Flow ID")
    flow_id = self.GetText("css=dt:contains('Flow ID') ~ dd:nth(0)")
    self.assertTrue("/" in flow_id)

  def testLogsCanBeOpenedByClickingOnLogsTab(self):
    # RecursiveTestFlow doesn't send any results back.
    for _ in flow_test_lib.TestFlowHelper(
        gui_test_lib.FlowWithOneLogStatement.__name__,
        self.action_mock,
        client_id=self.client_id,
        token=self.token):
      pass

    self.Open("/#c=C.0000000000000001")
    self.Click("css=a[grrtarget='client.flows']")
    self.Click("css=td:contains('FlowWithOneLogStatement')")
    self.Click("css=li[heading=Log]")

    self.WaitUntil(self.IsTextPresent, "I do log.")

  def testLogTimestampsArePresentedInUTC(self):
    with test_lib.FakeTime(42):
      for _ in flow_test_lib.TestFlowHelper(
          gui_test_lib.FlowWithOneLogStatement.__name__,
          self.action_mock,
          client_id=self.client_id,
          token=self.token):
        pass

    self.Open("/#c=C.0000000000000001")
    self.Click("css=a[grrtarget='client.flows']")
    self.Click("css=td:contains('FlowWithOneLogStatement')")
    self.Click("css=li[heading=Log]")

    self.WaitUntil(self.IsTextPresent, "1970-01-01 00:00:42 UTC")

  def testResultsAreDisplayedInResultsTab(self):
    for _ in flow_test_lib.TestFlowHelper(
        gui_test_lib.FlowWithOneStatEntryResult.__name__,
        self.action_mock,
        client_id=self.client_id,
        token=self.token):
      pass

    self.Open("/#c=C.0000000000000001")
    self.Click("css=a[grrtarget='client.flows']")
    self.Click("css=td:contains('FlowWithOneStatEntryResult')")
    self.Click("css=li[heading=Results]")

    self.WaitUntil(self.IsTextPresent,
                   "aff4:/C.0000000000000001/fs/os/some/unique/path")

  def testEmptyTableIsDisplayedInResultsWhenNoResults(self):
    flow.GRRFlow.StartFlow(
        flow_name=gui_test_lib.FlowWithOneStatEntryResult.__name__,
        client_id=self.client_id,
        sync=False,
        token=self.token)

    self.Open("/#c=" + self.client_id.Basename())
    self.Click("css=a[grrtarget='client.flows']")
    self.Click("css=td:contains('FlowWithOneStatEntryResult')")
    self.Click("css=li[heading=Results]")

    self.WaitUntil(self.IsElementPresent, "css=#main_bottomPane table thead "
                   "th:contains('Value')")

  def testHashesAreDisplayedCorrectly(self):
    for _ in flow_test_lib.TestFlowHelper(
        gui_test_lib.FlowWithOneHashEntryResult.__name__,
        self.action_mock,
        client_id=self.client_id,
        token=self.token):
      pass

    self.Open("/#c=C.0000000000000001")
    self.Click("css=a[grrtarget='client.flows']")
    self.Click("css=td:contains('FlowWithOneHashEntryResult')")
    self.Click("css=li[heading=Results]")

    self.WaitUntil(self.IsTextPresent,
                   "9e8dc93e150021bb4752029ebbff51394aa36f069cf19901578"
                   "e4f06017acdb5")
    self.WaitUntil(self.IsTextPresent,
                   "6dd6bee591dfcb6d75eb705405302c3eab65e21a")
    self.WaitUntil(self.IsTextPresent, "8b0a15eefe63fd41f8dc9dee01c5cf9a")

  def testBrokenFlowsAreShown(self):
    for s in flow_test_lib.TestFlowHelper(
        gui_test_lib.FlowWithOneHashEntryResult.__name__,
        self.action_mock,
        client_id=self.client_id,
        token=self.token):
      flow_urn = s

    for s in flow_test_lib.TestFlowHelper(
        gui_test_lib.FlowWithOneHashEntryResult.__name__,
        self.action_mock,
        client_id=self.client_id,
        token=self.token):
      broken_flow_urn = s

    # Break the flow.
    data_store.DB.DeleteAttributes(broken_flow_urn,
                                   [flow.GRRFlow.SchemaCls.FLOW_CONTEXT])
    data_store.DB.Flush()

    flow_id = flow_urn.Basename()
    broken_flow_id = broken_flow_urn.Basename()

    self.Open("/#/clients/C.0000000000000001/flows")

    # Both flows are shown in the list even though one is broken.
    self.WaitUntil(self.IsTextPresent, flow_id)
    self.WaitUntil(self.IsTextPresent, broken_flow_id)

    # The broken flow shows the error message.
    self.Click("css=td:contains('%s')" % broken_flow_id)
    self.WaitUntil(self.IsTextPresent, "Error while Opening")
    self.WaitUntil(self.IsTextPresent, "Error while opening flow:")

  def testApiExampleIsShown(self):
    flow_urn = flow.GRRFlow.StartFlow(
        flow_name=gui_test_lib.FlowWithOneStatEntryResult.__name__,
        client_id=self.client_id,
        token=self.token)

    flow_id = flow_urn.Basename()
    self.Open("/#/clients/C.0000000000000001/flows/%s/api" % flow_id)

    self.WaitUntil(self.IsTextPresent,
                   "HTTP (authentication details are omitted)")
    self.WaitUntil(self.IsTextPresent,
                   'curl -X POST -H "Content-Type: application/json"')
    self.WaitUntil(self.IsTextPresent, '"@type": "type.googleapis.com/')
    self.WaitUntil(
        self.IsTextPresent,
        '"name": "%s"' % gui_test_lib.FlowWithOneStatEntryResult.__name__)

  def testChangingTabUpdatesUrl(self):
    flow_urn = flow.GRRFlow.StartFlow(
        flow_name=gui_test_lib.FlowWithOneStatEntryResult.__name__,
        client_id=self.client_id,
        token=self.token)

    flow_id = flow_urn.Basename()
    base_url = "/#/clients/C.0000000000000001/flows/%s" % flow_id

    self.Open(base_url)

    self.Click("css=li[heading=Requests]")
    self.WaitUntilEqual(base_url + "/requests", self.GetCurrentUrlPath)

    self.Click("css=li[heading=Results]")
    self.WaitUntilEqual(base_url + "/results", self.GetCurrentUrlPath)

    self.Click("css=li[heading=Log]")
    self.WaitUntilEqual(base_url + "/log", self.GetCurrentUrlPath)

    self.Click("css=li[heading='Flow Information']")
    self.WaitUntilEqual(base_url, self.GetCurrentUrlPath)

    self.Click("css=li[heading=API]")
    self.WaitUntilEqual(base_url + "/api", self.GetCurrentUrlPath)

  def testDirectLinksToFlowsTabsWorkCorrectly(self):
    flow_urn = flow.GRRFlow.StartFlow(
        flow_name=gui_test_lib.FlowWithOneStatEntryResult.__name__,
        client_id=self.client_id,
        token=self.token)

    flow_id = flow_urn.Basename()
    base_url = "/#/clients/C.0000000000000001/flows/%s" % flow_id

    self.Open(base_url + "/requests")
    self.WaitUntil(self.IsElementPresent, "css=li.active[heading=Requests]")

    self.Open(base_url + "/results")
    self.WaitUntil(self.IsElementPresent, "css=li.active[heading=Results]")

    self.Open(base_url + "/log")
    self.WaitUntil(self.IsElementPresent, "css=li.active[heading=Log]")

    # Check that both clients/.../flows/... and clients/.../flows/.../ URLs
    # work.
    self.Open(base_url)
    self.WaitUntil(self.IsElementPresent,
                   "css=li.active[heading='Flow Information']")

    self.Open(base_url + "/")
    self.WaitUntil(self.IsElementPresent,
                   "css=li.active[heading='Flow Information']")

  def testCancelFlowWorksCorrectly(self):
    """Tests that cancelling flows works."""
    flow.GRRFlow.StartFlow(
        client_id=self.client_id,
        flow_name=gui_test_lib.RecursiveTestFlow.__name__,
        token=self.token)

    # Open client and find the flow
    self.Open("/")

    self.Type("client_query", "C.0000000000000001")
    self.Click("client_query_submit")

    self.WaitUntilEqual(u"C.0000000000000001", self.GetText,
                        "css=span[type=subject]")
    self.Click("css=td:contains('0001')")
    self.Click("css=a[grrtarget='client.flows']")

    self.Click("css=td:contains('RecursiveTestFlow')")
    self.Click("css=button[name=cancel_flow]")

    # The window should be updated now
    self.WaitUntil(self.IsTextPresent, "Cancelled in GUI")

  def testFlowListGetsUpdatedWithNewFlows(self):
    flow_1 = flow.GRRFlow.StartFlow(
        client_id=self.client_id,
        flow_name=gui_test_lib.RecursiveTestFlow.__name__,
        token=self.token)

    self.Open("/#/clients/C.0000000000000001")
    # Ensure auto-refresh updates happen every second.
    self.GetJavaScriptValue(
        "grrUi.flow.flowsListDirective.AUTO_REFRESH_INTERVAL_MS = 1000")

    # Go to the flows page without refreshing the page, so that
    # AUTO_REFRESH_INTERVAL_MS setting is not reset.
    self.Click("css=a[grrtarget='client.flows']")

    # Check that the flow list is correctly loaded.
    self.WaitUntil(self.IsElementPresent,
                   "css=tr:contains('%s')" % flow_1.Basename())

    flow_2 = flow.GRRFlow.StartFlow(
        client_id=self.client_id,
        flow_name=gui_test_lib.FlowWithOneLogStatement.__name__,
        token=self.token)

    # Check that the flow we started in the background appears in the list.
    self.WaitUntil(self.IsElementPresent,
                   "css=tr:contains('%s')" % flow_2.Basename())

  def testFlowListGetsUpdatedWithChangedFlows(self):
    f = flow.GRRFlow.StartFlow(
        client_id=self.client_id,
        flow_name=gui_test_lib.RecursiveTestFlow.__name__,
        token=self.token)

    self.Open("/#/clients/C.0000000000000001")
    # Ensure auto-refresh updates happen every second.
    self.GetJavaScriptValue(
        "grrUi.flow.flowsListDirective.AUTO_REFRESH_INTERVAL_MS = 1000")

    # Go to the flows page without refreshing the page, so that
    # AUTO_REFRESH_INTERVAL_MS setting is not reset.
    self.Click("css=a[grrtarget='client.flows']")

    # Check that the flow is running.
    self.WaitUntil(self.IsElementPresent,
                   "css=tr:contains('%s') div[state=RUNNING]" % f.Basename())

    # Cancel the flow and check that the flow state gets updated.
    flow.GRRFlow.TerminateFlow(
        f, "Because I said so", token=self.token, force=True)
    self.WaitUntil(self.IsElementPresent,
                   "css=tr:contains('%s') div[state=ERROR]" % f.Basename())

  def testFlowOverviewGetsUpdatedWhenFlowChanges(self):
    f = flow.GRRFlow.StartFlow(
        client_id=self.client_id,
        flow_name=gui_test_lib.RecursiveTestFlow.__name__,
        token=self.token)

    self.Open("/#/clients/C.0000000000000001")
    # Ensure auto-refresh updates happen every second.
    self.GetJavaScriptValue(
        "grrUi.flow.flowOverviewDirective.AUTO_REFRESH_INTERVAL_MS = 1000")

    # Go to the flows page without refreshing the page, so that
    # AUTO_REFRESH_INTERVAL_MS setting is not reset.
    self.Click("css=a[grrtarget='client.flows']")
    self.Click("css=tr:contains('%s')" % f.Basename())

    # Check that the flow is running.
    self.WaitUntil(self.IsElementPresent,
                   "css=grr-flow-inspector dd:contains('RUNNING')")
    self.WaitUntil(self.IsElementPresent, "css=grr-flow-inspector "
                   "tr:contains('Status'):contains('Subflow call 1')")

    # Cancel the flow and check that the flow state gets updated.
    flow.GRRFlow.TerminateFlow(
        f, "Because I said so", token=self.token, force=True)
    self.WaitUntil(self.IsElementPresent,
                   "css=grr-flow-inspector dd:contains('ERROR')")
    self.WaitUntil(self.IsElementPresent, "css=grr-flow-inspector "
                   "tr:contains('Status'):contains('Because I said so')")

  def testFlowLogsTabGetsUpdatedWhenNewLogsAreAdded(self):
    f = flow.GRRFlow.StartFlow(
        client_id=self.client_id,
        flow_name=gui_test_lib.RecursiveTestFlow.__name__,
        token=self.token)

    with aff4.FACTORY.Open(f, token=self.token) as fd:
      fd.Log("foo-log")

    self.Open("/#/clients/C.0000000000000001")
    # Ensure auto-refresh updates happen every second.
    self.GetJavaScriptValue(
        "grrUi.flow.flowLogDirective.AUTO_REFRESH_INTERVAL_MS = 1000")

    # Go to the flows page without refreshing the page, so that
    # AUTO_REFRESH_INTERVAL_MS setting is not reset.
    self.Click("css=a[grrtarget='client.flows']")
    self.Click("css=tr:contains('%s')" % f.Basename())
    self.Click("css=li[heading=Log]:not([disabled]")

    self.WaitUntil(self.IsElementPresent,
                   "css=grr-flow-log td:contains('foo-log')")
    self.WaitUntilNot(self.IsElementPresent,
                      "css=grr-flow-log td:contains('bar-log')")

    with aff4.FACTORY.Open(f, token=self.token) as fd:
      fd.Log("bar-log")

    self.WaitUntil(self.IsElementPresent,
                   "css=grr-flow-log td:contains('bar-log')")

  def testFlowResultsTabGetsUpdatedWhenNewResultsAreAdded(self):
    f = flow.GRRFlow.StartFlow(
        client_id=self.client_id,
        flow_name=gui_test_lib.RecursiveTestFlow.__name__,
        token=self.token)

    with data_store.DB.GetMutationPool() as pool:
      flow.GRRFlow.ResultCollectionForFID(f).Add(
          rdfvalue.RDFString("foo-result"), mutation_pool=pool)

    self.Open("/#/clients/C.0000000000000001")
    # Ensure auto-refresh updates happen every second.
    self.GetJavaScriptValue(
        "grrUi.core.resultsCollectionDirective.AUTO_REFRESH_INTERVAL_MS = 1000")

    # Go to the flows page without refreshing the page, so that
    # AUTO_REFRESH_INTERVAL_MS setting is not reset.
    self.Click("css=a[grrtarget='client.flows']")
    self.Click("css=tr:contains('%s')" % f.Basename())
    self.Click("css=li[heading=Results]:not([disabled]")

    self.WaitUntil(self.IsElementPresent,
                   "css=grr-results-collection td:contains('foo-result')")
    self.WaitUntilNot(self.IsElementPresent,
                      "css=grr-results-collection td:contains('bar-result')")

    with data_store.DB.GetMutationPool() as pool:
      flow.GRRFlow.ResultCollectionForFID(f).Add(
          rdfvalue.RDFString("bar-result"), mutation_pool=pool)
    self.WaitUntil(self.IsElementPresent,
                   "css=grr-results-collection td:contains('bar-result')")

  def testDownloadFilesPanelIsShownWhenNewResultsAreAdded(self):
    f = flow.GRRFlow.StartFlow(
        client_id=self.client_id,
        flow_name=gui_test_lib.RecursiveTestFlow.__name__,
        token=self.token)

    with data_store.DB.GetMutationPool() as pool:
      flow.GRRFlow.ResultCollectionForFID(f).Add(
          rdfvalue.RDFString("foo-result"), mutation_pool=pool)

    self.Open("/#/clients/C.0000000000000001")
    # Ensure auto-refresh updates happen every second.
    self.GetJavaScriptValue(
        "grrUi.core.resultsCollectionDirective.AUTO_REFRESH_INTERVAL_MS = 1000")

    # Go to the flows page without refreshing the page, so that
    # AUTO_REFRESH_INTERVAL_MS setting is not reset.
    self.Click("css=a[grrtarget='client.flows']")
    self.Click("css=tr:contains('%s')" % f.Basename())
    self.Click("css=li[heading=Results]:not([disabled]")

    self.WaitUntil(self.IsElementPresent,
                   "css=grr-results-collection td:contains('foo-result')")
    self.WaitUntilNot(
        self.IsElementPresent,
        "css=grr-results-collection grr-download-collection-files")

    stat_entry = rdf_client.StatEntry(
        pathspec=rdf_paths.PathSpec(
            path="/foo/bar", pathtype=rdf_paths.PathSpec.PathType.OS))
    with data_store.DB.GetMutationPool() as pool:
      flow.GRRFlow.ResultCollectionForFID(f).Add(stat_entry, mutation_pool=pool)

    self.WaitUntil(self.IsElementPresent,
                   "css=grr-results-collection grr-download-collection-files")


def main(argv):
  del argv  # Unused.
  # Run the full test suite
  unittest.main()


if __name__ == "__main__":
  flags.StartMain(main)
