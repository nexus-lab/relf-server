#!/usr/bin/env python
"""Implementation of a router class that has approvals-based ACL checks."""



from grr.gui import api_call_handler_base
from grr.gui import api_call_router
from grr.gui import api_call_router_without_checks

from grr.gui.api_plugins import flow as api_flow
from grr.gui.api_plugins import user as api_user

from grr.server import access_control
from grr.server import aff4

from grr.server.aff4_objects import cronjobs
from grr.server.aff4_objects import user_managers

from grr.server.hunts import implementation


class ApiCallRouterWithApprovalChecks(api_call_router.ApiCallRouterStub):
  """Router that uses approvals-based ACL checks."""

  full_access_control_manager = None

  @staticmethod
  def ClearCache():
    cls = ApiCallRouterWithApprovalChecks
    cls.full_access_control_manager = None

  def _GetFullAccessControlManager(self):
    cls = ApiCallRouterWithApprovalChecks
    if cls.full_access_control_manager is None:
      cls.full_access_control_manager = user_managers.FullAccessControlManager()
    return cls.full_access_control_manager

  def CheckClientAccess(self, client_id, token=None):
    self.legacy_manager.CheckClientAccess(token.RealUID(),
                                          client_id.ToClientURN())

  def CheckHuntAccess(self, hunt_id, token=None):
    self.legacy_manager.CheckHuntAccess(token.RealUID(), hunt_id.ToURN())

  def CheckCronJobAccess(self, cron_job_id, token=None):
    cron_job_urn = cronjobs.CRON_MANAGER.CRON_JOBS_PATH.Add(cron_job_id)
    self.legacy_manager.CheckCronJobAccess(token.RealUID(), cron_job_urn)

  def CheckIfCanStartClientFlow(self, flow_name, token=None):
    self.legacy_manager.CheckIfCanStartFlow(token.RealUID(), flow_name)

  def CheckIfUserIsAdmin(self, token=None):
    user_managers.CheckUserForLabels(token.username, ["admin"], token=token)

  def __init__(self, params=None, legacy_manager=None, delegate=None):
    super(ApiCallRouterWithApprovalChecks, self).__init__(params=params)

    if not legacy_manager:
      legacy_manager = self._GetFullAccessControlManager()
    self.legacy_manager = legacy_manager

    if not delegate:
      delegate = api_call_router_without_checks.ApiCallRouterWithoutChecks()
    self.delegate = delegate

  # Artifacts methods.
  # =================
  #
  def ListArtifacts(self, args, token=None):
    # Everybody is allowed to list artifacts.

    return self.delegate.ListArtifacts(args, token=token)

  def UploadArtifact(self, args, token=None):
    # Everybody is allowed to upload artifacts.

    return self.delegate.UploadArtifact(args, token=token)

  def DeleteArtifacts(self, args, token=None):
    # Everybody is allowed to delete artifacts.

    return self.delegate.DeleteArtifacts(args, token=token)

  # Clients methods.
  # ===============
  #
  def SearchClients(self, args, token=None):
    # Everybody is allowed to search clients.

    return self.delegate.SearchClients(args, token=token)

  def GetClient(self, args, token=None):
    # Everybody is allowed to get information about a particular client.

    return self.delegate.GetClient(args, token=token)

  def GetClientVersions(self, args, token=None):
    # Everybody is allowed to get historical information about a client.

    return self.delegate.GetClientVersions(args, token=token)

  def GetClientVersionTimes(self, args, token=None):
    # Everybody is allowed to get the versions of a particular client.

    return self.delegate.GetClientVersionTimes(args, token=token)

  def InterrogateClient(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.InterrogateClient(args, token=token)

  def GetInterrogateOperationState(self, args, token=None):
    # No ACL checks are required here, since the user can only check
    # operations started by him- or herself.

    return self.delegate.GetInterrogateOperationState(args, token=token)

  def GetLastClientIPAddress(self, args, token=None):
    # Everybody is allowed to get the last ip address of a particular client.

    return self.delegate.GetLastClientIPAddress(args, token=token)

  def ListClientCrashes(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.ListClientCrashes(args, token=token)

  def ListClientActionRequests(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.ListClientActionRequests(args, token=token)

  def GetClientLoadStats(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.GetClientLoadStats(args, token=token)

  # Virtual file system methods.
  # ============================
  #
  def ListFiles(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.ListFiles(args, token=token)

  def GetVfsFilesArchive(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.GetVfsFilesArchive(args, token=token)

  def GetFileDetails(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.GetFileDetails(args, token=token)

  def GetFileText(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.GetFileText(args, token=token)

  def GetFileBlob(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.GetFileBlob(args, token=token)

  def GetFileVersionTimes(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.GetFileVersionTimes(args, token=token)

  def GetFileDownloadCommand(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.GetFileDownloadCommand(args, token=token)

  def CreateVfsRefreshOperation(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.CreateVfsRefreshOperation(args, token=token)

  def GetVfsRefreshOperationState(self, args, token=None):
    # No ACL checks are required here, since the user can only check
    # operations started by him- or herself.

    return self.delegate.GetVfsRefreshOperationState(args, token=token)

  def GetVfsTimeline(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.GetVfsTimeline(args, token=token)

  def GetVfsTimelineAsCsv(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.GetVfsTimelineAsCsv(args, token=token)

  def UpdateVfsFileContent(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.UpdateVfsFileContent(args, token=token)

  def GetVfsFileContentUpdateState(self, args, token=None):
    # No ACL checks are required here, since the user can only check
    # operations started by him- or herself.

    return self.delegate.GetVfsFileContentUpdateState(args, token=token)

  # Clients labels methods.
  # ======================
  #
  def ListClientsLabels(self, args, token=None):
    # Everybody is allowed to get a list of all labels used on the system.

    return self.delegate.ListClientsLabels(args, token=token)

  def AddClientsLabels(self, args, token=None):
    # Everybody is allowed to add labels. Labels owner will be attributed to
    # the current user.

    return self.delegate.AddClientsLabels(args, token=token)

  def RemoveClientsLabels(self, args, token=None):
    # Everybody is allowed to remove labels. ApiRemoveClientsLabelsHandler is
    # written in such a way, so that it will only delete user's own labels.

    return self.delegate.RemoveClientsLabels(args, token=token)

  # Clients flows methods.
  # =====================
  #
  def ListFlows(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.ListFlows(args, token=token)

  def GetFlow(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.GetFlow(args, token=token)

  def CreateFlow(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)
    self.CheckIfCanStartClientFlow(
        args.flow.name or args.flow.runner_args.flow_name, token=token)

    return self.delegate.CreateFlow(args, token=token)

  def CancelFlow(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.CancelFlow(args, token=token)

  def ListFlowRequests(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.ListFlowRequests(args, token=token)

  def ListFlowResults(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.ListFlowResults(args, token=token)

  def GetExportedFlowResults(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.GetExportedFlowResults(args, token=token)

  def GetFlowResultsExportCommand(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.GetFlowResultsExportCommand(args, token=token)

  def GetFlowFilesArchive(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.GetFlowFilesArchive(args, token=token)

  def ListFlowOutputPlugins(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.ListFlowOutputPlugins(args, token=token)

  def ListFlowOutputPluginLogs(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.ListFlowOutputPluginLogs(args, token=token)

  def ListFlowOutputPluginErrors(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.ListFlowOutputPluginErrors(args, token=token)

  def ListFlowLogs(self, args, token=None):
    self.CheckClientAccess(args.client_id, token=token)

    return self.delegate.ListFlowLogs(args, token=token)

  # Cron jobs methods.
  # =================
  #
  def ListCronJobs(self, args, token=None):
    # Everybody can list cron jobs.

    return self.delegate.ListCronJobs(args, token=token)

  def CreateCronJob(self, args, token=None):
    # Everybody can create a cron job.

    return self.delegate.CreateCronJob(args, token=token)

  def GetCronJob(self, args, token=None):
    # Everybody can retrieve a cron job.

    return self.delegate.GetCronJob(args, token=token)

  def ForceRunCronJob(self, args, token=None):
    self.CheckCronJobAccess(args.cron_job_id, token=token)

    return self.delegate.ForceRunCronJob(args, token=token)

  def ModifyCronJob(self, args, token=None):
    self.CheckCronJobAccess(args.cron_job_id, token=token)

    return self.delegate.ModifyCronJob(args, token=token)

  def ListCronJobFlows(self, args, token=None):
    # Everybody can list cron jobs' flows.

    return self.delegate.ListCronJobFlows(args, token=token)

  def GetCronJobFlow(self, args, token=None):
    # Everybody can get cron flows.

    return self.delegate.GetCronJobFlow(args, token=token)

  def DeleteCronJob(self, args, token=None):
    self.CheckCronJobAccess(args.cron_job_id, token=token)

    return self.delegate.DeleteCronJob(args, token=token)

  # Hunts methods.
  # =============
  #
  def ListHunts(self, args, token=None):
    # Everybody can list hunts.

    return self.delegate.ListHunts(args, token=token)

  def GetHunt(self, args, token=None):
    # Everybody can get hunt's information.

    return self.delegate.GetHunt(args, token=token)

  def ListHuntErrors(self, args, token=None):
    # Everybody can get hunt errors list.

    return self.delegate.ListHuntErrors(args, token=token)

  def ListHuntLogs(self, args, token=None):
    # Everybody can look into hunt's logs.

    return self.delegate.ListHuntLogs(args, token=token)

  def ListHuntResults(self, args, token=None):
    # Everybody can look into hunt's results.

    return self.delegate.ListHuntResults(args, token=token)

  def GetExportedHuntResults(self, args, token=None):
    # Everybody can export hunt's results.

    return self.delegate.GetExportedHuntResults(args, token=token)

  def GetHuntResultsExportCommand(self, args, token=None):
    # Everybody can get hunt's export command.

    return self.delegate.GetHuntResultsExportCommand(args, token=token)

  def ListHuntOutputPlugins(self, args, token=None):
    # Everybody can list hunt output plugins.

    return self.delegate.ListHuntOutputPlugins(args, token=token)

  def ListHuntOutputPluginLogs(self, args, token=None):
    # Everybody can list hunt output plugins logs.

    return self.delegate.ListHuntOutputPluginLogs(args, token=token)

  def ListHuntOutputPluginErrors(self, args, token=None):
    # Everybody can list hunt output plugin errors.

    return self.delegate.ListHuntOutputPluginErrors(args, token=token)

  def ListHuntCrashes(self, args, token=None):
    # Everybody can list hunt's crashes.

    return self.delegate.ListHuntCrashes(args, token=token)

  def GetHuntClientCompletionStats(self, args, token=None):
    # Everybody can get hunt's client completion stats.

    return self.delegate.GetHuntClientCompletionStats(args, token=token)

  def GetHuntStats(self, args, token=None):
    # Everybody can get hunt's stats.

    return self.delegate.GetHuntStats(args, token=token)

  def ListHuntClients(self, args, token=None):
    # Everybody can get hunt's clients.

    return self.delegate.ListHuntClients(args, token=token)

  def GetHuntContext(self, args, token=None):
    # Everybody can get hunt's context.

    return self.delegate.GetHuntContext(args, token=token)

  def CreateHunt(self, args, token=None):
    # Everybody can create a hunt.

    return self.delegate.CreateHunt(args, token=token)

  def ModifyHunt(self, args, token=None):
    # Starting/stopping hunt or modifying its attributes requires an approval.
    self.CheckHuntAccess(args.hunt_id, token=token)

    return self.delegate.ModifyHunt(args, token=token)

  def _GetHuntObj(self, hunt_id, token=None):
    hunt_urn = hunt_id.ToURN()
    try:
      return aff4.FACTORY.Open(
          hunt_urn, aff4_type=implementation.GRRHunt, token=token)
    except aff4.InstantiationError:
      raise api_call_handler_base.ResourceNotFoundError(
          "Hunt with id %s could not be found" % hunt_id)

  def DeleteHunt(self, args, token=None):
    hunt_obj = self._GetHuntObj(args.hunt_id, token=token)

    # Hunt's creator is allowed to delete the hunt.
    if token.username != hunt_obj.creator:
      self.CheckHuntAccess(args.hunt_id, token=token)

    return self.delegate.DeleteHunt(args, token=token)

  def GetHuntFilesArchive(self, args, token=None):
    self.CheckHuntAccess(args.hunt_id, token=token)

    return self.delegate.GetHuntFilesArchive(args, token=token)

  def GetHuntFile(self, args, token=None):
    self.CheckHuntAccess(args.hunt_id, token=token)

    return self.delegate.GetHuntFile(args, token=token)

  # Stats metrics methods.
  # =====================
  #
  def ListStatsStoreMetricsMetadata(self, args, token=None):
    # Everybody can list stats store metrics metadata.

    return self.delegate.ListStatsStoreMetricsMetadata(args, token=token)

  def GetStatsStoreMetric(self, args, token=None):
    # Everybody can get a metric.

    return self.delegate.GetStatsStoreMetric(args, token=token)

  def ListReports(self, args, token=None):
    # Everybody can list the reports.

    return self.delegate.ListReports(args, token=token)

  def GetReport(self, args, token=None):
    # Everybody can get report data.

    return self.delegate.GetReport(args, token=token)

  # Approvals methods.
  # =================
  #
  def CreateClientApproval(self, args, token=None):
    # Everybody can create a user client approval.

    return self.delegate.CreateClientApproval(args, token=token)

  def GetClientApproval(self, args, token=None):
    # Everybody can have access to everybody's client approvals, provided
    # they know: a client id, a username of the requester and an approval id.

    return self.delegate.GetClientApproval(args, token=token)

  def GrantClientApproval(self, args, token=None):
    # Everybody can grant everybody's client approvals, provided
    # they know: a client id, a username of the requester and an approval id.
    #
    # NOTE: Granting an approval doesn't necessarily mean that corresponding
    # approval request becomes fulfilled right away. Calling this method
    # adds the caller to the approval's approvers list. Then it depends
    # on a particular approval if this list is sufficient or not.
    # Typical case: user can grant his own approval, but this won't make
    # the approval valid.

    return self.delegate.GrantClientApproval(args, token=token)

  def ListClientApprovals(self, args, token=None):
    # Everybody can list their own user client approvals.

    return self.delegate.ListClientApprovals(args, token=token)

  def CreateHuntApproval(self, args, token=None):
    # Everybody can request a hunt approval.

    return self.delegate.CreateHuntApproval(args, token=token)

  def GetHuntApproval(self, args, token=None):
    # Everybody can have access to everybody's hunts approvals, provided
    # they know: a hunt id, a username of the requester and an approval id.

    return self.delegate.GetHuntApproval(args, token=token)

  def GrantHuntApproval(self, args, token=None):
    # Everybody can grant everybody's hunts approvals, provided
    # they know: a hunt id, a username of the requester and an approval id.
    #
    # NOTE: Granting an approval doesn't necessarily mean that corresponding
    # approval request becomes fulfilled right away. Calling this method
    # adds the caller to the approval's approvers list. Then it depends
    # on a particular approval if this list is sufficient or not.
    # Typical case: user can grant his own approval, but this won't make
    # the approval valid.

    return self.delegate.GrantHuntApproval(args, token=token)

  def ListHuntApprovals(self, args, token=None):
    # Everybody can list their own user hunt approvals.

    return self.delegate.ListHuntApprovals(args, token=token)

  def CreateCronJobApproval(self, args, token=None):
    # Everybody can request a cron job approval.

    return self.delegate.CreateCronJobApproval(args, token=token)

  def GetCronJobApproval(self, args, token=None):
    # Everybody can have access to everybody's crons approvals, provided
    # they know: a cron job id, a username of the requester and an approval id.

    return self.delegate.GetCronJobApproval(args, token=token)

  def GrantCronJobApproval(self, args, token=None):
    # Everybody can have access to everybody's crons approvals, provided
    # they know: a cron job id, a username of the requester and an approval id.
    #
    # NOTE: Granting an approval doesn't necessarily mean that corresponding
    # approval request becomes fulfilled right away. Calling this method
    # adds the caller to the approval's approvers list. Then it depends
    # on a particular approval if this list is sufficient or not.
    # Typical case: user can grant his own approval, but this won't make
    # the approval valid.

    return self.delegate.GrantCronJobApproval(args, token=token)

  def ListCronJobApprovals(self, args, token=None):
    # Everybody can list their own user cron approvals.

    return self.delegate.ListCronJobApprovals(args, token=token)

  # User settings methods.
  # =====================
  #
  def GetPendingUserNotificationsCount(self, args, token=None):
    # Everybody can get their own pending notifications count.

    return self.delegate.GetPendingUserNotificationsCount(args, token=token)

  def ListPendingUserNotifications(self, args, token=None):
    # Everybody can get their own pending notifications count.

    return self.delegate.ListPendingUserNotifications(args, token=token)

  def DeletePendingUserNotification(self, args, token=None):
    # Everybody can get their own pending notifications count.

    return self.delegate.DeletePendingUserNotification(args, token=token)

  def ListAndResetUserNotifications(self, args, token=None):
    # Everybody can get their own user notifications.

    return self.delegate.ListAndResetUserNotifications(args, token=token)

  def GetGrrUser(self, args, token=None):
    # Everybody can get their own user settings.

    interface_traits = api_user.ApiGrrUserInterfaceTraits().EnableAll()
    try:
      self.CheckIfUserIsAdmin(token=token)
    except access_control.UnauthorizedAccess:
      interface_traits.manage_binaries_nav_item_enabled = False

    return api_user.ApiGetOwnGrrUserHandler(interface_traits=interface_traits)

  def UpdateGrrUser(self, args, token=None):
    # Everybody can update their own user settings.

    return self.delegate.UpdateGrrUser(args, token=token)

  def ListPendingGlobalNotifications(self, args, token=None):
    # Everybody can get their global pending notifications.

    return self.delegate.ListPendingGlobalNotifications(args, token=token)

  def DeletePendingGlobalNotification(self, args, token=None):
    # Everybody can delete their global pending notifications.

    return self.delegate.DeletePendingGlobalNotification(args, token=token)

  # Config methods.
  # ==============
  #
  def GetConfig(self, args, token=None):
    # Everybody can read the whole config.

    return self.delegate.GetConfig(args, token=token)

  def GetConfigOption(self, args, token=None):
    # Everybody can read selected config options.

    return self.delegate.GetConfigOption(args, token=token)

  def ListGrrBinaries(self, args, token=None):
    self.CheckIfUserIsAdmin(token=token)

    return self.delegate.ListGrrBinaries(args, token=token)

  def GetGrrBinary(self, args, token=None):
    self.CheckIfUserIsAdmin(token=token)

    return self.delegate.GetGrrBinary(args, token=token)

  # Reflection methods.
  # ==================
  #
  def ListKbFields(self, args, token=None):
    # Everybody can list knowledge base fields.

    return self.delegate.ListKbFields(args, token=token)

  def ListFlowDescriptors(self, args, token=None):
    # Everybody can list flow descritors.

    return api_flow.ApiListFlowDescriptorsHandler(
        legacy_security_manager=self.legacy_manager)

  def ListAff4AttributeDescriptors(self, args, token=None):
    # Everybody can list aff4 attribute descriptors.

    return self.delegate.ListAff4AttributeDescriptors(args, token=token)

  def GetRDFValueDescriptor(self, args, token=None):
    # Everybody can get rdfvalue descriptors.

    return self.delegate.GetRDFValueDescriptor(args, token=token)

  def ListRDFValuesDescriptors(self, args, token=None):
    # Everybody can list rdfvalue descriptors.

    return self.delegate.ListRDFValuesDescriptors(args, token=token)

  def ListOutputPluginDescriptors(self, args, token=None):
    # Everybody can list output plugin descriptors.

    return self.delegate.ListOutputPluginDescriptors(args, token=token)

  def ListKnownEncodings(self, args, token=None):
    # Everybody can list file encodings.

    return self.delegate.ListKnownEncodings(args, token=token)

  def ListApiMethods(self, args, token=None):
    # Everybody can get the docs.

    return self.delegate.ListApiMethods(args, token=token)


# This class is kept here for backwards compatibility only.
# TODO(user): Remove EOQ42017
class ApiCallRouterWithApprovalChecksWithoutRobotAccess(
    ApiCallRouterWithApprovalChecks):
  pass


# This class is kept here for backwards compatibility only.
# TODO(user): Remove EOQ42017
class ApiCallRouterWithApprovalChecksWithRobotAccess(
    ApiCallRouterWithApprovalChecks):
  pass
