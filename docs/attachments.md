# Attachments

Attachments store large blobs next to a log without forcing the blob into indexed log text.

Create an attachment:

```text
POST /v1/logs/{log_id}/attachments
```

```json
{
  "filename": "traceback.txt",
  "content_type": "text/plain",
  "content_base64": "VGltZW91dCBzdGFja3RyYWNl..."
}
```

List attachments:

```text
GET /v1/logs/{log_id}/attachments
```

Download an attachment:

```text
GET /v1/logs/{log_id}/attachments/{attachment_id}
```

Rules:

- Upload requires `logs:write`.
- Listing and downloading require `logs:read`.
- Attachment metadata is searchable through the owning log context, but blob content is not full-text indexed.
- Persistent mode stores bytes in MinIO and metadata in Postgres.
- Public attachment metadata does not expose internal MinIO object keys.
