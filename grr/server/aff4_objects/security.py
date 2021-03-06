#!/usr/bin/env python
"""AFF4 Objects to enforce ACL policies."""


import email

import jinja2

from grr import config
from grr.lib import rdfvalue
from grr.lib import utils
from grr.lib.rdfvalues import client as rdf_client
from grr.server import access_control
from grr.server import aff4
from grr.server import email_alerts
from grr.server import events
from grr.server.aff4_objects import aff4_grr
from grr.server.aff4_objects import users as aff4_users
from grr.server.authorization import client_approval_auth


class Error(Exception):
  """Base exception class."""


class ErrorClientDoesNotExist(Error):
  """Raised when trying to check approvals on non-existent client."""


class Approval(aff4.AFF4Object):
  """An abstract approval request object.

  This object normally lives within the namespace:
  aff4:/ACL/...

  The aff4:/ACL namespace is not writable by users, hence all manipulation of
  this object must be done via dedicated flows. These flows use the server's
  access credentials for manipulating this object.
  """

  class SchemaCls(aff4.AFF4Object.SchemaCls):
    """The Schema for the Approval class."""
    REQUESTOR = aff4.Attribute("aff4:approval/requestor", rdfvalue.RDFString,
                               "Requestor of the approval.")

    APPROVER = aff4.Attribute("aff4:approval/approver", rdfvalue.RDFString,
                              "An approver for the request.", "approver")

    SUBJECT = aff4.Attribute("aff4:approval/subject", rdfvalue.RDFURN,
                             "Subject of the approval. I.e. the resource that "
                             "requires approved access.")

    REASON = aff4.Attribute("aff4:approval/reason",
                            rdfvalue.RDFString,
                            "The reason for requesting access to this client.")

    EMAIL_MSG_ID = aff4.Attribute("aff4:approval/email_msg_id",
                                  rdfvalue.RDFString,
                                  "The email thread message ID for this"
                                  "approval. Storing this allows for "
                                  "conversation threading.")

    EMAIL_CC = aff4.Attribute("aff4:approval/email_cc", rdfvalue.RDFString,
                              "Comma separated list of email addresses to "
                              "CC on approval emails.")

    NOTIFIED_USERS = aff4.Attribute("aff4:approval/notified_users",
                                    rdfvalue.RDFString,
                                    "Comma-separated list of GRR users "
                                    "notified about this approval.")

  def CheckAccess(self, token):
    """Check that this approval applies to the given token.

    Args:
      token: User's credentials token.
    Returns:
      True if access is granted, raises access_control.UnauthorizedAccess
      otherwise.
    Raises:
      access_control.UnauthorizedAccess: if access is rejected.
    """
    _ = token
    raise NotImplementedError()

  @staticmethod
  def GetApprovalForObject(object_urn, token=None, username=""):
    """Looks for approvals for an object and returns available valid tokens.

    Args:
      object_urn: Urn of the object we want access to.

      token: The token to use to lookup the ACLs.

      username: The user to get the approval for, if "" we get it from the
        token.

    Returns:
      A token for access to the object on success, otherwise raises.

    Raises:
      UnauthorizedAccess: If there are no valid approvals available.

    """
    if token is None:
      raise access_control.UnauthorizedAccess(
          "No token given, cannot authenticate.")

    if not username:
      username = token.username

    approvals_root_urn = aff4.ROOT_URN.Add("ACL").Add(
        object_urn.Path()).Add(username)

    children_urns = list(aff4.FACTORY.ListChildren(approvals_root_urn))
    if not children_urns:
      raise access_control.UnauthorizedAccess(
          "No approval found for user %s" % utils.SmartStr(username),
          subject=object_urn)

    last_error = None
    approvals = aff4.FACTORY.MultiOpen(
        children_urns,
        mode="r",
        aff4_type=Approval,
        age=aff4.ALL_TIMES,
        token=token)
    for approval in approvals:
      try:
        test_token = access_control.ACLToken(
            username=username, reason=approval.Get(approval.Schema.REASON))
        approval.CheckAccess(test_token)

        return test_token
      except access_control.UnauthorizedAccess as e:
        last_error = e

    if last_error:
      # We tried all possible approvals, but got no usable results.
      raise access_control.UnauthorizedAccess(last_error, subject=object_urn)
    else:
      # If last error is None, means that none of the URNs in children_urns
      # could be opened. This shouldn't really happen ever, but we have
      # to make sure to provide a meaningful error message.
      raise access_control.UnauthorizedAccess(
          "Couldn't open any of %d approvals "
          "for user %s" % (len(children_urns), utils.SmartStr(username)),
          subject=object_urn)


