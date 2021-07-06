#!/usr/bin/env python
"""These are process related flows."""

from grr.lib.rdfvalues.android import AndroidSensorDataRequest
from grr.server import flow
from grr.server import server_stubs


class GetSensorData(flow.GRRFlow):
  """Dump sensor data of a specific sensor on an Android device for a duration."""

  category = "/Hardware/"
  behaviours = flow.GRRFlow.behaviours + "BASIC"
  args_type = AndroidSensorDataRequest

  @flow.StateHandler()
  def Start(self):
    """Start processing."""
    self.CallClient(server_stubs.GetAndroidSensorData,
                    self.args,
                    next_state="OnCompleted")

  @flow.StateHandler()
  def OnCompleted(self, responses):
    """This stores the processes."""

    if not responses.success:
      # Check for error, but continue. Errors are common on client.
      raise flow.FlowError("Error during sensor data dumping %s" % responses.status)

    for p in responses:
      self.SendReply(p)


  def NotifyAboutEnd(self):
    if self.runner.IsWritingResults():
      self.Notify("ViewObject", self.urn, "GetSensorData completed.")
