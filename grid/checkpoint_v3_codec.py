"""Strict checkpoint V3 CLAIM codec, not an authority or confirmation adapter.

Schema SHA256: 4de720d9391e5a89c0577b5298c283e742fbfe490c4454c184e31c2348589ea4.
Owner Option1 distinguishes unknown commit time from an unconfirmed commit.
No network, storage, identity discovery or production proof integration exists here.
"""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re

MAX_BYTES = 32768
MAX_DEPTH = 12
MAX_MEMBERS = 48
MAX_U63 = 9223372036854775807


class CheckpointFormatError(ValueError):
    """Unsupported/noncanonical or internally inconsistent untrusted claim."""


class AuthorityIntegrationUnavailable(RuntimeError):
    """No admitted actual publication proof adapter is wired to this codec."""


# Fixed review image, never a schema supplied by a caller or read from disk.
_SCHEMA_BYTES = (
    b'{\r\n'
    b'  "$schema": "https://json-schema.org/draft/2020-12/schema",\r\n'
    b'  "$id": "urn:unified:historical-checkpoint:v3-review1",\r\n'
    b'  "title": "New owner-approved time semantics, exact wire ACK pending",\r\n'
    b'  "oneOf": [\r\n'
    b'    {\r\n'
    b'      "type": "object",\r\n'
    b'      "additionalProperties": false,\r\n'
    b'      "properties": {\r\n'
    b'        "schema_version": {\r\n'
    b'          "const": "3"\r\n'
    b'        },\r\n'
    b'        "schema": {\r\n'
    b'          "const": "unified.historical-checkpoint-confirmed.v3-review1"\r\n'
    b'        },\r\n'
    b'        "authority_profile": {\r\n'
    b'          "const": "unified.authority.event-ordered.v3"\r\n'
    b'        },\r\n'
    b'        "publication_content": {\r\n'
    b'          "type": "object",\r\n'
    b'          "additionalProperties": false,\r\n'
    b'          "properties": {\r\n'
    b'            "schema_version": {\r\n'
    b'              "const": "3"\r\n'
    b'            },\r\n'
    b'            "dataset_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'            },\r\n'
    b'            "instrument_id": {\r\n'
    b'              "type": "object",\r\n'
    b'              "additionalProperties": false,\r\n'
    b'              "properties": {\r\n'
    b'                "exchange": {\r\n'
    b'                  "const": "bybit"\r\n'
    b'                },\r\n'
    b'                "category": {\r\n'
    b'                  "enum": [\r\n'
    b'                    "linear",\r\n'
    b'                    "spot",\r\n'
    b'                    "inverse",\r\n'
    b'                    "option"\r\n'
    b'                  ]\r\n'
    b'                },\r\n'
    b'                "symbol": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[A-Z0-9][A-Z0-9_-]{0,63}$"\r\n'
    b'                },\r\n'
    b'                "instrument_version": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'                }\r\n'
    b'              },\r\n'
    b'              "required": [\r\n'
    b'                "exchange",\r\n'
    b'                "category",\r\n'
    b'                "symbol",\r\n'
    b'                "instrument_version"\r\n'
    b'              ]\r\n'
    b'            },\r\n'
    b'            "partition_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'            },\r\n'
    b'            "source_cursor": {\r\n'
    b'              "type": "object",\r\n'
    b'              "additionalProperties": false,\r\n'
    b'              "properties": {\r\n'
    b'                "kind": {\r\n'
    b'                  "const": "bybit.kline.reverse.1m.v1"\r\n'
    b'                },\r\n'
    b'                "requested_range": {\r\n'
    b'                  "type": "object",\r\n'
    b'                  "additionalProperties": false,\r\n'
    b'                  "properties": {\r\n'
    b'                    "start_ms": {\r\n'
    b'                      "type": "string",\r\n'
    b'                      "pattern": "^(0|[1-9][0-9]{0,18})$"\r\n'
    b'                    },\r\n'
    b'                    "end_ms": {\r\n'
    b'                      "type": "string",\r\n'
    b'                      "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'                    }\r\n'
    b'                  },\r\n'
    b'                  "required": [\r\n'
    b'                    "start_ms",\r\n'
    b'                    "end_ms"\r\n'
    b'                  ]\r\n'
    b'                },\r\n'
    b'                "request_end_ms": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^(0|[1-9][0-9]{0,18})$"\r\n'
    b'                },\r\n'
    b'                "response_sha256": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[0-9a-f]{64}$"\r\n'
    b'                }\r\n'
    b'              },\r\n'
    b'              "required": [\r\n'
    b'                "kind",\r\n'
    b'                "requested_range",\r\n'
    b'                "request_end_ms",\r\n'
    b'                "response_sha256"\r\n'
    b'              ]\r\n'
    b'            },\r\n'
    b'            "committed_cursor": {\r\n'
    b'              "type": "object",\r\n'
    b'              "additionalProperties": false,\r\n'
    b'              "properties": {\r\n'
    b'                "kind": {\r\n'
    b'                  "const": "bybit.kline.reverse.1m.v1"\r\n'
    b'                },\r\n'
    b'                "next_end_ms": {\r\n'
    b'                  "anyOf": [\r\n'
    b'                    {\r\n'
    b'                      "type": "string",\r\n'
    b'                      "pattern": "^(0|[1-9][0-9]{0,18})$"\r\n'
    b'                    },\r\n'
    b'                    {\r\n'
    b'                      "type": "null"\r\n'
    b'                    }\r\n'
    b'                  ]\r\n'
    b'                },\r\n'
    b'                "disposition_frontier_ms": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^(0|[1-9][0-9]{0,18})$"\r\n'
    b'                },\r\n'
    b'                "coverage_root": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[0-9a-f]{64}$"\r\n'
    b'                },\r\n'
    b'                "gap_root": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[0-9a-f]{64}$"\r\n'
    b'                }\r\n'
    b'              },\r\n'
    b'              "required": [\r\n'
    b'                "kind",\r\n'
    b'                "next_end_ms",\r\n'
    b'                "disposition_frontier_ms",\r\n'
    b'                "coverage_root",\r\n'
    b'                "gap_root"\r\n'
    b'              ]\r\n'
    b'            },\r\n'
    b'            "segment_manifest_revision": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'            },\r\n'
    b'            "assignment_revision": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'            },\r\n'
    b'            "lease_epoch": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'            },\r\n'
    b'            "fencing_token": {\r\n'
    b'              "type": "object",\r\n'
    b'              "additionalProperties": false,\r\n'
    b'              "properties": {\r\n'
    b'                "cluster_generation": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'                },\r\n'
    b'                "assignment_id": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'                },\r\n'
    b'                "lease_id": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'                },\r\n'
    b'                "node_id": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'                },\r\n'
    b'                "worker_incarnation_id": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'                },\r\n'
    b'                "leader_lock_index": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'                },\r\n'
    b'                "assignment_revision": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'                },\r\n'
    b'                "lease_epoch": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'                },\r\n'
    b'                "grant_revision": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'                },\r\n'
    b'                "owner_id": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'                }\r\n'
    b'              },\r\n'
    b'              "required": [\r\n'
    b'                "cluster_generation",\r\n'
    b'                "assignment_id",\r\n'
    b'                "lease_id",\r\n'
    b'                "node_id",\r\n'
    b'                "worker_incarnation_id",\r\n'
    b'                "leader_lock_index",\r\n'
    b'                "assignment_revision",\r\n'
    b'                "lease_epoch",\r\n'
    b'                "grant_revision",\r\n'
    b'                "owner_id"\r\n'
    b'              ]\r\n'
    b'            },\r\n'
    b'            "commit_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'            },\r\n'
    b'            "committed_at_utc": {\r\n'
    b'              "type": "null"\r\n'
    b'            },\r\n'
    b'            "cluster_generation": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'            },\r\n'
    b'            "checkpoint_revision": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'            },\r\n'
    b'            "previous_checkpoint_sha256": {\r\n'
    b'              "anyOf": [\r\n'
    b'                {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[0-9a-f]{64}$"\r\n'
    b'                },\r\n'
    b'                {\r\n'
    b'                  "type": "null"\r\n'
    b'                }\r\n'
    b'              ]\r\n'
    b'            },\r\n'
    b'            "segment_manifest_sha256": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{64}$"\r\n'
    b'            },\r\n'
    b'            "assignment_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'            },\r\n'
    b'            "grant_revision": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'            },\r\n'
    b'            "lease_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'            },\r\n'
    b'            "owner_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'            },\r\n'
    b'            "worker_incarnation_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'            },\r\n'
    b'            "storage_reservation_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'            },\r\n'
    b'            "storage_budget_revision": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'            },\r\n'
    b'            "publication_mode": {\r\n'
    b'              "const": "authority-root"\r\n'
    b'            },\r\n'
    b'            "target_range": {\r\n'
    b'              "type": "object",\r\n'
    b'              "additionalProperties": false,\r\n'
    b'              "properties": {\r\n'
    b'                "start_ms": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^(0|[1-9][0-9]{0,18})$"\r\n'
    b'                },\r\n'
    b'                "end_ms": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'                }\r\n'
    b'              },\r\n'
    b'              "required": [\r\n'
    b'                "start_ms",\r\n'
    b'                "end_ms"\r\n'
    b'              ]\r\n'
    b'            },\r\n'
    b'            "interval_ms": {\r\n'
    b'              "const": "60000"\r\n'
    b'            },\r\n'
    b'            "checkpoint_scope": {\r\n'
    b'              "const": "dataset-partition"\r\n'
    b'            },\r\n'
    b'            "source_id": {\r\n'
    b'              "const": "bybit.public.linear.kline.1m.v1"\r\n'
    b'            },\r\n'
    b'            "cluster_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'            },\r\n'
    b'            "node_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'            },\r\n'
    b'            "authority_profile": {\r\n'
    b'              "const": "unified.authority.event-ordered.v3"\r\n'
    b'            },\r\n'
    b'            "authority_session_binding": {\r\n'
    b'              "type": "object",\r\n'
    b'              "additionalProperties": false,\r\n'
    b'              "properties": {\r\n'
    b'                "leader_session_id": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'                },\r\n'
    b'                "lease_session_id": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'                },\r\n'
    b'                "lease_binding_revision": {\r\n'
    b'                  "type": "string",\r\n'
    b'                  "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'                }\r\n'
    b'              },\r\n'
    b'              "required": [\r\n'
    b'                "leader_session_id",\r\n'
    b'                "lease_session_id",\r\n'
    b'                "lease_binding_revision"\r\n'
    b'              ]\r\n'
    b'            },\r\n'
    b'            "commit_time_status": {\r\n'
    b'              "const": "UNKNOWN_COMMIT_INSTANT"\r\n'
    b'            }\r\n'
    b'          },\r\n'
    b'          "required": [\r\n'
    b'            "schema_version",\r\n'
    b'            "dataset_id",\r\n'
    b'            "instrument_id",\r\n'
    b'            "partition_id",\r\n'
    b'            "source_cursor",\r\n'
    b'            "committed_cursor",\r\n'
    b'            "segment_manifest_revision",\r\n'
    b'            "assignment_revision",\r\n'
    b'            "lease_epoch",\r\n'
    b'            "fencing_token",\r\n'
    b'            "commit_id",\r\n'
    b'            "committed_at_utc",\r\n'
    b'            "cluster_generation",\r\n'
    b'            "checkpoint_revision",\r\n'
    b'            "previous_checkpoint_sha256",\r\n'
    b'            "segment_manifest_sha256",\r\n'
    b'            "assignment_id",\r\n'
    b'            "grant_revision",\r\n'
    b'            "lease_id",\r\n'
    b'            "owner_id",\r\n'
    b'            "worker_incarnation_id",\r\n'
    b'            "storage_reservation_id",\r\n'
    b'            "storage_budget_revision",\r\n'
    b'            "publication_mode",\r\n'
    b'            "target_range",\r\n'
    b'            "interval_ms",\r\n'
    b'            "checkpoint_scope",\r\n'
    b'            "source_id",\r\n'
    b'            "cluster_id",\r\n'
    b'            "node_id",\r\n'
    b'            "authority_profile",\r\n'
    b'            "authority_session_binding",\r\n'
    b'            "commit_time_status"\r\n'
    b'          ]\r\n'
    b'        },\r\n'
    b'        "publication_content_sha256": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[0-9a-f]{64}$"\r\n'
    b'        },\r\n'
    b'        "receipt_ref": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'        },\r\n'
    b'        "authority_modify_index": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'        },\r\n'
    b'        "observation_id": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'        },\r\n'
    b'        "observer_id": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'        },\r\n'
    b'        "authority_provider_id": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'        },\r\n'
    b'        "publication_root_sha256": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[0-9a-f]{64}$"\r\n'
    b'        },\r\n'
    b'        "cluster_id": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'        },\r\n'
    b'        "cluster_generation": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'        },\r\n'
    b'        "commit_id": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'        },\r\n'
    b'        "submitted_at_utc": {\r\n'
    b'          "anyOf": [\r\n'
    b'            {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\\\.[0-9]{3}Z$"\r\n'
    b'            },\r\n'
    b'            {\r\n'
    b'              "type": "null"\r\n'
    b'            }\r\n'
    b'          ]\r\n'
    b'        },\r\n'
    b'        "clock_uncertainty_ms": {\r\n'
    b'          "anyOf": [\r\n'
    b'            {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^(0|[1-9][0-9]{0,18})$"\r\n'
    b'            },\r\n'
    b'            {\r\n'
    b'              "type": "null"\r\n'
    b'            }\r\n'
    b'          ]\r\n'
    b'        },\r\n'
    b'        "clock_epoch_id": {\r\n'
    b'          "anyOf": [\r\n'
    b'            {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'            },\r\n'
    b'            {\r\n'
    b'              "type": "null"\r\n'
    b'            }\r\n'
    b'          ]\r\n'
    b'        },\r\n'
    b'        "submitted_clock_epoch_id": {\r\n'
    b'          "anyOf": [\r\n'
    b'            {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'            },\r\n'
    b'            {\r\n'
    b'              "type": "null"\r\n'
    b'            }\r\n'
    b'          ]\r\n'
    b'        },\r\n'
    b'        "submitted_clock_uncertainty_ms": {\r\n'
    b'          "anyOf": [\r\n'
    b'            {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^(0|[1-9][0-9]{0,18})$"\r\n'
    b'            },\r\n'
    b'            {\r\n'
    b'              "type": "null"\r\n'
    b'            }\r\n'
    b'          ]\r\n'
    b'        },\r\n'
    b'        "audit_evidence_ref": {\r\n'
    b'          "anyOf": [\r\n'
    b'            {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'            },\r\n'
    b'            {\r\n'
    b'              "type": "null"\r\n'
    b'            }\r\n'
    b'          ]\r\n'
    b'        },\r\n'
    b'        "commit_status": {\r\n'
    b'          "const": "COMMITTED"\r\n'
    b'        },\r\n'
    b'        "confirmed_observed_at_utc": {\r\n'
    b'          "anyOf": [\r\n'
    b'            {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\\\.[0-9]{3}Z$"\r\n'
    b'            },\r\n'
    b'            {\r\n'
    b'              "type": "null"\r\n'
    b'            }\r\n'
    b'          ]\r\n'
    b'        },\r\n'
    b'        "publication_evidence": {\r\n'
    b'          "type": "object",\r\n'
    b'          "additionalProperties": false,\r\n'
    b'          "properties": {\r\n'
    b'            "evidence_schema": {\r\n'
    b'              "const": "unified.publication-evidence.v3-review1"\r\n'
    b'            },\r\n'
    b'            "publication_status": {\r\n'
    b'              "const": "DATA_PUBLICATION_COMMITTED"\r\n'
    b'            },\r\n'
    b'            "producer_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'            },\r\n'
    b'            "evidence_ref": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'            },\r\n'
    b'            "receipt_ref": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'            },\r\n'
    b'            "receipt_sha256": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{64}$"\r\n'
    b'            },\r\n'
    b'            "authority_modify_index": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'            },\r\n'
    b'            "request_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'            },\r\n'
    b'            "commit_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'            },\r\n'
    b'            "cluster_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'            },\r\n'
    b'            "cluster_generation": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'            },\r\n'
    b'            "job_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'            },\r\n'
    b'            "dataset_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'            },\r\n'
    b'            "source_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'            },\r\n'
    b'            "partition_id": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"\r\n'
    b'            },\r\n'
    b'            "dataset_revision": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'            },\r\n'
    b'            "checkpoint_revision": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[1-9][0-9]{0,18}$"\r\n'
    b'            },\r\n'
    b'            "full_intent_sha256": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{64}$"\r\n'
    b'            },\r\n'
    b'            "publication_root_sha256": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{64}$"\r\n'
    b'            },\r\n'
    b'            "publication_content_sha256": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{64}$"\r\n'
    b'            },\r\n'
    b'            "manifest_content_sha256": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{64}$"\r\n'
    b'            },\r\n'
    b'            "outbox_content_sha256": {\r\n'
    b'              "type": "string",\r\n'
    b'              "pattern": "^[0-9a-f]{64}$"\r\n'
    b'            }\r\n'
    b'          },\r\n'
    b'          "required": [\r\n'
    b'            "evidence_schema",\r\n'
    b'            "publication_status",\r\n'
    b'            "producer_id",\r\n'
    b'            "evidence_ref",\r\n'
    b'            "receipt_ref",\r\n'
    b'            "receipt_sha256",\r\n'
    b'            "authority_modify_index",\r\n'
    b'            "request_id",\r\n'
    b'            "commit_id",\r\n'
    b'            "cluster_id",\r\n'
    b'            "cluster_generation",\r\n'
    b'            "job_id",\r\n'
    b'            "dataset_id",\r\n'
    b'            "source_id",\r\n'
    b'            "partition_id",\r\n'
    b'            "dataset_revision",\r\n'
    b'            "checkpoint_revision",\r\n'
    b'            "full_intent_sha256",\r\n'
    b'            "publication_root_sha256",\r\n'
    b'            "publication_content_sha256",\r\n'
    b'            "manifest_content_sha256",\r\n'
    b'            "outbox_content_sha256"\r\n'
    b'          ]\r\n'
    b'        }\r\n'
    b'      },\r\n'
    b'      "required": [\r\n'
    b'        "schema_version",\r\n'
    b'        "schema",\r\n'
    b'        "authority_profile",\r\n'
    b'        "publication_content",\r\n'
    b'        "publication_content_sha256",\r\n'
    b'        "receipt_ref",\r\n'
    b'        "authority_modify_index",\r\n'
    b'        "observation_id",\r\n'
    b'        "observer_id",\r\n'
    b'        "authority_provider_id",\r\n'
    b'        "publication_root_sha256",\r\n'
    b'        "cluster_id",\r\n'
    b'        "cluster_generation",\r\n'
    b'        "commit_id",\r\n'
    b'        "submitted_at_utc",\r\n'
    b'        "clock_uncertainty_ms",\r\n'
    b'        "clock_epoch_id",\r\n'
    b'        "submitted_clock_epoch_id",\r\n'
    b'        "submitted_clock_uncertainty_ms",\r\n'
    b'        "audit_evidence_ref",\r\n'
    b'        "commit_status",\r\n'
    b'        "confirmed_observed_at_utc",\r\n'
    b'        "publication_evidence"\r\n'
    b'      ]\r\n'
    b'    },\r\n'
    b'    {\r\n'
    b'      "type": "object",\r\n'
    b'      "additionalProperties": false,\r\n'
    b'      "properties": {\r\n'
    b'        "schema_version": {\r\n'
    b'          "const": "3"\r\n'
    b'        },\r\n'
    b'        "schema": {\r\n'
    b'          "const": "unified.historical-checkpoint-unconfirmed.v3-review1"\r\n'
    b'        },\r\n'
    b'        "authority_profile": {\r\n'
    b'          "const": "unified.authority.event-ordered.v3"\r\n'
    b'        },\r\n'
    b'        "commit_status": {\r\n'
    b'          "const": "COMMIT_UNCONFIRMED"\r\n'
    b'        },\r\n'
    b'        "cluster_id": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'        },\r\n'
    b'        "cluster_generation": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'        },\r\n'
    b'        "request_id": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'        },\r\n'
    b'        "commit_id": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"\r\n'
    b'        },\r\n'
    b'        "full_intent_sha256": {\r\n'
    b'          "type": "string",\r\n'
    b'          "pattern": "^[0-9a-f]{64}$"\r\n'
    b'        },\r\n'
    b'        "reason": {\r\n'
    b'          "enum": [\r\n'
    b'            "AUTHORITY_UNAVAILABLE",\r\n'
    b'            "RECEIPT_UNVERIFIED",\r\n'
    b'            "CONFLICTING_EVIDENCE"\r\n'
    b'          ]\r\n'
    b'        }\r\n'
    b'      },\r\n'
    b'      "required": [\r\n'
    b'        "schema_version",\r\n'
    b'        "schema",\r\n'
    b'        "authority_profile",\r\n'
    b'        "commit_status",\r\n'
    b'        "cluster_id",\r\n'
    b'        "cluster_generation",\r\n'
    b'        "request_id",\r\n'
    b'        "commit_id",\r\n'
    b'        "full_intent_sha256",\r\n'
    b'        "reason"\r\n'
    b'      ]\r\n'
    b'    }\r\n'
    b'  ]\r\n'
    b'}\r\n'
)
SCHEMA_SHA256 = hashlib.sha256(_SCHEMA_BYTES).hexdigest()
_SCHEMA = json.loads(_SCHEMA_BYTES)
_U63_PATTERNS = {"^(0|[1-9][0-9]{0,18})$", "^[1-9][0-9]{0,18}$"}