class ApprovalWithApproversAndReason(Approval):
  """Generic all-purpose base approval class.

  This object normally lives within the aff4:/ACL namespace. Username is
  encoded into this object's urn. Subject's urn (i.e. urn of the object
  which this approval corresponds for) can also be inferred from this approval's
  urn.
  This class provides following functionality:
  * Number of approvers configured by ACL.approvers_required configuration
    parameter is required for this approval's CheckAccess() to succeed.
  * Optional checked_approvers_label attribute may be specified. Then
    at least min_approvers_with_label number of approvers will have to
    have checked_approvers_label label in order for CheckAccess to
    succeed.
  * Break-glass functionality. If this approval's BREAK_GLASS attribute is
    set, user's token is marked as emergency token and CheckAccess() returns
    True.

  The aff4:/ACL namespace is not writable by users, hence all manipulation of
  this object must be done via dedicated flows.
  """

  checked_approvers_label = None
  min_approvers_with_label = 1

  class SchemaCls(Approval.SchemaCls):
    """The Schema for the ClientAccessApproval class."""

    LIFETIME = aff4.Attribute(
        "aff4:approval/lifetime",
        rdfvalue.RDFInteger,
        "The number of seconds an approval is valid for.",
        default=0)
    BREAK_GLASS = aff4.Attribute(
        "aff4:approval/breakglass", rdfvalue.RDFDatetime,
        "The date when this break glass approval will expire.")

  def InferUserAndSubjectFromUrn(self):
    """Infers user name and subject urn from self.urn.

    Returns:
      (username, subject_urn) tuple.
    """
    raise NotImplementedError()

  def GetApprovers(self, now):
    lifetime = rdfvalue.Duration(
        self.Get(self.Schema.LIFETIME) or config.CONFIG["ACL.token_expiry"])

    # Check that there are enough approvers.
    approvers = set()
    for approver in self.GetValuesForAttribute(self.Schema.APPROVER):
      if approver.age + lifetime > now:
        approvers.add(utils.SmartStr(approver))
    return approvers

  def CheckAccess(self, token):
    """Enforce a dual approver policy for access."""
    namespace, _ = self.urn.Split(2)

    if namespace != "ACL":
      raise access_control.UnauthorizedAccess(
          "Approval object has invalid urn %s." % self.urn,
          subject=self.urn,
          requested_access=token.requested_access)

    user, subject_urn = self.InferUserAndSubjectFromUrn()
    if user != token.username:
      raise access_control.UnauthorizedAccess(
          "Approval object is not for user %s." % token.username,
          subject=self.urn,
          requested_access=token.requested_access)

    now = rdfvalue.RDFDatetime.Now()

    # Is this an emergency access?
    break_glass = self.Get(self.Schema.BREAK_GLASS)
    if break_glass and now < break_glass:
      # This tags the token as an emergency token.
      token.is_emergency = True
      return True

    # Check that there are enough approvers.
    approvers = self.GetNonExpiredApprovers()
    approvers_required = config.CONFIG["ACL.approvers_required"]
    if len(approvers) < approvers_required:
      missing = approvers_required - len(approvers)
      msg = ("Need at least %d additional approver%s for access." %
             (missing, "s" if missing > 1 else ""))

      raise access_control.UnauthorizedAccess(
          msg, subject=subject_urn, requested_access=token.requested_access)

    # Check User labels
    if self.checked_approvers_label:
      approvers_with_label = []

      # We need to check labels with high privilege since normal users can
      # inspect other user's labels.
      for approver in approvers:
        try:
          user = aff4.FACTORY.Open(
              "aff4:/users/%s" % approver,
              aff4_type=aff4_users.GRRUser,
              token=token.SetUID())
          if self.checked_approvers_label in user.GetLabelsNames():
            approvers_with_label.append(approver)
        except IOError:
          pass

      if len(approvers_with_label) < self.min_approvers_with_label:
        missing = self.min_approvers_with_label - len(approvers_with_label)
        raise access_control.UnauthorizedAccess(
            "Need at least %d additional approver%s "
            "with the '%s' label for access." % (missing, "s"
                                                 if missing > 1 else "",
                                                 self.checked_approvers_label),
            subject=subject_urn,
            requested_access=token.requested_access)

    return True

  def GetNonExpiredApprovers(self):
    """Returns a list of usernames of approvers who approved this approval."""

    lifetime = rdfvalue.Duration(
        self.Get(self.Schema.LIFETIME) or config.CONFIG["ACL.token_expiry"])

    # Check that there are enough approvers.
    #
    # TODO(user): approvals have to be opened with
    # age=aff4.ALL_TIMES because versioning is used to store lists
    # of approvers. This doesn't seem right and has to be fixed.
    approvers = set()
    now = rdfvalue.RDFDatetime.Now()
    for approver in self.GetValuesForAttribute(self.Schema.APPROVER):
      if approver.age + lifetime > now:
        approvers.add(utils.SmartStr(approver))

    return list(approvers)


