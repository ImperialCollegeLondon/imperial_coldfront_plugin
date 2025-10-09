# Application Overview

This application extends the functionality of Coldfront to support management of the
RDF Active storage service for Imperial users. It provides:

- a high level interface to Active Directory (via LDAP).
- a high level interface to the GPFS API.
- a high level interface to the Microsoft graph for retrieval of user identity data.
- additional allocation and project attributes to store additional required metadata.
- administration views for the creation of Groups (reskinned Coldfront projects) and
  RDF Active Storage allocations.

Working in conjunction with overrides of various base Coldfront components this supports
the following functionality:

- Groups (a.k.a. Coldfront Projects) can be created only by admins using a dedicated
  view. Additional metadata is stored as project attributes (e.g. department and
  faculty).
- RDF Active storage allocations can be created via a view available to application
  admins. Creating a storage allocation in this way:
  - Assigns a unique GID for the allocation.
  - Creates a new AD group and adds the owner of the allocation as a member.
  - Creates a new fileset in GPFS owned by the AD group.
  - Stores required additional metadata for as allocation attributes.
- Adding/removing members to/from RDF Active storage allocations updates AD group
  membership.
- Synchronisation of fileset quota usages from GPFS to Coldfront allocations.
- Periodic auditing of the consistency of Coldfront allocation memberships and AD
  groups. Notifications are sent to application admins for manual resolution of
  discrepancies.
