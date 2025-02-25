# Simple File Conversion Service

This FastAPI service supports file conversions between PDF, DOCX, and other formats like HTML. Use the `/convert` endpoint to convert files by specifying the `from_format`, `to_format`, and uploading the file.

## Endpoints
- `/`: Returns "hello, world!"
- `/ping`: Returns "pong"
- `/convert`: Converts files from one format to another and downloads the converted file.

Files are temporarily stored and automatically deleted after 1 minute.

# Usage

Run from docker

```bash
docker run -d --name converter -p 8000:80 shellphy/chatwiki_converter
```

Convert html doc file to markdown

```bash
curl -X POST -F "from_format=html" -F "to_format=md" -F "file=@/path/to/example.html" http://127.0.0.1:8000/convert --output result.md
```

Convert html string to markdown

```bash
curl -X POST -F "from_format=html" -F "to_format=md" -F "content=hello,world" http://127.0.0.1:8000/convert --output result.md
```

Build docker image

```bash
docker build --platform linux/amd64 -t registry.cn-hangzhou.aliyuncs.com/chatwiki/converter:{tag} .
```