class ClientApproval(ApprovalWithApproversAndReason):
  """An approval request for access to a specific client.

  This object normally lives within the namespace:
  aff4:/ACL/client_id/user/approval:<id>

  Hence the client_id and user which is granted access are inferred from this
  object's URN.
  """

  def InferUserAndSubjectFromUrn(self):
    """Infers user name and subject urn from self.urn."""
    _, client_id, user, _ = self.urn.Split(4)
    return (user, rdf_client.ClientURN(client_id))

  def CheckAccess(self, token):
    super(ClientApproval, self).CheckAccess(token)
    # If approvers isn't set and super-class checking passed, we're done.
    if not client_approval_auth.CLIENT_APPROVAL_AUTH_MGR.IsActive():
      return True

    now = rdfvalue.RDFDatetime.Now()
    approvers = self.GetApprovers(now)
    requester, client_urn = self.InferUserAndSubjectFromUrn()
    # Open the client object with superuser privs so we can get the list of
    # labels
    try:
      client_object = aff4.FACTORY.Open(
          client_urn,
          mode="r",
          aff4_type=aff4_grr.VFSGRRClient,
          token=token.SetUID())
    except aff4.InstantiationError:
      raise ErrorClientDoesNotExist("Can't check label approvals on client %s "
                                    "that doesn't exist" % client_urn)

    client_labels = client_object.Get(client_object.Schema.LABELS, [])

    for label in client_labels:
      client_approval_auth.CLIENT_APPROVAL_AUTH_MGR.CheckApproversForLabel(
          token, client_urn, requester, approvers, label.name)

    return True


class HuntApproval(ApprovalWithApproversAndReason):
  """An approval request for running a specific hunt.

  This object normally lives within the namespace:
  aff4:/ACL/hunts/hunt_id/user_id/approval:<id>

  Hence the hunt_id and user_id are inferred from this object's URN.
  """

  checked_approvers_label = "admin"

  def InferUserAndSubjectFromUrn(self):
    """Infers user name and subject urn from self.urn."""
    _, hunts_str, hunt_id, user, _ = self.urn.Split(5)

    if hunts_str != "hunts":
      raise access_control.UnauthorizedAccess(
          "Approval object has invalid urn %s." % self.urn,
          requested_access=self.token.requested_access)

    return (user, aff4.ROOT_URN.Add("hunts").Add(hunt_id))


class CronJobApproval(ApprovalWithApproversAndReason):
  """An approval request for managing a specific cron job.

  This object normally lives within the namespace:
  aff4:/ACL/cron/cron_job_id/user_id/approval:<id>

  Hence the hunt_id and user_id are inferred from this object's URN.
  """

  checked_approvers_label = "admin"

  def InferUserAndSubjectFromUrn(self):
    """Infers user name and subject urn from self.urn."""
    _, cron_str, cron_job_name, user, _ = self.urn.Split(5)

    if cron_str != "cron":
      raise access_control.UnauthorizedAccess(
          "Approval object has invalid urn %s." % self.urn,
          requested_access=self.token.requested_access)

    return (user, aff4.ROOT_URN.Add("cron").Add(cron_job_name))