def _fail():
    # Do not echo untrusted payload/evidence/identity values in diagnostics.
    raise CheckpointFormatError("Unsupported or inconsistent checkpoint V3 claim")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _safe_tree(value, depth=1, budget=None):
    if budget is None:
        budget = [MAX_BYTES]
    if depth > MAX_DEPTH:
        _fail()
    if type(value) is dict:
        if len(value) > MAX_MEMBERS:
            _fail()
        budget[0] -= 2 + max(0, len(value) - 1)
        for key, child in value.items():
            if type(key) is not str or any(not 32 <= ord(ch) <= 126 for ch in key):
                _fail()
            budget[0] -= len(key) + key.count('"') + key.count('\\') + 3
            if budget[0] < 0:
                _fail()
            _safe_tree(child, depth + 1, budget)
    elif type(value) is str:
        if len(value) > MAX_BYTES:
            _fail()
        if any(not 32 <= ord(ch) <= 126 for ch in value):
            _fail()
        budget[0] -= len(value) + value.count('"') + value.count('\\') + 2
    elif value is None or type(value) is bool:
        budget[0] -= len(str(value).lower())
    elif value is not None and type(value) is not bool:
        # No arrays or JSON numeric values occur in the closed V3 result schema.
        _fail()
    if budget[0] < 0:
        _fail()


