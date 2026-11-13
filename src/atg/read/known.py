"""What the 20+ reader recognises. Built from real exports; anything else is reported as unknown.

Add an entry only after seeing it in a real export.
"""

from __future__ import annotations

# Haul root tag -> canonical type. contentHaul is split by its inner element (CONTENT_SUBTYPES).
HAUL_ROOTS: dict[str, str] = {
    "applicationHaul": "application",
    "contentHaul": "content",
    "processModelHaul": "processModel",
    "processModelFolderHaul": "processModelFolder",
    "recordTypeHaul": "recordType",
    "groupHaul": "group",
    "siteHaul": "site",
    "connectedSystemHaul": "connectedSystem",
    "dataStoreHaul": "dataStore",
    "webApiHaul": "webApi",
    # Legacy Tempo objects, seen in 20.x and 22.x exports
    "tempoFeedHaul": "tempoFeed",
    "tempoReportHaul": "tempoReport",
    "taskReportHaul": "taskReport",
}

# Inner element of a contentHaul -> canonical type.
CONTENT_SUBTYPES: dict[str, str] = {
    "rule": "rule",
    "interface": "interface",
    "constant": "constant",
    "decision": "decision",
    "outboundIntegration": "integration",
    "document": "document",
    "folder": "folder",
    "rulesFolder": "rulesFolder",
    "report": "report",
    "communityKnowledgeCenter": "knowledgeCenter",
}

# Children of a Haul root that are metadata, not the object itself.
HAUL_METADATA = frozenset(
    {"versionUuid", "roleMap", "history", "typedValue", "isPublished", "folderUuid"}
)

# Elements whose UUIDs are version stamps, not references.
VERSION_TAGS = frozenset({"versionUuid", "historyInfo"})

# Process node types (ac/local-id) seen in real exports (Appian 20.1 to 26.6).
NODE_TYPES: frozenset[str] = frozenset(
    {
        "core.0",  # Start Node
        "core.1",  # End Node
        "core.2",  # AND
        "core.3",  # OR
        "core.4",  # XOR
        "core.5",  # Complex
        "core.7",  # Intermediate Consuming Event
        "internal.9",  # Create Folder
        "internal.16",  # Script task (Unattended Multiple Questions)
        "internal.17",  # User Input Task
        "internal.19",  # Add Members to Group
        "internal.38",  # Sub-process
        "internal2.movedocument",
        "internal3.createGroup",
        "internal3.delete_records_from_source",
        "internal3.delete_records_from_source_23r4",
        "internal3.integration",
        "internal3.sendemail3",
        "internal3.write_records_to_source",
        "internal3.write_records_to_source_23r3",
        "internal.database601",  # Query Database
        "internal.sendemail2",  # Send E-Mail (older)
        "internal2.deactivateuser",
        "internal2.deletedocument",
        "internal2.deletefolder",
        "appian.system.smart-services.data-export-entity-excel2",
        "appian.system.smart-services.delete-from-data-store",
        "appian.system.smart-services.post-comment-to-feed-2",
        "appian.system.smart-services.post-custom-event-to-feed-5",
        "appian.system.smart-services.complete-task-2",
        "appian.system.smart-services.start-process-2",
        "appian.system.smart-services.write-to-data-store",
        # Plugin smart services
        "PersonalizationUtilities.AddUserWithi18n",
        "msgraphmailpoller.MSGraphMailPoller",
        "com.appiancorp.a2.process.runtime.activities.sftp.GetRemoteFolderContentsOverSFTP_V21",
        "com.appiancorp.a2.process.runtime.activities.sftp.SendFileOverFTPS_V21",
        "com.appiancorp.a2.process.runtime.activities.sftp.SendFileOverSFTP_V21",
    }
)

# Gateways whose acp "rules" hold (condition -> target node) pairs.
GATEWAY_TYPES = frozenset({"core.3", "core.4", "core.5"})

# Type namespaces that belong to the platform, not to the app.
PLATFORM_TYPE_NAMESPACES = frozenset(
    {
        "http://www.w3.org/2001/XMLSchema",
        "http://www.appian.com/ae/types/2009",
    }
)