class AbstractApprovalBase(object):
  """Abstract class for approval requests/grants."""
  approval_type = None

  def BuildApprovalUrn(self, approval_id):
    """Builds approval object urn."""
    raise NotImplementedError()

  def BuildApprovalSymlinksUrns(self, unused_approval_id):
    """Builds a list of symlinks to the approval object."""
    return []

  def BuildSubjectTitle(self):
    """Returns the string with subject's title."""
    raise NotImplementedError()

  @staticmethod
  def ApprovalUrnBuilder(subject, user, approval_id):
    """Encode an approval URN."""
    return aff4.ROOT_URN.Add("ACL").Add(subject).Add(user).Add(approval_id)

  @staticmethod
  def ApprovalSymlinkUrnBuilder(approval_type, subject_id, user, approval_id):
    """Build an approval symlink URN."""
    return aff4.ROOT_URN.Add("users").Add(user).Add("approvals").Add(
        approval_type).Add(subject_id).Add(approval_id)


class ApprovalRequestor(AbstractApprovalBase):
  """Base class for requesting approvals of a certain type."""

  def __init__(self,
               reason=None,
               subject_urn=None,
               approver=None,
               email_cc_address=None,
               token=None):
    super(ApprovalRequestor, self).__init__()

    if not reason:
      raise ValueError("reason can't be empty.")
    self.reason = reason

    if not subject_urn:
      raise ValueError("subject_urn can't be empty.")
    self.subject_urn = rdfvalue.RDFURN(subject_urn)

    if not approver:
      raise ValueError("approver can't be empty.")
    self.approver = approver

    self.email_cc_address = email_cc_address

    if not token:
      raise ValueError("token can't be empty.")
    self.token = token

  def BuildApprovalReviewUrlPath(self, approval_id):
    """Build the url path to the approval review page."""
    raise NotImplementedError()

  def Request(self):
    """Create the Approval object and notify the Approval Granter."""

    approval_id = "approval:%X" % utils.PRNG.GetULong()
    approval_urn = self.BuildApprovalUrn(approval_id)

    subject_title = self.BuildSubjectTitle()
    email_msg_id = email.utils.make_msgid()

    with aff4.FACTORY.Create(
        approval_urn, self.approval_type, mode="w",
        token=self.token) as approval_request:
      approval_request.Set(approval_request.Schema.SUBJECT(self.subject_urn))
      approval_request.Set(
          approval_request.Schema.REQUESTOR(self.token.username))
      approval_request.Set(approval_request.Schema.REASON(self.reason))
      approval_request.Set(approval_request.Schema.EMAIL_MSG_ID(email_msg_id))

      cc_addresses = (self.email_cc_address,
                      config.CONFIG.Get("Email.approval_cc_address"))
      email_cc = ",".join(filter(None, cc_addresses))

      # When we reply with the approval we want to cc all the people to whom the
      # original approval was sent, to avoid people approving stuff that was
      # already approved.
      if email_cc:
        reply_cc = ",".join((self.approver, email_cc))
      else:
        reply_cc = self.approver

      approval_request.Set(approval_request.Schema.EMAIL_CC(reply_cc))

      approval_request.Set(
          approval_request.Schema.NOTIFIED_USERS(self.approver))

      # We add ourselves as an approver as well (The requirement is that we have
      # 2 approvers, so the requester is automatically an approver).
      approval_request.AddAttribute(
          approval_request.Schema.APPROVER(self.token.username))

    approval_link_urns = self.BuildApprovalSymlinksUrns(approval_id)
    for link_urn in approval_link_urns:
      with aff4.FACTORY.Create(
          link_urn, aff4.AFF4Symlink, mode="w", token=self.token) as link:
        link.Set(link.Schema.SYMLINK_TARGET(approval_urn))

    # Notify to the users.
    for user in self.approver.split(","):
      user = user.strip()
      try:
        fd = aff4.FACTORY.Open(
            aff4.ROOT_URN.Add("users").Add(user),
            aff4_type=aff4_users.GRRUser,
            mode="rw",
            token=self.token)
      except aff4.InstantiationError:
        continue

      fd.Notify("GrantAccess", approval_urn,
                "Please grant access to %s" % subject_title, "")
      fd.Close()

    if not config.CONFIG.Get("Email.send_approval_emails"):
      return approval_urn

    subject_template = jinja2.Template(
        "Approval for {{ user }} to access {{ client }}.", autoescape=True)
    subject = subject_template.render(
        user=utils.SmartUnicode(self.token.username),
        client=utils.SmartUnicode(subject_title))

    template = jinja2.Template(
        """
<html><body><h1>Approval to access
<a href='{{ admin_ui }}/#/{{ approval_url }}'>{{ subject_title }}</a>
requested.</h1>

The user "{{ username }}" has requested access to
<a href='{{ admin_ui }}/#/{{ approval_url }}'>{{ subject_title }}</a>
for the purpose of <em>{{ reason }}</em>.

Please click <a href='{{ admin_ui }}/#/{{ approval_url }}'>
here
</a> to review this request and then grant access.

<p>Thanks,</p>
<p>{{ signature }}</p>
<p>{{ image|safe }}</p>
</body></html>""",
        autoescape=True)

    body = template.render(
        username=utils.SmartUnicode(self.token.username),
        reason=utils.SmartUnicode(self.reason),
        admin_ui=utils.SmartUnicode(config.CONFIG["AdminUI.url"]),
        subject_title=utils.SmartUnicode(subject_title),
        approval_url=utils.SmartUnicode(
            self.BuildApprovalReviewUrlPath(approval_id)),
        # If you feel like it, add a funny cat picture here :)
        image=utils.SmartUnicode(config.CONFIG["Email.approval_signature"]),
        signature=utils.SmartUnicode(config.CONFIG["Email.signature"]))

    email_alerts.EMAIL_ALERTER.SendEmail(
        self.approver,
        utils.SmartStr(self.token.username),
        utils.SmartStr(subject),
        utils.SmartStr(body),
        is_html=True,
        cc_addresses=email_cc,
        message_id=email_msg_id)

    return approval_urn


