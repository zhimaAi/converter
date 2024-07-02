# Simple File Conversion Service

This FastAPI service supports file conversions between PDF, DOCX, and other formats like HTML. Use the `/convert` endpoint to convert files by specifying the `from_format`, `to_format`, and uploading the file.

## Endpoints
- `/`: Returns "hello, world!"
- `/ping`: Returns "pong"
- `/convert`: Converts files from one format to another and downloads the converted file.

Files are temporarily stored and automatically deleted after 1 minute.