def _matches(value, spec):
    """Validate only the fixed schema's finite subset, not arbitrary JSON Schema."""
    if "oneOf" in spec or "anyOf" in spec:
        choices = spec.get("oneOf", spec.get("anyOf"))
        count = sum(_matches(value, choice) for choice in choices)
        return count == 1 if "oneOf" in spec else count > 0
    if "const" in spec:
        expected = spec["const"]
        return type(value) is type(expected) and value == expected
    if "enum" in spec:
        return type(value) is str and value in spec["enum"]
    kind = spec.get("type")
    if kind == "object":
        if type(value) is not dict:
            return False
        props = spec["properties"]
        if set(value) != set(spec["required"]):
            return False
        return all(_matches(child, props[key]) for key, child in value.items())
    if kind == "null":
        return value is None
    if kind == "string":
        if type(value) is not str:
            return False
        pattern = spec.get("pattern")
        if pattern and re.fullmatch(pattern, value) is None:
            return False
        if pattern in _U63_PATTERNS and int(value) > MAX_U63:
            return False
        return True
    return False


def _audit_clock(value, time_key, epoch_key, uncertainty_key):
    time_value, epoch, uncertainty = (value[time_key], value[epoch_key], value[uncertainty_key])
    if time_value is None:
        if epoch is not None or uncertainty is not None:
            _fail()
        return None
    if epoch is None or uncertainty is None or value["audit_evidence_ref"] is None:
        _fail()
    try:
        parsed = datetime.strptime(time_value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        _fail()
    if not 1970 <= parsed.year <= 9999:
        _fail()
    return parsed


def _relationships(value):
    if value["commit_status"] == "COMMIT_UNCONFIRMED":
        if value["request_id"] != value["commit_id"]:
            _fail()
        return
    body = value["publication_content"]
    proof = value["publication_evidence"]
    if body["instrument_id"]["category"] != "linear":
        # This exact version's source_id is the closed linear/1m source.
        _fail()
    if hashlib.sha256(_canonical(body)).hexdigest() != value["publication_content_sha256"]:
        _fail()
    for key in ("cluster_id", "cluster_generation", "commit_id"):
        if value[key] != body[key] or proof[key] != body[key]:
            _fail()
    for key in ("dataset_id", "source_id", "partition_id", "checkpoint_revision"):
        if proof[key] != body[key]:
            _fail()
    for key in ("receipt_ref", "authority_modify_index", "publication_root_sha256", "publication_content_sha256"):
        if proof[key] != value[key]:
            _fail()
    if proof["request_id"] != body["commit_id"] or proof["producer_id"] != value["authority_provider_id"]:
        _fail()
    if proof["manifest_content_sha256"] != body["segment_manifest_sha256"]:
        _fail()
    fence = body["fencing_token"]
    for key in ("cluster_generation", "assignment_id", "lease_id", "assignment_revision", "lease_epoch", "grant_revision", "owner_id", "node_id", "worker_incarnation_id"):
        if fence[key] != body[key]:
            _fail()
    revision = int(body["checkpoint_revision"])
    if (revision == 1) != (body["previous_checkpoint_sha256"] is None):
        _fail()
    target, request = body["target_range"], body["source_cursor"]["requested_range"]
    lo, hi = int(target["start_ms"]), int(target["end_ms"])
    request_lo, request_hi = int(request["start_ms"]), int(request["end_ms"])
    frontier = int(body["committed_cursor"]["disposition_frontier_ms"])
    if not lo < hi or lo % 60000 or hi % 60000:
        _fail()
    if not lo <= request_lo < request_hi <= hi or request_lo % 60000 or request_hi % 60000:
        _fail()
    if int(body["source_cursor"]["request_end_ms"]) != request_hi - 1:
        _fail()
    if not lo <= frontier <= hi or frontier % 60000:
        _fail()
    expected_next = None if frontier == lo else str(frontier - 1)
    if body["committed_cursor"]["next_end_ms"] != expected_next:
        _fail()
    observed = _audit_clock(value, "confirmed_observed_at_utc", "clock_epoch_id", "clock_uncertainty_ms")
    submitted = _audit_clock(value, "submitted_at_utc", "submitted_clock_epoch_id", "submitted_clock_uncertainty_ms")
    if observed and submitted and value["clock_epoch_id"] == value["submitted_clock_epoch_id"] and submitted > observed:
        _fail()


def _validated_bytes(value):
    _safe_tree(value)
    if not _matches(value, _SCHEMA):
        _fail()
    _relationships(value)
    raw = _canonical(value)
    if len(raw) > MAX_BYTES:
        _fail()
    return raw


def _preflight(raw):
    if type(raw) is not bytes or not raw or len(raw) > MAX_BYTES:
        _fail()
    depth, quoted, escaped = 0, False, False
    for ch in raw:
        if quoted:
            if escaped:
                escaped = False
            elif ch == 92:
                escaped = True
            elif ch == 34:
                quoted = False
        elif ch == 34:
            quoted = True
        elif ch in (123, 91):
            depth += 1
            if depth > MAX_DEPTH:
                _fail()
        elif ch in (125, 93):
            depth -= 1
            if depth < 0:
                _fail()
    if quoted or depth:
        _fail()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def _number(_):
    _fail()


@dataclass(frozen=True)
class ParsedCheckpointClaim:
    """Canonical immutable bytes of an UNTRUSTED claim, never a proof handle."""
    canonical_bytes: bytes

    def as_dict(self):
        return json.loads(self.canonical_bytes)

    @property
    def commit_status(self):
        return self.as_dict()["commit_status"]


def parse_claim(raw: bytes) -> ParsedCheckpointClaim:
    """Reject unsupported versions/aliases/noncanonical input; verify no authority."""
    _preflight(raw)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_int=_number, parse_float=_number, parse_constant=_number)
        canonical = _validated_bytes(value)
    except (UnicodeError, ValueError, RecursionError, KeyError, TypeError) as exc:
        if isinstance(exc, CheckpointFormatError):
            raise
        raise CheckpointFormatError("Invalid checkpoint V3 claim") from None
    if canonical != raw:
        _fail()
    return ParsedCheckpointClaim(canonical)


def encode_claim(value: dict) -> bytes:
    """Encode validated CLAIM structure only; no external evidence is verified."""
    return _validated_bytes(value)


def require_authoritative_checkpoint(claim):
    """Always deny: actual A2/A4 proof integration is not admitted in this module."""
    raise AuthorityIntegrationUnavailable("Actual publication proof integration is unavailable")