class ApprovalGrantor(AbstractApprovalBase):
  """Base class for granting approvals of a certain type."""

  def __init__(self, reason=None, subject_urn=None, delegate=None, token=None):
    super(ApprovalGrantor, self).__init__()

    if not reason:
      raise ValueError("reason can't be empty.")
    self.reason = reason

    if not subject_urn:
      raise ValueError("subject_urn can't be empty.")
    self.subject_urn = rdfvalue.RDFURN(subject_urn)

    if not delegate:
      raise ValueError("delegate can't be empty.")
    self.delegate = delegate

    if not token:
      raise ValueError("token can't be empty.")
    self.token = token

  def Grant(self):
    """Create the Approval object and notify the Approval Granter."""

    approvals_root_urn = aff4.ROOT_URN.Add("ACL").Add(
        self.subject_urn.Path()).Add(self.delegate)
    children_urns = list(aff4.FACTORY.ListChildren(approvals_root_urn))
    if not children_urns:
      raise access_control.UnauthorizedAccess(
          "No approval found for user %s" % utils.SmartStr(self.token.username),
          subject=self.subject_urn)

    approvals = aff4.FACTORY.MultiOpen(
        children_urns, mode="r", aff4_type=Approval, token=self.token)
    found_approval_urn = None
    for approval in approvals:
      approval_reason = approval.Get(approval.Schema.REASON)
      if (utils.SmartUnicode(approval_reason) == utils.SmartUnicode(
          self.reason) and (not found_approval_urn or
                            approval_reason.age > found_approval_urn.age)):
        found_approval_urn = approval.urn
        found_approval_urn.age = approval_reason.age

    if not found_approval_urn:
      raise access_control.UnauthorizedAccess(
          "No approval with reason '%s' found for user %s" %
          (utils.SmartStr(self.reason), utils.SmartStr(self.token.username)),
          subject=self.subject_urn)

    subject_title = self.BuildSubjectTitle()
    access_url = self.BuildAccessUrl()

    # This object must already exist.
    try:
      approval_request = aff4.FACTORY.Open(
          found_approval_urn,
          mode="rw",
          aff4_type=self.approval_type,
          token=self.token)
    except IOError:
      raise access_control.UnauthorizedAccess(
          "Approval object does not exist.", requested_access="rw")

    with approval_request:
      # We are now an approver for this request.
      approval_request.AddAttribute(
          approval_request.Schema.APPROVER(self.token.username))
      email_msg_id = utils.SmartStr(
          approval_request.Get(approval_request.Schema.EMAIL_MSG_ID))
      email_cc = utils.SmartStr(
          approval_request.Get(approval_request.Schema.EMAIL_CC))

    # Notify to the user.
    with aff4.FACTORY.Create(
        aff4.ROOT_URN.Add("users").Add(self.delegate),
        aff4_users.GRRUser,
        mode="rw",
        token=self.token) as fd:
      fd.Notify("ViewObject", self.subject_urn,
                "%s has granted you access to %s." % (self.token.username,
                                                      subject_title), "")

    if not config.CONFIG.Get("Email.send_approval_emails"):
      return found_approval_urn

    subject_template = jinja2.Template(
        "Approval for {{ user }} to access {{ client }}.", autoescape=True)
    subject = subject_template.render(
        user=utils.SmartUnicode(self.delegate),
        client=utils.SmartUnicode(subject_title))

    template = jinja2.Template(
        """
<html><body><h1>Access to
<a href='{{ admin_ui }}/#/{{ subject_url }}'>{{ subject_title }}</a>
granted.</h1>

The user {{ username }} has granted access to
<a href='{{ admin_ui }}/#/{{ subject_url }}'>{{ subject_title }}</a> for the
purpose of <em>{{ reason }}</em>.

Please click <a href='{{ admin_ui }}/#/{{ subject_url }}'>here</a> to access it.

<p>Thanks,</p>
<p>{{ signature }}</p>
</body></html>""",
        autoescape=True)
    body = template.render(
        subject_title=utils.SmartUnicode(subject_title),
        username=utils.SmartUnicode(self.token.username),
        reason=utils.SmartUnicode(self.reason),
        admin_ui=utils.SmartUnicode(config.CONFIG["AdminUI.url"].strip("/")),
        subject_url=utils.SmartUnicode(access_url.strip("/")),
        signature=utils.SmartUnicode(config.CONFIG["Email.signature"]))

    # Email subject should match approval request, and we add message id
    # references so they are grouped together in a thread by gmail.
    headers = {"In-Reply-To": email_msg_id, "References": email_msg_id}
    email_alerts.EMAIL_ALERTER.SendEmail(
        utils.SmartStr(self.delegate),
        utils.SmartStr(self.token.username),
        utils.SmartStr(subject),
        utils.SmartStr(body),
        is_html=True,
        cc_addresses=email_cc,
        headers=headers)

    return found_approval_urn


class ClientApprovalRequestor(ApprovalRequestor):
  """A flow to request approval to access a client."""
  approval_type = ClientApproval

  def __init__(self, **kwargs):
    super(ClientApprovalRequestor, self).__init__(**kwargs)

    # Make sure subject_urn is actually a ClientURN.
    self.subject_urn = rdf_client.ClientURN(self.subject_urn)

  def BuildApprovalUrn(self, approval_id):
    """Builds approval object urn."""
    event = events.AuditEvent(
        user=self.token.username,
        action="CLIENT_APPROVAL_REQUEST",
        client=self.subject_urn,
        description=self.reason)
    events.Events.PublishEvent("Audit", event, token=self.token)

    return self.ApprovalUrnBuilder(self.subject_urn.Path(), self.token.username,
                                   approval_id)

  def BuildApprovalSymlinksUrns(self, approval_id):
    """Builds list of symlinks URNs for the approval object."""
    return [
        self.ApprovalSymlinkUrnBuilder("client", self.subject_urn.Basename(),
                                       self.token.username, approval_id)
    ]

  def BuildSubjectTitle(self):
    """Returns the string with subject's title."""
    client = aff4.FACTORY.Open(self.subject_urn, token=self.token)
    hostname = client.Get(client.Schema.HOSTNAME)
    return u"GRR client %s (%s)" % (self.subject_urn.Basename(), hostname)

  def BuildApprovalReviewUrlPath(self, approval_id):
    return "/".join([
        "users", self.token.username, "approvals", "client",
        self.subject_urn.Basename(), approval_id
    ])


class ClientApprovalGrantor(ApprovalGrantor):
  """Grant the approval requested."""
  approval_type = ClientApproval

  def BuildApprovalUrn(self, approval_id):
    """Builds approval object urn."""
    events.Events.PublishEvent(
        "Audit",
        events.AuditEvent(
            user=self.token.username,
            action="CLIENT_APPROVAL_GRANT",
            client=self.subject_urn,
            description=self.reason),
        token=self.token)

    return self.ApprovalUrnBuilder(self.subject_urn.Path(), self.delegate,
                                   approval_id)

  def BuildAccessUrl(self):
    """Builds the urn to access this object."""
    return "/clients/%s" % self.subject_urn.Basename()

  def BuildSubjectTitle(self):
    """Returns the string with subject's title."""
    client = aff4.FACTORY.Open(self.subject_urn, token=self.token)
    hostname = client.Get(client.Schema.HOSTNAME)
    return u"GRR client %s (%s)" % (self.subject_urn.Basename(), hostname)


class HuntApprovalRequestor(ApprovalRequestor):
  """A flow to request approval to access a client."""
  approval_type = HuntApproval

  def BuildApprovalUrn(self, approval_id):
    """Builds approval object URN."""
    # In this case subject_urn is hunt's URN.
    events.Events.PublishEvent(
        "Audit",
        events.AuditEvent(
            user=self.token.username,
            action="HUNT_APPROVAL_REQUEST",
            urn=self.subject_urn,
            description=self.reason),
        token=self.token)

    return self.ApprovalUrnBuilder(self.subject_urn.Path(), self.token.username,
                                   approval_id)

  def BuildApprovalSymlinksUrns(self, approval_id):
    """Builds list of symlinks URNs for the approval object."""
    return [
        self.ApprovalSymlinkUrnBuilder("hunt", self.subject_urn.Basename(),
                                       self.token.username, approval_id)
    ]

  def BuildSubjectTitle(self):
    """Returns the string with subject's title."""
    return u"hunt %s" % self.subject_urn.Basename()

  def BuildApprovalReviewUrlPath(self, approval_id):
    return "/".join([
        "users", self.token.username, "approvals", "hunt",
        self.subject_urn.Basename(), approval_id
    ])


class HuntApprovalGrantor(ApprovalGrantor):
  """Grant the approval requested."""
  approval_type = HuntApproval

  def BuildApprovalUrn(self, approval_id):
    """Builds approval object URN."""
    # In this case subject_urn is hunt's URN.
    events.Events.PublishEvent(
        "Audit",
        events.AuditEvent(
            user=self.token.username,
            action="HUNT_APPROVAL_GRANT",
            urn=self.subject_urn,
            description=self.reason),
        token=self.token)

    return self.ApprovalUrnBuilder(self.subject_urn.Path(), self.delegate,
                                   approval_id)

  def BuildSubjectTitle(self):
    """Returns the string with subject's title."""
    return u"hunt %s" % self.subject_urn.Basename()

  def BuildAccessUrl(self):
    """Builds the urn to access this object."""
    return "/hunts/%s" % self.subject_urn.Basename()


class CronJobApprovalRequestor(ApprovalRequestor):
  """A flow to request approval to manage a cron job."""
  approval_type = CronJobApproval

  def BuildApprovalUrn(self, approval_id):
    """Builds approval object URN."""
    # In this case subject_urn is a cron job's URN.
    events.Events.PublishEvent(
        "Audit",
        events.AuditEvent(
            user=self.token.username,
            action="CRON_APPROVAL_REQUEST",
            urn=self.subject_urn,
            description=self.reason),
        token=self.token)

    return self.ApprovalUrnBuilder(self.subject_urn.Path(), self.token.username,
                                   approval_id)

  def BuildApprovalSymlinksUrns(self, approval_id):
    """Builds list of symlinks URNs for the approval object."""
    return [
        self.ApprovalSymlinkUrnBuilder("cron", self.subject_urn.Basename(),
                                       self.token.username, approval_id)
    ]

  def BuildSubjectTitle(self):
    """Returns the string with subject's title."""
    return u"a cron job"

  def BuildApprovalReviewUrlPath(self, approval_id):
    return "/".join([
        "users", self.token.username, "approvals", "cron-job",
        self.subject_urn.Basename(), approval_id
    ])


class CronJobApprovalGrantor(ApprovalGrantor):
  """Grant approval to manage a cron job."""
  approval_type = CronJobApproval

  def BuildApprovalUrn(self):
    """Builds approval object URN."""
    events.Events.PublishEvent(
        "Audit",
        events.AuditEvent(
            user=self.token.username,
            action="CRON_APPROVAL_GRANT",
            urn=self.subject_urn,
            description=self.reason),
        token=self.token)

    return self.ApprovalUrnBuilder(self.subject_urn.Path(), self.delegate,
                                   self.reason)

  def BuildSubjectTitle(self):
    """Returns the string with subject's title."""
    return u"a cron job"

  def BuildAccessUrl(self):
    """Builds the urn to access this object."""
    return "/crons/%s" % self.subject_urn.Basename()
